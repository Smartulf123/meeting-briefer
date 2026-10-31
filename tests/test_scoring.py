from meeting_briefer.models import ActionItem
from meeting_briefer.scoring import Expected, ExpectedAction, aggregate, score_case


def expected(*actions, decisions=()):
    return Expected(
        action_items=[ExpectedAction(owner=o, keywords=k) for o, k in actions],
        decisions=[list(d) for d in decisions],
    )


def test_perfect_match(summary):
    exp = expected(("Jonas", ["pricing page"]), (None, ["onboarding"]), decisions=[["march"]])
    s = score_case(summary, exp)
    assert (s.matched_actions, s.tasks_found, s.owners_correct, s.decisions_found) == (2, 2, 2, 1)
    assert aggregate([s])["action_f1"] == 1.0


def test_wrong_owner_counts_as_found_task_but_not_match(summary):
    summary.action_items[0].owner = "Maria"
    s = score_case(summary, expected(("Jonas", ["pricing page"])))
    assert s.tasks_found == 1 and s.owners_correct == 0 and s.matched_actions == 0


def test_predicted_owner_when_none_expected_is_wrong(summary):
    summary.action_items[1].owner = "Jonas"
    s = score_case(summary, expected((None, ["onboarding"])))
    assert s.matched_actions == 0


def test_one_prediction_cannot_match_two_expectations(summary):
    summary.action_items = [ActionItem(task="Update the pricing page", owner="Jonas", due=None)]
    s = score_case(summary, expected(("Jonas", ["pricing"]), ("Jonas", ["page"])))
    assert s.matched_actions == 1


def test_empty_case_scores_perfect_when_nothing_predicted(summary):
    summary.action_items, summary.decisions = [], []
    metrics = aggregate([score_case(summary, expected())])
    assert metrics["action_precision"] == 1.0 and metrics["decision_recall"] == 1.0


def test_hallucinated_items_lower_precision(summary):
    metrics = aggregate([score_case(summary, expected(("Jonas", ["pricing page"])))])
    assert metrics["action_recall"] == 1.0
    assert metrics["action_precision"] == 0.5
