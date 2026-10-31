from types import SimpleNamespace

import pytest

from meeting_briefer.config import Settings
from meeting_briefer.models import ActionItem, MeetingSummary

TRANSCRIPT = """Maria: The new pricing goes live March 1st, that's decided.
Jonas: I'll update the pricing page by Friday.
Maria: Someone should check the onboarding emails."""


@pytest.fixture
def settings(tmp_path) -> Settings:
    # _env_file=None: tests never read the developer's real .env or keys.
    return Settings(_env_file=None, output_dir=tmp_path, max_attempts=3)


@pytest.fixture
def summary() -> MeetingSummary:
    return MeetingSummary(
        title="Pricing sync",
        summary="The team agreed on the pricing launch date.",
        decisions=["New pricing goes live on March 1st."],
        action_items=[
            ActionItem(task="Update the pricing page", owner="Jonas", due="Friday"),
            ActionItem(task="Check the onboarding emails", owner=None, due=None),
        ],
        open_questions=[],
    )


class FakeClaude:
    """Stands in for anthropic.Anthropic. Returns the queued responses in order."""

    def __init__(self, *outputs):
        self.outputs = list(outputs)
        self.calls = []
        self.messages = self

    def parse(self, **kwargs):
        self.calls.append(kwargs)
        out = self.outputs.pop(0)
        if isinstance(out, Exception):
            raise out
        stop_reason, parsed = out if isinstance(out, tuple) else ("end_turn", out)
        return SimpleNamespace(
            stop_reason=stop_reason,
            parsed_output=parsed,
            usage=SimpleNamespace(input_tokens=100, output_tokens=50),
        )
