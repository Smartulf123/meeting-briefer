"""Data shapes shared by the extractor, the briefing writer, the API and the evals."""

from pydantic import BaseModel, Field


class ActionItem(BaseModel):
    task: str = Field(description="What has to be done, as a short imperative sentence.")
    owner: str | None = Field(
        description="Name of the person responsible, exactly as written in the transcript. "
        "null if nobody clearly took or was given the task."
    )
    due: str | None = Field(
        description="Deadline as stated in the transcript (e.g. 'Friday', '15 March'). "
        "null if none was mentioned."
    )


class MeetingSummary(BaseModel):
    title: str = Field(description="A short title for the meeting, max 8 words.")
    summary: str = Field(description="One or two sentences on what the meeting was about.")
    decisions: list[str] = Field(description="Decisions that were actually agreed, not proposals.")
    action_items: list[ActionItem]
    open_questions: list[str] = Field(description="Questions raised but left unresolved.")
