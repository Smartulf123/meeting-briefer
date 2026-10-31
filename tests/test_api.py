import hashlib
import hmac
import json
import time

from fastapi.testclient import TestClient
from pydantic import SecretStr

from meeting_briefer import pipeline
from meeting_briefer.api import create_app, sign, verify_signature
from meeting_briefer.config import get_settings
from meeting_briefer.extract import ExtractionResult

from .conftest import TRANSCRIPT


def make_client(settings, summary, seen=None):
    def fake_run(transcript, s, audio=True):
        if seen is not None:
            seen.append(s)
        return pipeline.run(
            transcript,
            s,
            audio=audio,
            extractor=lambda t, _: ExtractionResult(summary, attempts=1),
            synthesizer=lambda text, _: b"ID3-fake-mp3",
        )

    app = create_app(run=fake_run)
    app.dependency_overrides[get_settings] = lambda: settings
    return TestClient(app)


def test_health_and_index_page(settings, summary):
    client = make_client(settings, summary)
    assert client.get("/health").json() == {"status": "ok"}
    page = client.get("/")
    assert page.status_code == 200 and "X-Anthropic-Api-Key" in page.text


def test_caller_keys_are_used_for_that_request_only(settings, summary):
    seen = []
    client = make_client(settings, summary, seen)
    headers = {"X-Anthropic-Api-Key": "sk-ant-caller", "X-ElevenLabs-Api-Key": "el-caller"}
    client.post("/briefings", json={"transcript": TRANSCRIPT}, headers=headers)
    client.post("/briefings", json={"transcript": TRANSCRIPT})

    assert seen[0].anthropic_api_key.get_secret_value() == "sk-ant-caller"
    assert seen[0].elevenlabs_api_key.get_secret_value() == "el-caller"
    assert seen[1].anthropic_api_key is None  # not leaked into the next request
    assert settings.anthropic_api_key is None


def test_missing_key_is_400_with_a_clear_message(settings, summary):
    app = create_app()  # real pipeline, no keys anywhere
    app.dependency_overrides[get_settings] = lambda: settings
    resp = TestClient(app).post("/briefings", json={"transcript": TRANSCRIPT})
    assert resp.status_code == 400
    assert "ANTHROPIC_API_KEY" in resp.json()["detail"]


def test_create_briefing_and_fetch_audio(settings, summary):
    client = make_client(settings, summary)
    resp = client.post("/briefings", json={"transcript": TRANSCRIPT, "source": "test"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["summary"]["action_items"][0]["owner"] == "Jonas"
    assert body["script"].startswith("Briefing:")

    audio = client.get(body["audio_url"])
    assert audio.status_code == 200
    assert audio.headers["content-type"] == "audio/mpeg"
    assert audio.content == b"ID3-fake-mp3"


def test_audio_can_be_skipped(settings, summary):
    resp = make_client(settings, summary).post(
        "/briefings", json={"transcript": TRANSCRIPT, "audio": False}
    )
    assert resp.json()["audio_url"] is None


def test_too_short_transcript_is_422(settings, summary):
    resp = make_client(settings, summary).post("/briefings", json={"transcript": "hi"})
    assert resp.status_code == 422


def test_bad_audio_id_is_404(settings, summary):
    assert make_client(settings, summary).get("/briefings/../../.env/audio").status_code == 404


JSON = {"Content-Type": "application/json"}


def test_signature_required_when_secret_set(settings, summary):
    settings = settings.model_copy(update={"webhook_secret": SecretStr("s3cret")})
    client = make_client(settings, summary)
    body = json.dumps({"transcript": TRANSCRIPT, "audio": False}).encode()

    assert client.post("/briefings", content=body, headers=JSON).status_code == 401

    ts = str(int(time.time()))
    expected = hmac.new(b"s3cret", ts.encode() + b"." + body, hashlib.sha256).hexdigest()
    headers = {**JSON, "X-Timestamp": ts, "X-Signature": "sha256=" + expected}
    assert client.post("/briefings", content=body, headers=headers).status_code == 200


def test_verify_signature_rejects_tampered_body_and_replays():
    now = 1_800_000_000
    ts = str(now)
    sig = sign(b"original", ts, "k")
    assert verify_signature(b"original", sig, ts, "k", now=now)
    assert not verify_signature(b"tampered", sig, ts, "k", now=now)
    assert not verify_signature(b"original", None, ts, "k", now=now)
    assert not verify_signature(b"original", sig, None, "k", now=now)
    # Same valid signature replayed ten minutes later is refused.
    assert not verify_signature(b"original", sig, ts, "k", now=now + 600)
    # Changing the timestamp to look fresh breaks the signature.
    assert not verify_signature(b"original", sig, str(now + 600), "k", now=now + 600)


def test_non_json_post_is_rejected_before_any_work(settings, summary):
    seen = []
    client = make_client(settings, summary, seen)
    body = json.dumps({"transcript": TRANSCRIPT})
    for content_type in ("text/plain", "application/x-www-form-urlencoded"):
        resp = client.post("/briefings", content=body, headers={"Content-Type": content_type})
        assert resp.status_code == 415
    assert seen == []
