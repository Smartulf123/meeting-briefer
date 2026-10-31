"""Transcript (or recording) in, summary.json + briefing.txt + briefing.mp3 out."""

import json
import logging
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from .briefing import build_script
from .config import Settings
from .extract import ExtractionResult, extract
from .models import MeetingSummary
from .stt import Transcription, transcribe
from .tts import synthesize

log = logging.getLogger(__name__)

Extractor = Callable[[str, Settings], ExtractionResult]
Synthesizer = Callable[[str, Settings], bytes]
Transcriber = Callable[[bytes, str, Settings], Transcription]


@dataclass
class BriefingRun:
    id: str
    folder: Path
    summary: MeetingSummary
    script: str
    audio_path: Path | None
    attempts: int
    transcript: str | None = None  # set when the input was a recording


def run(
    transcript: str,
    settings: Settings,
    *,
    audio: bool = True,
    out_dir: Path | None = None,
    run_id: str | None = None,
    extractor: Extractor = extract,
    synthesizer: Synthesizer = synthesize,
) -> BriefingRun:
    run_id = run_id or uuid.uuid4().hex[:12]
    folder = out_dir or settings.output_dir / run_id
    folder.mkdir(parents=True, exist_ok=True)

    result = extractor(transcript, settings)
    script = build_script(result.summary)

    (folder / "summary.json").write_text(
        json.dumps(result.summary.model_dump(), indent=2, ensure_ascii=False), encoding="utf-8"
    )
    (folder / "briefing.txt").write_text(script + "\n", encoding="utf-8")

    audio_path = None
    if audio:
        audio_path = folder / "briefing.mp3"
        audio_path.write_bytes(synthesizer(script, settings))

    log.info("run id=%s folder=%s attempts=%d audio=%s", run_id, folder, result.attempts, audio)
    return BriefingRun(run_id, folder, result.summary, script, audio_path, result.attempts)


def run_from_audio(
    recording: bytes,
    filename: str,
    settings: Settings,
    *,
    audio: bool = True,
    out_dir: Path | None = None,
    transcriber: Transcriber = transcribe,
    **kwargs,
) -> BriefingRun:
    """Transcribe a recording first, keep the transcript next to the other outputs."""
    run_id = uuid.uuid4().hex[:12]
    folder = out_dir or settings.output_dir / run_id
    folder.mkdir(parents=True, exist_ok=True)

    transcription = transcriber(recording, filename, settings)
    (folder / "transcript.txt").write_text(transcription.text + "\n", encoding="utf-8")

    result = run(transcription.text, settings, audio=audio, out_dir=folder, run_id=run_id, **kwargs)
    result.transcript = transcription.text
    return result
