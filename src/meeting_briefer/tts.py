"""Speak the briefing script with the ElevenLabs text-to-speech API."""

import logging
import time
from typing import Any

from .config import Settings, require

log = logging.getLogger(__name__)


def synthesize(text: str, settings: Settings, client: Any = None) -> bytes:
    if client is None:
        from elevenlabs.client import ElevenLabs

        client = ElevenLabs(api_key=require(settings.elevenlabs_api_key, "ELEVENLABS_API_KEY"))

    started = time.perf_counter()
    chunks = client.text_to_speech.convert(
        voice_id=settings.elevenlabs_voice_id,
        text=text,
        model_id=settings.elevenlabs_model,
        output_format="mp3_44100_128",
    )
    audio = b"".join(chunks)
    log.info(
        "tts model=%s characters=%d bytes=%d seconds=%.1f",
        settings.elevenlabs_model,
        len(text),
        len(audio),
        time.perf_counter() - started,
    )
    return audio
