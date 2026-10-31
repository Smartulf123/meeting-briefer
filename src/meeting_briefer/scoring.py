"""Score an extracted MeetingSummary against hand-written expectations.

Matching is deliberately simple and transparent: an expected action item matches a predicted
one when one of its keywords appears in the predicted task, and the owner is the same person
(or both have no owner). Keywords are alternatives, so a case can accept "postmortem" or
"post-mortem". Each predicted item can match at most one expected item.
"""

from dataclasses import asdict, dataclass

from pydantic import BaseModel

from .models import ActionItem, MeetingSummary


class ExpectedAction(BaseModel):
    owner: str | None
    keywords: list[str]


class Expected(BaseModel):
    action_items: list[ExpectedAction]
    decisions: list[list[str]]  # each decision: keywords, any of which must appear


@dataclass
class CaseScore:
    expected_actions: int
    predicted_actions: int
    matched_actions: int  # right task and right owner
    tasks_found: int  # right task, owner ignored
    owners_correct: int  # of tasks_found
    expected_decisions: int
    predicted_decisions: int
    decisions_found: int
    decisions_supported: int  # predicted decisions that match some expected one

    def as_dict(self) -> dict:
        return asdict(self)


def _hits(text: str, keywords: list[str]) -> bool:
    text = text.lower()
    return any(k.lower() in text for k in keywords)


def _same_owner(expected: str | None, predicted: str | None) -> bool:
    if expected is None or predicted is None:
        return expected is None and predicted is None
    return expected.lower() in predicted.lower()


def _greedy(expected: list[ExpectedAction], predicted: list[ActionItem], use_owner: bool):
    used: set[int] = set()
    pairs = []
    for exp in expected:
        for i, pred in enumerate(predicted):
            if i in used or not _hits(pred.task, exp.keywords):
                continue
            if use_owner and not _same_owner(exp.owner, pred.owner):
                continue
            used.add(i)
            pairs.append((exp, pred))
            break
    return pairs


def score_case(summary: MeetingSummary, expected: Expected) -> CaseScore:
    strict = _greedy(expected.action_items, summary.action_items, use_owner=True)
    loose = _greedy(expected.action_items, summary.action_items, use_owner=False)
    owners_correct = sum(_same_owner(e.owner, p.owner) for e, p in loose)

    found = sum(any(_hits(d, kws) for d in summary.decisions) for kws in expected.decisions)
    supported = sum(any(_hits(d, kws) for kws in expected.decisions) for d in summary.decisions)

    return CaseScore(
        expected_actions=len(expected.action_items),
        predicted_actions=len(summary.action_items),
        matched_actions=len(strict),
        tasks_found=len(loose),
        owners_correct=owners_correct,
        expected_decisions=len(expected.decisions),
        predicted_decisions=len(summary.decisions),
        decisions_found=found,
        decisions_supported=supported,
    )


def _ratio(num: int, den: int) -> float:
    return 1.0 if den == 0 else num / den


def aggregate(scores: list[CaseScore]) -> dict[str, float]:
    """Micro-averaged metrics across all cases."""
    total = {k: sum(getattr(s, k) for s in scores) for k in CaseScore.__dataclass_fields__}
    precision = _ratio(total["matched_actions"], total["predicted_actions"])
    recall = _ratio(total["matched_actions"], total["expected_actions"])
    f1 = 0.0 if precision + recall == 0 else 2 * precision * recall / (precision + recall)
    return {
        "action_precision": precision,
        "action_recall": recall,
        "action_f1": f1,
        "owner_accuracy": _ratio(total["owners_correct"], total["tasks_found"]),
        "decision_recall": _ratio(total["decisions_found"], total["expected_decisions"]),
        "decision_precision": _ratio(total["decisions_supported"], total["predicted_decisions"]),
    }
