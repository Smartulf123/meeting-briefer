"""FastAPI app: POST a transcript or a recording, get the summary JSON and a link to the audio.

Run locally:  uvicorn meeting_briefer.api:app --reload   then open http://127.0.0.1:8000

Bring your own keys: callers can send their own Anthropic and ElevenLabs keys in the
X-Anthropic-Api-Key and X-ElevenLabs-Api-Key headers. They are used for that one request
and never stored or logged. Without the headers the server falls back to its .env keys.
"""

import hashlib
import hmac
import logging
import re
import time
from pathlib import Path

import anthropic
from elevenlabs.core import ApiError as ElevenLabsError
from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, SecretStr, ValidationError

from . import pipeline
from .config import MissingKeyError, Settings, get_settings
from .extract import ExtractionError
from .logging_setup import setup_logging
from .models import MeetingSummary

log = logging.getLogger(__name__)
INDEX_HTML = Path(__file__).parent / "static" / "index.html"
MAX_SIGNATURE_AGE = 300  # seconds


class BriefingRequest(BaseModel):
    transcript: str = Field(min_length=20, max_length=100_000)
    audio: bool = True
    source: str | None = Field(default=None, description="Where the transcript came from.")


class BriefingResponse(BaseModel):
    id: str
    summary: MeetingSummary
    script: str
    audio_url: str | None
    attempts: int
    transcript: str | None = Field(
        default=None, description="Machine transcript, when the input was a recording."
    )


def sign(body: bytes, timestamp: str, secret: str) -> str:
    """Slack-style signature over "<timestamp>.<body>", so an old request can't be replayed."""
    message = timestamp.encode() + b"." + body
    return "sha256=" + hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()


def verify_signature(
    body: bytes, header: str | None, timestamp: str | None, secret: str, now: float | None = None
) -> bool:
    if not header or not timestamp or not timestamp.isdigit():
        return False
    now = time.time() if now is None else now
    if abs(now - int(timestamp)) > MAX_SIGNATURE_AGE:
        return False
    return hmac.compare_digest(sign(body, timestamp, secret), header)


def with_caller_keys(settings: Settings, anthropic_key: str | None, eleven_key: str | None):
    """Per-request copy of the settings that uses the caller's keys when given."""
    update = {}
    if anthropic_key:
        update["anthropic_api_key"] = SecretStr(anthropic_key.strip())
    if eleven_key:
        update["elevenlabs_api_key"] = SecretStr(eleven_key.strip())
    return settings.model_copy(update=update) if update else settings


def _media_type(request: Request) -> str:
    return request.headers.get("content-type", "").split(";")[0].strip().lower()


def _check_signature(settings: Settings, body: bytes, signature, timestamp) -> None:
    if settings.webhook_secret is None:
        return
    if not verify_signature(body, signature, timestamp, settings.webhook_secret.get_secret_value()):
        log.warning("webhook rejected reason=bad_or_stale_signature")
        raise HTTPException(401, detail="Invalid, missing or expired X-Signature/X-Timestamp.")


async def _execute(fn, *args, **kwargs) -> pipeline.BriefingRun:
    """Run the blocking pipeline off the event loop and turn known failures into HTTP errors."""
    try:
        return await run_in_threadpool(fn, *args, **kwargs)
    except MissingKeyError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except anthropic.AuthenticationError as exc:
        raise HTTPException(status_code=401, detail="Anthropic rejected the API key.") from exc
    except ElevenLabsError as exc:
        if exc.status_code == 401:
            raise HTTPException(401, detail="ElevenLabs rejected the API key.") from exc
        raise HTTPException(502, detail=f"ElevenLabs error {exc.status_code}.") from exc
    except ExtractionError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ValueError as exc:  # e.g. a recording with no speech in it
        raise HTTPException(status_code=422, detail=str(exc)) from exc


def _response(result: pipeline.BriefingRun) -> BriefingResponse:
    return BriefingResponse(
        id=result.id,
        summary=result.summary,
        script=result.script,
        audio_url=f"/briefings/{result.id}/audio" if result.audio_path else None,
        attempts=result.attempts,
        transcript=result.transcript,
    )


