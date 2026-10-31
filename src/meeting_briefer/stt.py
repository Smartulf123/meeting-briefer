"""Turn a meeting recording into a speaker-labelled transcript with ElevenLabs Scribe."""

import logging
import time
from dataclasses import dataclass
from typing import Any

from .config import Settings, require

log = logging.getLogger(__name__)

AUDIO_SUFFIXES = {".mp3", ".wav", ".m4a", ".ogg", ".webm", ".flac", ".mp4"}


@dataclass
class Transcription:
    text: str
    speakers: int
    audio_seconds: float | None


def format_transcript(words: list[Any]) -> tuple[str, int]:
    """Group Scribe's word list into one line per speaker turn: "Speaker 1: ...".

    Scribe returns words and the spaces between them as separate items, each with a
    speaker_id such as "speaker_0". A new line starts whenever the speaker changes.
    """
    labels: dict[str, str] = {}
    lines: list[tuple[str, str]] = []
    for word in words:
        if word.type == "audio_event":
            continue
        speaker = word.speaker_id or "speaker_0"
        if speaker not in labels:
            labels[speaker] = f"Speaker {len(labels) + 1}"
        label = labels[speaker]
        if word.type == "word" and (not lines or lines[-1][0] != label):
            lines.append((label, word.text))
        elif lines:
            lines[-1] = (lines[-1][0], lines[-1][1] + word.text)
    text = "\n".join(f"{label}: {said.strip()}" for label, said in lines if said.strip())
    return text, len(labels)


def transcribe(
    audio: bytes, filename: str, settings: Settings, client: Any = None
) -> Transcription:
    if client is None:
        from elevenlabs.client import ElevenLabs

        client = ElevenLabs(api_key=require(settings.elevenlabs_api_key, "ELEVENLABS_API_KEY"))

    started = time.perf_counter()
    result = client.speech_to_text.convert(
        file=(filename, audio),
        model_id=settings.stt_model,
        language_code="en",
        diarize=True,
        tag_audio_events=False,
    )
    text, speakers = format_transcript(result.words or [])
    seconds = getattr(result, "audio_duration_secs", None)
    log.info(
        "stt model=%s bytes=%d audio_seconds=%s speakers=%d characters=%d seconds=%.1f",
        settings.stt_model,
        len(audio),
        seconds,
        speakers,
        len(text),
        time.perf_counter() - started,
    )
    if not text:
        raise ValueError("No speech was found in the recording.")
    return Transcription(text, speakers, seconds)
