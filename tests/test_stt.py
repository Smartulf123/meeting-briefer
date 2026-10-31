from types import SimpleNamespace

import pytest

from meeting_briefer import pipeline
from meeting_briefer.extract import ExtractionResult
from meeting_briefer.stt import Transcription, format_transcript, transcribe


def w(text, speaker, kind="word"):
    return SimpleNamespace(text=text, speaker_id=speaker, type=kind)


WORDS = [
    w("Omar,", "speaker_0"), w(" ", "speaker_0", "spacing"), w("you", "speaker_0"),
    w(" ", "speaker_0", "spacing"), w("own", "speaker_0"), w(" ", "speaker_0", "spacing"),
    w("it?", "speaker_0"), w(" ", "speaker_1", "spacing"),
    w("(laughs)", "speaker_1", "audio_event"), w("Yes.", "speaker_1"),
    w(" ", "speaker_0", "spacing"), w("Great.", "speaker_0"),
]  # fmt: skip


def test_format_groups_turns_by_speaker():
    text, speakers = format_transcript(WORDS)
    assert text == "Speaker 1: Omar, you own it?\nSpeaker 2: Yes.\nSpeaker 1: Great."
    assert speakers == 2


def test_format_empty():
    assert format_transcript([]) == ("", 0)


class FakeScribe:
    def __init__(self, words):
        self.words = words
        self.calls = []
        self.speech_to_text = self

    def convert(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(words=self.words, audio_duration_secs=4.2)


def test_transcribe_asks_for_speaker_labels(settings):
    client = FakeScribe(WORDS)
    result = transcribe(b"fake-mp3", "standup.mp3", settings, client=client)
    assert result.speakers == 2 and result.audio_seconds == 4.2
    call = client.calls[0]
    assert call["diarize"] is True
    assert call["model_id"] == settings.stt_model
    assert call["file"] == ("standup.mp3", b"fake-mp3")


def test_silent_recording_is_an_error(settings):
    with pytest.raises(ValueError, match="No speech"):
        transcribe(b"x", "silence.mp3", settings, client=FakeScribe([]))


def test_run_from_audio_saves_transcript_next_to_outputs(settings, summary):
    result = pipeline.run_from_audio(
        b"fake-mp3",
        "standup.mp3",
        settings,
        transcriber=lambda audio, name, s: Transcription("Speaker 1: hello there", 1, 1.0),
        extractor=lambda text, s: ExtractionResult(summary, attempts=1),
        synthesizer=lambda text, s: b"ID3",
    )
    assert result.transcript == "Speaker 1: hello there"
    assert result.folder.name == result.id  # the audio URL depends on this
    assert (result.folder / "transcript.txt").read_text().strip() == "Speaker 1: hello there"
    assert (result.folder / "briefing.mp3").read_bytes() == b"ID3"
