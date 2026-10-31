"""Check that both API keys work before spending credits on a full run.

    python scripts/check_setup.py

Makes one tiny Claude call (a few tokens) and reads the ElevenLabs voice and quota.
No audio is generated, so this uses no ElevenLabs characters. Never prints the keys.
"""

import sys

import anthropic

from meeting_briefer.config import MissingKeyError, get_settings, require


def check_claude(settings) -> bool:
    try:
        client = anthropic.Anthropic(
            api_key=require(settings.anthropic_api_key, "ANTHROPIC_API_KEY")
        )
        client.messages.create(
            model=settings.extract_model,
            max_tokens=200,
            output_config={"effort": "low"},
            messages=[{"role": "user", "content": "Reply with the single word: ok"}],
        )
    except (MissingKeyError, anthropic.APIError) as exc:
        print(f"Claude: FAILED ({type(exc).__name__}: {exc})")
        return False
    print(f"Claude: ok (model {settings.extract_model})")
    return True


def check_elevenlabs(settings) -> bool:
    try:
        from elevenlabs.client import ElevenLabs

        client = ElevenLabs(api_key=require(settings.elevenlabs_api_key, "ELEVENLABS_API_KEY"))
        voice = client.voices.get(settings.elevenlabs_voice_id)
        sub = client.user.subscription.get()
    except Exception as exc:  # the SDK raises several error types; report any of them
        print(f"ElevenLabs: FAILED ({type(exc).__name__}: {exc})")
        return False
    left = sub.character_limit - sub.character_count
    print(f"ElevenLabs: ok (voice '{voice.name}', plan {sub.tier}, {left} characters left)")
    return True


def main() -> int:
    settings = get_settings()
    results = [check_claude(settings), check_elevenlabs(settings)]
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
