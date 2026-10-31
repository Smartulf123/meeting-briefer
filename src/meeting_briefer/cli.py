"""Command line: meeting-briefer path/to/transcript.txt [--no-audio] [--out folder]"""

import argparse
import sys
from pathlib import Path

from . import pipeline
from .config import MissingKeyError, get_settings
from .extract import ExtractionError
from .logging_setup import setup_logging


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="meeting-briefer", description=__doc__)
    parser.add_argument("transcript", type=Path, help="Text file with the transcript or notes.")
    parser.add_argument("--no-audio", action="store_true", help="Skip ElevenLabs, write JSON only.")
    parser.add_argument("--out", type=Path, help="Output folder (default: out/<run id>).")
    args = parser.parse_args(argv)

    settings = get_settings()
    setup_logging(settings.log_level)
    text = args.transcript.read_text(encoding="utf-8")
    try:
        result = pipeline.run(text, settings, audio=not args.no_audio, out_dir=args.out)
    except (MissingKeyError, ExtractionError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(result.script)
    print(f"\nWritten to {result.folder}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
