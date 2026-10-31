"""Command line: meeting-briefer <notes.txt | recording.mp3> [--no-audio] [--out folder]

A text file is used as the transcript. An audio or video file (.mp3, .wav, .m4a, ...) is
transcribed with ElevenLabs Scribe first.
"""

import argparse
import sys
from pathlib import Path

from . import pipeline
from .config import MissingKeyError, get_settings
from .extract import ExtractionError
from .logging_setup import setup_logging
from .stt import AUDIO_SUFFIXES


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="meeting-briefer", description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("input", type=Path, help="Text file with notes, or a meeting recording.")
    parser.add_argument("--no-audio", action="store_true", help="Skip the spoken briefing.")
    parser.add_argument("--out", type=Path, help="Output folder (default: out/<run id>).")
    args = parser.parse_args(argv)

    settings = get_settings()
    setup_logging(settings.log_level)
    try:
        if args.input.suffix.lower() in AUDIO_SUFFIXES:
            result = pipeline.run_from_audio(
                args.input.read_bytes(),
                args.input.name,
                settings,
                audio=not args.no_audio,
                out_dir=args.out,
            )
        else:
            text = args.input.read_text(encoding="utf-8")
            result = pipeline.run(text, settings, audio=not args.no_audio, out_dir=args.out)
    except (MissingKeyError, ExtractionError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    if result.transcript:
        print(f"Transcript:\n{result.transcript}\n")
    print(result.script)
    print(f"\nWritten to {result.folder}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