def create_app(run=pipeline.run, run_audio=pipeline.run_from_audio) -> FastAPI:
    app = FastAPI(title="meeting-briefer", version="0.2.0")

    @app.get("/", include_in_schema=False)
    def index() -> FileResponse:
        return FileResponse(INDEX_HTML, media_type="text/html")

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok"}

    @app.post("/briefings", response_model=BriefingResponse)
    async def create_briefing(
        request: Request,
        settings: Settings = Depends(get_settings),
        x_signature: str | None = Header(default=None),
        x_timestamp: str | None = Header(default=None),
        x_anthropic_api_key: str | None = Header(default=None),
        x_elevenlabs_api_key: str | None = Header(default=None),
    ) -> BriefingResponse:
        # Browsers can send text/plain or form posts cross-site without a CORS preflight.
        # Requiring JSON forces the preflight, so another website can't spend this server's keys.
        if _media_type(request) != "application/json":
            raise HTTPException(status_code=415, detail="Content-Type must be application/json.")

        body = await request.body()
        _check_signature(settings, body, x_signature, x_timestamp)
        try:
            payload = BriefingRequest.model_validate_json(body)
        except ValidationError as exc:
            raise HTTPException(status_code=422, detail=exc.errors(include_url=False)) from exc

        settings = with_caller_keys(settings, x_anthropic_api_key, x_elevenlabs_api_key)
        log.info(
            "briefing received source=%s chars=%d caller_keys=%s",
            payload.source,
            len(payload.transcript),
            bool(x_anthropic_api_key or x_elevenlabs_api_key),
        )
        result = await _execute(run, payload.transcript, settings, audio=payload.audio)
        return _response(result)

    @app.post("/briefings/audio", response_model=BriefingResponse)
    async def create_briefing_from_audio(
        request: Request,
        settings: Settings = Depends(get_settings),
        audio: bool = Query(default=True, description="Also make the spoken briefing."),
        filename: str = Query(default="meeting.mp3", max_length=200),
        x_signature: str | None = Header(default=None),
        x_timestamp: str | None = Header(default=None),
        x_anthropic_api_key: str | None = Header(default=None),
        x_elevenlabs_api_key: str | None = Header(default=None),
    ) -> BriefingResponse:
        """Upload a recording as the raw request body, e.g. Content-Type: audio/mpeg.

        A raw audio/* body (not a multipart form) keeps the CORS preflight in place.
        """
        media_type = _media_type(request)
        if not media_type.startswith(("audio/", "video/")):
            raise HTTPException(415, detail="Send the recording with an audio/* Content-Type.")

        limit = settings.max_upload_mb * 1024 * 1024
        declared = request.headers.get("content-length", "")
        if declared.isdigit() and int(declared) > limit:
            raise HTTPException(
                413, detail=f"Recording is larger than {settings.max_upload_mb} MB."
            )
        body = await request.body()
        if len(body) > limit:
            raise HTTPException(
                413, detail=f"Recording is larger than {settings.max_upload_mb} MB."
            )
        if not body:
            raise HTTPException(422, detail="The recording is empty.")
        _check_signature(settings, body, x_signature, x_timestamp)

        settings = with_caller_keys(settings, x_anthropic_api_key, x_elevenlabs_api_key)
        log.info(
            "recording received type=%s bytes=%d caller_keys=%s",
            media_type,
            len(body),
            bool(x_anthropic_api_key or x_elevenlabs_api_key),
        )
        result = await _execute(run_audio, body, Path(filename).name, settings, audio=audio)
        return _response(result)

    @app.get("/briefings/{run_id}/audio")
    def get_audio(run_id: str, settings: Settings = Depends(get_settings)) -> FileResponse:
        if not re.fullmatch(r"[0-9a-f]{12}", run_id):
            raise HTTPException(status_code=404)
        path = Path(settings.output_dir) / run_id / "briefing.mp3"
        if not path.is_file():
            raise HTTPException(status_code=404)
        return FileResponse(path, media_type="audio/mpeg")

    return app


setup_logging(get_settings().log_level)
app = create_app()
