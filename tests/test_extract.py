import pytest

from meeting_briefer.extract import ExtractionError, check_against_transcript, extract
from meeting_briefer.models import ActionItem

from .conftest import TRANSCRIPT, FakeClaude


def test_valid_answer_returns_on_first_attempt(settings, summary):
    client = FakeClaude(summary)
    result = extract(TRANSCRIPT, settings, client=client)
    assert result.attempts == 1
    assert result.summary == summary
    assert result.input_tokens == 100
    call = client.calls[0]
    assert call["model"] == settings.extract_model
    assert "<transcript>" in call["messages"][0]["content"]


def test_invented_owner_triggers_retry_with_feedback(settings, summary):
    bad = summary.model_copy(deep=True)
    bad.action_items[0] = ActionItem(task="Update the pricing page", owner="Ola", due=None)
    client = FakeClaude(bad, summary)

    result = extract(TRANSCRIPT, settings, client=client)

    assert result.attempts == 2
    assert "Ola" in result.problems_fixed[0]
    retry_prompt = client.calls[1]["messages"][0]["content"]
    assert "was rejected" in retry_prompt and "Ola" in retry_prompt


def test_truncated_answer_is_retried(settings, summary):
    client = FakeClaude(("max_tokens", None), summary)
    assert extract(TRANSCRIPT, settings, client=client).attempts == 2


def test_gives_up_after_max_attempts(settings, summary):
    bad = summary.model_copy(deep=True)
    bad.action_items[0].owner = "Nobody Real"
    client = FakeClaude(bad, bad, bad)
    with pytest.raises(ExtractionError, match="3 attempts"):
        extract(TRANSCRIPT, settings, client=client)
    assert len(client.calls) == 3


def test_refusal_is_not_retried(settings, summary):
    client = FakeClaude(("refusal", None), summary)
    with pytest.raises(ExtractionError, match="declined"):
        extract(TRANSCRIPT, settings, client=client)
    assert len(client.calls) == 1


def test_empty_transcript_is_rejected(settings):
    with pytest.raises(ValueError):
        extract("   ", settings, client=FakeClaude())


def test_duplicate_tasks_are_flagged(summary):
    summary.action_items.append(summary.action_items[0])
    assert any("more than once" in p for p in check_against_transcript(summary, TRANSCRIPT))
