"""FastAPI app: POST a transcript, get the summary JSON and a link to the audio.

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
from fastapi import Depends, FastAPI, Header, HTTPException, Request
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


MAX_SIGNATURE_AGE = 300  # seconds


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


def create_app(run=pipeline.run) -> FastAPI:
    app = FastAPI(title="meeting-briefer", version="0.1.0")

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
        content_type = request.headers.get("content-type", "").split(";")[0].strip().lower()
        if content_type != "application/json":
            raise HTTPException(status_code=415, detail="Content-Type must be application/json.")

        body = await request.body()
        if settings.webhook_secret is not None:
            secret = settings.webhook_secret.get_secret_value()
            if not verify_signature(body, x_signature, x_timestamp, secret):
                log.warning("webhook rejected reason=bad_or_stale_signature")
                raise HTTPException(
                    status_code=401, detail="Invalid, missing or expired X-Signature/X-Timestamp."
                )

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
        try:
            # The pipeline makes blocking HTTP calls, so keep it off the event loop.
            result = await run_in_threadpool(run, payload.transcript, settings, audio=payload.audio)
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

        return BriefingResponse(
            id=result.id,
            summary=result.summary,
            script=result.script,
            audio_url=f"/briefings/{result.id}/audio" if result.audio_path else None,
            attempts=result.attempts,
        )

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
