"""Pydantic schemas: API payloads + extraction output contract (Appendix A).

Author: Wang, Bing <colin2wang@gmail.com>
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

ExperienceType = Literal["question", "hypothesis", "experiment", "decision", "action"]
ExperienceStatus = Literal[
    "pending", "in_progress", "planned", "effective", "invalid", "completed"
]
RelationType = Literal["evolves", "supports", "grounds", "conflicts", "suspected_duplicate"]
ReviewDecision = Literal["accept", "accept_edited", "reject"]


# --------------------------------------------------------------------- #
# Extraction contract (design doc, Appendix A)
# --------------------------------------------------------------------- #
class SourceSpan(BaseModel):
    """Character span + verbatim quote into the meeting transcript."""

    start: int
    end: int
    quote: str


class ExtractedItem(BaseModel):
    """One experience candidate produced by the extractor node."""

    type: ExperienceType
    title: str = Field(max_length=60)
    description: str | None = None
    owner_hint: str | None = None
    due_hint: str | None = None
    acceptance_criteria: str | None = None
    source_span: SourceSpan
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)


class ExtractionOutput(BaseModel):
    """Strict schema for the extractor LLM response."""

    items: list[ExtractedItem] = Field(default_factory=list)


# --------------------------------------------------------------------- #
# Meeting payloads
# --------------------------------------------------------------------- #
class MeetingCreate(BaseModel):
    """Transcript push (upload or API integration) triggering the G1 graph."""

    title: str
    meet_date: date | None = None
    participants: list[str] = Field(default_factory=list)
    source_type: Literal["upload", "transcript", "api"] = "api"
    transcript_text: str  # full transcript body
    pipeline_version: str = "v1"


class MeetingOut(BaseModel):
    id: str
    title: str
    meet_date: date | None = None
    participants: list[str] = Field(default_factory=list)
    review_status: str
    exp_stat_cache: dict = Field(default_factory=dict)


class MeetingDetailOut(MeetingOut):
    summary: str | None = None
    discussion: str | None = None
    related_experiences: list["ExperienceOutLite"] = Field(default_factory=list)


# --------------------------------------------------------------------- #
# Experience payloads
# --------------------------------------------------------------------- #
class ExperienceOutLite(BaseModel):
    """Minimal experience card (used inside meeting detail / chain cards)."""

    id: str
    code: str | None = None
    type: ExperienceType
    title: str
    status: str
    description: str | None = None
    source_meeting_id: str | None = None


class ExperienceOut(BaseModel):
    id: str
    code: str | None = None
    type: ExperienceType
    title: str
    description: str | None = None
    status: str
    owner_id: str | None = None
    owner_name: str | None = None
    due_date: date | None = None
    acceptance_criteria: str | None = None
    source_meeting_id: str | None = None
    source_span: dict = Field(default_factory=dict)
    updated_at: datetime | None = None


class ExperiencePatch(BaseModel):
    """Editable fields; every changed field is written to change_log."""

    title: str | None = None
    description: str | None = None
    status: ExperienceStatus | None = None
    owner_id: str | None = None
    due_date: date | None = None
    acceptance_criteria: str | None = None


class ReviewSubmit(BaseModel):
    """Human verdict resuming the interrupted G2 review graph."""

    decision: ReviewDecision
    reviewer_id: str | None = None
    reason: str | None = None  # required when decision == reject
    edited: ExtractedItem | None = None  # required when decision == accept_edited


# --------------------------------------------------------------------- #
# Chain / overview payloads
# --------------------------------------------------------------------- #
class ChainCard(BaseModel):
    experience: ExperienceOut
    meeting_date: date | None = None
    evidence_span: dict = Field(default_factory=dict)


class Swimlane(BaseModel):
    type: ExperienceType
    cards: list[ChainCard] = Field(default_factory=list)
    placeholder: str = ""


class ChainOut(BaseModel):
    topic: str
    time_span: list[date | None] = Field(default_factory=list)
    relation_count: int = 0
    lanes: list[Swimlane] = Field(default_factory=list)
    disclaimer: str = (
        "Related items do not automatically imply causation or completed verification."
    )


class OverviewOut(BaseModel):
    metrics: dict = Field(default_factory=dict)
    attention_list: list[ExperienceOut] = Field(default_factory=list)
    pilots: list[ExperienceOut] = Field(default_factory=list)
    decision_quotes: list[ExperienceOut] = Field(default_factory=list)


# --------------------------------------------------------------------- #
# AI provider health
# --------------------------------------------------------------------- #
class ProviderHealthOut(BaseModel):
    provider: str
    status: str
    models: list[str] = Field(default_factory=list)
    chat_model_ready: bool = False
    breaker_state: str = "closed"
    detail: str = ""


MeetingDetailOut.model_rebuild()
