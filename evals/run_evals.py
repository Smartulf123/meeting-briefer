"""Run the extractor on every case in evals/cases and score it.

    python evals/run_evals.py                      # uses EXTRACT_MODEL from .env
    python evals/run_evals.py --model claude-haiku-5-5
    python evals/run_evals.py --replay evals/results/claude-opus-5-5.json   # re-score, no API calls

Writes evals/results/<model>.json (predictions + scores) and prints a Markdown table.
"""

import argparse
import json
import sys
import time
from pathlib import Path

from meeting_briefer.config import get_settings
from meeting_briefer.extract import ExtractionError, extract
from meeting_briefer.logging_setup import setup_logging
from meeting_briefer.models import MeetingSummary
from meeting_briefer.scoring import Expected, aggregate, score_case

CASES = Path(__file__).parent / "cases"
RESULTS = Path(__file__).parent / "results"


def load_cases() -> list[tuple[str, str, Expected]]:
    cases = []
    for folder in sorted(p for p in CASES.iterdir() if p.is_dir()):
        transcript = (folder / "transcript.txt").read_text(encoding="utf-8")
        expected = Expected.model_validate_json((folder / "expected.json").read_text("utf-8"))
        cases.append((folder.name, transcript, expected))
    return cases


def table(rows: list[dict], totals: dict) -> str:
    lines = [
        "| case | actions (matched/expected/predicted) | owners right | decisions found "
        "| attempts |",
        "|---|---|---|---|---|",
    ]
    for r in rows:
        s = r["score"]
        if s is None:
            lines.append(f"| {r['case']} | failed: {r['error']} | | | |")
            continue
        lines.append(
            f"| {r['case']} | {s['matched_actions']}/{s['expected_actions']}/"
            f"{s['predicted_actions']} | {s['owners_correct']}/{s['tasks_found']} | "
            f"{s['decisions_found']}/{s['expected_decisions']} | {r['attempts']} |"
        )
    lines.append("")
    lines.append("| metric | value |")
    lines.append("|---|---|")
    lines += [f"| {k} | {v:.2f} |" for k, v in totals.items()]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", help="Override EXTRACT_MODEL.")
    parser.add_argument("--replay", type=Path, help="Re-score a saved results file.")
    args = parser.parse_args()

    settings = get_settings()
    if args.model:
        settings = settings.model_copy(update={"extract_model": args.model})
    setup_logging(settings.log_level)

    saved = {}
    if args.replay:
        saved = {r["case"]: r for r in json.loads(args.replay.read_text("utf-8"))["cases"]}

    rows, scores = [], []
    tokens_in = tokens_out = 0
    started = time.perf_counter()
    for name, transcript, expected in load_cases():
        row = {"case": name, "attempts": None, "prediction": None, "score": None, "error": None}
        try:
            if args.replay:
                row["attempts"] = saved[name]["attempts"]
                summary = MeetingSummary.model_validate(saved[name]["prediction"])
            else:
                result = extract(transcript, settings)
                summary, row["attempts"] = result.summary, result.attempts
                tokens_in += result.input_tokens
                tokens_out += result.output_tokens
        except (ExtractionError, KeyError, TypeError) as exc:
            row["error"] = str(exc)[:80]
            rows.append(row)
            continue
        score = score_case(summary, expected)
        row["prediction"] = summary.model_dump()
        row["score"] = score.as_dict()
        scores.append(score)
        rows.append(row)

    totals = aggregate(scores) if scores else {}
    failed = sum(r["score"] is None for r in rows)
    report = {
        "model": settings.extract_model,
        "effort": settings.extract_effort,
        "cases_run": len(rows),
        "cases_failed": failed,
        "input_tokens": tokens_in,
        "output_tokens": tokens_out,
        "seconds": round(time.perf_counter() - started, 1),
        "metrics": totals,
        "cases": rows,
    }
    if not args.replay:
        RESULTS.mkdir(exist_ok=True)
        out = RESULTS / f"{settings.extract_model}.{settings.extract_effort}.json"
        out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"Saved {out}", file=sys.stderr)

    print(f"## {settings.extract_model} (effort {settings.extract_effort})\n")
    print(table(rows, totals))
    print(f"\nTokens: {tokens_in} in, {tokens_out} out. Failed cases: {failed}.")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
