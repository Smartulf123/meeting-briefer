"""One-line, key=value log records so runs are easy to grep and compare."""

import logging
import sys


def setup_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s", "%H:%M:%S")
    )
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level.upper())
    # The HTTP clients are chatty at INFO; keep our own lines readable.
    for noisy in ("httpx", "httpx2", "httpcore", "anthropic", "elevenlabs"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
