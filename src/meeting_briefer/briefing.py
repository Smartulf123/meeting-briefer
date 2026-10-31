"""Turn a MeetingSummary into a short script meant to be listened to, not read.

The script is built from a template instead of a second LLM call. That keeps it cheap,
deterministic and testable, and it can only say what the validated JSON says.
"""

from .models import ActionItem, MeetingSummary

DECISIONS = {0: "No decisions were made.", 1: "One decision:"}
ACTIONS = {0: "No action items.", 1: "One action item:"}


def _count(phrases: dict, n: int, noun: str) -> str:
    return phrases.get(n, f"{n} {noun}:")


def _sentence(text: str) -> str:
    return text.strip().rstrip(".") + "."


def _lower_first(text: str) -> str:
    return text[:1].lower() + text[1:] if text else text


def _join(items: list[str]) -> str:
    items = [i.strip().rstrip(".?") for i in items]
    if len(items) <= 1:
        return "".join(items)
    return ", ".join(items[:-1]) + " and " + items[-1]


def _action(item: ActionItem) -> str:
    task = _lower_first(item.task.strip().rstrip("."))
    line = f"{item.owner} will {task}" if item.owner else f"Nobody owns this yet: {task}"
    if item.due:
        line += f", by {item.due}"
    return _sentence(line)


def build_script(summary: MeetingSummary) -> str:
    parts = [f"Briefing: {summary.title.strip().rstrip('.')}.", _sentence(summary.summary)]

    parts.append(_count(DECISIONS, len(summary.decisions), "decisions"))
    parts += [_sentence(d) for d in summary.decisions]

    parts.append(_count(ACTIONS, len(summary.action_items), "action items"))
    parts += [_action(a) for a in summary.action_items]

    if summary.open_questions:
        parts.append(f"Still open: {_join(summary.open_questions)}.")

    parts.append("That's all.")
    return " ".join(parts)
