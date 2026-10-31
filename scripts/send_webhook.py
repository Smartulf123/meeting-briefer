"""Post a transcript to a running server, signed the same way a real sender would.

    uvicorn meeting_briefer.api:app          # in one terminal
    python scripts/send_webhook.py demo/standup.txt

Signs the body with WEBHOOK_SECRET when it is set.
"""

import hashlib
import hmac
import json
import sys
from pathlib import Path

import httpx

from meeting_briefer.config import get_settings


def main() -> int:
    path = Path(sys.argv[1])
    url = sys.argv[2] if len(sys.argv) > 2 else "http://127.0.0.1:8000"
    body = json.dumps(
        {"transcript": path.read_text(encoding="utf-8"), "source": path.name}
    ).encode()

    headers = {"Content-Type": "application/json"}
    secret = get_settings().webhook_secret
    if secret is not None:
        digest = hmac.new(secret.get_secret_value().encode(), body, hashlib.sha256).hexdigest()
        headers["X-Signature"] = f"sha256={digest}"

    resp = httpx.post(f"{url}/briefings", content=body, headers=headers, timeout=120)
    print(resp.status_code)
    print(json.dumps(resp.json(), indent=2, ensure_ascii=False))
    if resp.is_success and resp.json().get("audio_url"):
        print(f"\nAudio: {url}{resp.json()['audio_url']}")
    return 0 if resp.is_success else 1


if __name__ == "__main__":
    raise SystemExit(main())
