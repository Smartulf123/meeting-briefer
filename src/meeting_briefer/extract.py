"""Extract decisions and action items from a transcript with Claude.

Two layers of validation:
1. Structured outputs (messages.parse + a Pydantic model) make the API return JSON that
   matches the MeetingSummary schema.
2. Our own checks catch answers that are valid JSON but wrong for this transcript, such as
   an owner whose name never appears in it. A failed check triggers a retry that tells the
   model what was wrong. HTTP-level retries (429, 5xx, timeouts) are left to the SDK.
"""

import logging
import time
from dataclasses import dataclass, field
from typing import Any

import anthropic
import pydantic

from .config import Settings, require
from .models import MeetingSummary

log = logging.getLogger(__name__)

SYSTEM_PROMPT = """You turn meeting transcripts and notes into a structured summary.

Rules:
- Only include what the transcript supports. Never invent people, tasks or dates.
- A decision is something the group agreed on. Proposals and ideas that were not agreed
  are not decisions. "No decision yet on X" is not a decision either: put X under
  open_questions instead.
- An action item is a concrete task someone took on or was given. If a task was handed over
  to someone else later in the meeting, use the final owner.
- owner is the person's name exactly as written in the transcript. Use null when no one
  clearly owns it ("someone should...", "we need to...").
- Machine transcripts may label people as "Speaker 1", "Speaker 2". Use a real name only
  when the conversation makes clear who that speaker is (they are addressed by name and
  answer). Otherwise use the label, such as "Speaker 2".
- due is the deadline as stated. Use null when none was given.
- Write everything in plain English."""


class ExtractionError(RuntimeError):
    """Claude could not produce a usable summary within the allowed attempts."""


@dataclass
class ExtractionResult:
    summary: MeetingSummary
    attempts: int
    input_tokens: int = 0
    output_tokens: int = 0
    problems_fixed: list[str] = field(default_factory=list)


def check_against_transcript(summary: MeetingSummary, transcript: str) -> list[str]:
    """Business rules the JSON schema cannot express. Returns a list of problems."""
    problems = []
    text = transcript.lower()
    for item in summary.action_items:
        if item.owner and item.owner.split()[0].lower() not in text:
            problems.append(
                f"Owner '{item.owner}' of task '{item.task}' does not appear in the transcript."
            )
        if not item.task.strip():
            problems.append("An action item has an empty task.")
    tasks = [i.task.strip().lower() for i in summary.action_items]
    if len(tasks) != len(set(tasks)):
        problems.append("The same action item is listed more than once.")
    return problems


def _user_message(transcript: str, problems: list[str]) -> str:
    msg = f"<transcript>\n{transcript.strip()}\n</transcript>"
    if problems:
        msg += (
            "\n\nA previous answer for this transcript was rejected for these reasons:\n- "
            + "\n- ".join(problems)
            + "\nFix them in your new answer."
        )
    return msg


def extract(transcript: str, settings: Settings, client: Any = None) -> ExtractionResult:
    if not transcript.strip():
        raise ValueError("Transcript is empty.")
    if client is None:
        api_key = require(settings.anthropic_api_key, "ANTHROPIC_API_KEY")
        client = anthropic.Anthropic(api_key=api_key)

    problems: list[str] = []
    seen_problems: list[str] = []
    tokens_in = tokens_out = 0

    for attempt in range(1, settings.max_attempts + 1):
        started = time.perf_counter()
        try:
            response = client.messages.parse(
                model=settings.extract_model,
                max_tokens=16000,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": _user_message(transcript, problems)}],
                output_config={"effort": settings.extract_effort},
                output_format=MeetingSummary,
            )
        except pydantic.ValidationError as exc:
            problems = [f"The JSON did not match the schema: {exc.errors()[:3]}"]
            log.warning("extract attempt=%d result=schema_error", attempt)
            seen_problems += problems
            continue

        usage = getattr(response, "usage", None)
        tokens_in += getattr(usage, "input_tokens", 0) or 0
        tokens_out += getattr(usage, "output_tokens", 0) or 0
        elapsed = time.perf_counter() - started

        if response.stop_reason == "refusal":
            raise ExtractionError("Claude declined to process this transcript.")
        if response.stop_reason == "max_tokens" or response.parsed_output is None:
            problems = ["The answer was cut off. Keep it shorter."]
            log.warning("extract attempt=%d result=truncated seconds=%.1f", attempt, elapsed)
            seen_problems += problems
            continue

        summary = response.parsed_output
        problems = check_against_transcript(summary, transcript)
        log.info(
            "extract attempt=%d model=%s seconds=%.1f input_tokens=%s output_tokens=%s "
            "actions=%d decisions=%d problems=%d",
            attempt,
            settings.extract_model,
            elapsed,
            tokens_in,
            tokens_out,
            len(summary.action_items),
            len(summary.decisions),
            len(problems),
        )
        if not problems:
            return ExtractionResult(summary, attempt, tokens_in, tokens_out, seen_problems)
        seen_problems += problems

    raise ExtractionError(
        f"No valid summary after {settings.max_attempts} attempts. Last problems: {problems}"
    )
