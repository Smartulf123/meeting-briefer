"""Make a fake meeting recording from a "Name: line" transcript, one ElevenLabs voice per person.

    python scripts/make_test_recording.py demo/standup.txt demo/standup-recording.mp3

Used to test the audio input path end to end without recording a real meeting.
Costs about half a credit per character with the Flash v2.5 model.
"""

import sys
from pathlib import Path

from elevenlabs.client import ElevenLabs

from meeting_briefer.config import get_settings, require

# Premade ElevenLabs voices; any speaker not listed gets the next free one.
VOICES = [
    "EXAVITQu4vr4xnSDxMaL",  # Sarah
    "iP95p4xoKVk53GoZ742B",  # Chris
    "IKne3meq5aSn9XLyUdCD",  # Charlie
    "Xb7hH8MSUJpSbSDYk0k2",  # Alice
]


def main() -> int:
    source, target = Path(sys.argv[1]), Path(sys.argv[2])
    settings = get_settings()
    client = ElevenLabs(api_key=require(settings.elevenlabs_api_key, "ELEVENLABS_API_KEY"))

    turns = []
    for line in source.read_text(encoding="utf-8").splitlines():
        name, sep, said = line.partition(":")
        if sep and said.strip() and " " not in name.strip():
            turns.append((name.strip(), said.strip()))

    voices: dict[str, str] = {}
    audio = b""
    for name, said in turns:
        voice = voices.setdefault(name, VOICES[len(voices) % len(VOICES)])
        # MP3 frames can be joined end to end; a short pause separates the speakers.
        audio += b"".join(
            client.text_to_speech.convert(
                voice_id=voice,
                text=said + ' <break time="0.4s" />',
                model_id=settings.elevenlabs_model,
                output_format="mp3_44100_128",
            )
        )
    target.write_bytes(audio)
    chars = sum(len(s) for _, s in turns)
    print(f"{len(turns)} turns, {len(voices)} voices, {chars} characters -> {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
