from meeting_briefer.briefing import build_script
from meeting_briefer.models import ActionItem, MeetingSummary


def test_script_reads_decisions_and_actions(summary):
    script = build_script(summary)
    assert script.startswith("Briefing: Pricing sync.")
    assert "One decision: New pricing goes live on March 1st." in script
    assert "2 action items:" in script
    assert "Jonas will update the pricing page, by Friday." in script
    assert "Nobody owns this yet: check the onboarding emails." in script
    assert script.endswith("That's all.")


def test_empty_meeting_and_open_questions():
    summary = MeetingSummary(
        title="Brainstorm",
        summary="Ideas only.",
        decisions=[],
        action_items=[],
        open_questions=["Voice mode?", "Weekly digest?"],
    )
    script = build_script(summary)
    assert "No decisions were made. No action items." in script
    assert "Still open: Voice mode and Weekly digest." in script


def test_single_action_wording():
    summary = MeetingSummary(
        title="Sync",
        summary="Short sync.",
        decisions=["Ship it", "Hire two people"],
        action_items=[ActionItem(task="Write the release notes.", owner="Li", due=None)],
        open_questions=[],
    )
    script = build_script(summary)
    assert "2 decisions: Ship it. Hire two people." in script
    assert "One action item: Li will write the release notes." in script
