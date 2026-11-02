"""Domain ORM models (PostgreSQL 16 + pgvector).

Mirrors the ER model in the design document, chapter 3.3 / 8.1.
The vector column uses a plain ``Vector`` type via pgvector's SQLAlchemy
extension; the HNSW index is created by the SQL migration script.

Author: Wang, Bing <colin2wang@gmail.com>
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    Text,
    TypeDecorator,
    Uuid,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

try:  # pgvector is optional at import time (tests may run without a DB)
    from pgvector.sqlalchemy import Vector
except ImportError:  # pragma: no cover
    Vector = None  # type: ignore[assignment]

EMBEDDING_DIMS = 1024


class Guid(TypeDecorator):
    """Cross-dialect UUID column: native UUID on PostgreSQL, CHAR(32) on SQLite.

    Accepts both ``uuid.UUID`` and plain strings, so route handlers can pass
    path parameters straight through without manual coercion.
    """

    impl = Uuid
    cache_ok = True

    def process_bind_param(self, value: object, dialect: object) -> object:
        if value is None or isinstance(value, uuid.UUID):
            return value
        return uuid.UUID(str(value))


class Base(DeclarativeBase):
    """Declarative base for all EEP domain tables."""


def _pk() -> Mapped[uuid.UUID]:
    return mapped_column(Guid(), primary_key=True, default=uuid.uuid4)


class Project(Base):
    __tablename__ = "project"

    id: Mapped[uuid.UUID] = _pk()
    name: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class User(Base):
    __tablename__ = "user"

    id: Mapped[uuid.UUID] = _pk()
    name: Mapped[str] = mapped_column(Text, nullable=False)
    avatar: Mapped[str | None] = mapped_column(Text)


class Meeting(Base):
    """Meeting record with transcript, review state and cached statistics."""

    __tablename__ = "meeting"

    id: Mapped[uuid.UUID] = _pk()
    project_id: Mapped[uuid.UUID] = mapped_column(
        Guid(), ForeignKey("project.id"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)  # keeps "transcript_" prefix
    meet_date: Mapped[date | None] = mapped_column(Date)
    participants: Mapped[list[Any]] = mapped_column(JSONB, default=list)
    source_type: Mapped[str] = mapped_column(Text, default="upload")  # upload|transcript|api
    transcript_uri: Mapped[str | None] = mapped_column(Text)
    summary: Mapped[str | None] = mapped_column(Text)
    discussion: Mapped[str | None] = mapped_column(Text)
    review_status: Mapped[str] = mapped_column(
        Text, default="pending"
    )  # pending | reviewed  (待审核 | 已审核入库)
    exp_stat_cache: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    pipeline_version: Mapped[str] = mapped_column(Text, default="v1")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Experience(Base):
    """Formal experience unit (five types) with dual timeline fields."""

    __tablename__ = "experience"

    id: Mapped[uuid.UUID] = _pk()
    project_id: Mapped[uuid.UUID] = mapped_column(
        Guid(), ForeignKey("project.id"), nullable=False, index=True
    )
    code: Mapped[str | None] = mapped_column(Text, unique=True)  # e.g. action-114
    type: Mapped[str] = mapped_column(Text, nullable=False)  # question|hypothesis|experiment|decision|action
    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, default="pending")
    owner_id: Mapped[uuid.UUID | None] = mapped_column(Guid(), ForeignKey("user.id"))
    due_date: Mapped[date | None] = mapped_column(Date)
    acceptance_criteria: Mapped[str | None] = mapped_column(Text)
    source_meeting_id: Mapped[uuid.UUID | None] = mapped_column(Guid())
    source_span: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    t_event: Mapped[date | None] = mapped_column(Date)
    t_invalid: Mapped[date | None] = mapped_column(Date)
    superseded_by: Mapped[uuid.UUID | None] = mapped_column(Guid())
    # Vector column on PostgreSQL (pgvector HNSW); plain TEXT on SQLite so the
    # default dev database auto-initializes without the pgvector extension.
    embedding: Mapped[Any] = (
        mapped_column(Vector(EMBEDDING_DIMS).with_variant(Text, "sqlite"))
        if Vector is not None
        else mapped_column(Text, nullable=True)
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Extraction(Base):
    """AI draft extraction awaiting human review (one per meeting run)."""

    __tablename__ = "extraction"

    id: Mapped[uuid.UUID] = _pk()
    meeting_id: Mapped[uuid.UUID] = mapped_column(
        Guid(), ForeignKey("meeting.id"), nullable=False, index=True
    )
    draft_json: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    model_ver: Mapped[str | None] = mapped_column(Text)
    confidence: Mapped[float | None] = mapped_column(Float)
    review_status: Mapped[str] = mapped_column(Text, default="pending")  # pending|accepted|rejected
    reviewer_id: Mapped[uuid.UUID | None] = mapped_column(Guid())
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        # Idempotency key: one pipeline run per (meeting, pipeline version).
        # Enforced in SQL migration; kept here for documentation parity.
    )


class ExpMeeting(Base):
    """Experience-to-meeting evidence link (meeting basis)."""

    __tablename__ = "exp_meeting"

    exp_id: Mapped[uuid.UUID] = mapped_column(
        Guid(), ForeignKey("experience.id"), primary_key=True
    )
    meeting_id: Mapped[uuid.UUID] = mapped_column(
        Guid(), ForeignKey("meeting.id"), primary_key=True
    )
    evidence_span: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    is_first_record: Mapped[bool] = mapped_column(Boolean, default=False)


class Relation(Base):
    """Evolution-chain edge table (Phase 1; Graphiti in Phase 2)."""

    __tablename__ = "relation"

    id: Mapped[uuid.UUID] = _pk()
    from_exp: Mapped[uuid.UUID] = mapped_column(
        Guid(), ForeignKey("experience.id"), nullable=False, index=True
    )
    to_exp: Mapped[uuid.UUID] = mapped_column(
        Guid(), ForeignKey("experience.id"), nullable=False, index=True
    )
    rel_type: Mapped[str] = mapped_column(Text, nullable=False)  # evolves|supports|grounds|conflicts|suspected_duplicate
    origin: Mapped[str] = mapped_column(Text, default="AI")  # manual|AI
    confidence: Mapped[float | None] = mapped_column(Float)
    meeting_id: Mapped[uuid.UUID | None] = mapped_column(Guid())


class ChangeLog(Base):
    """Append-only field-level audit trail (INSERT only; enforced by trigger)."""

    __tablename__ = "change_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    entity_type: Mapped[str] = mapped_column(Text, nullable=False)
    entity_id: Mapped[uuid.UUID | None] = mapped_column(Guid())
    field: Mapped[str] = mapped_column(Text, nullable=False)
    old_value: Mapped[str | None] = mapped_column(Text)
    new_value: Mapped[str | None] = mapped_column(Text)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(Guid())
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    source: Mapped[str] = mapped_column(Text, default="ui")  # ui | background-sync


class Integration(Base):
    """Connected external service registration."""

    __tablename__ = "integration"

    id: Mapped[uuid.UUID] = _pk()
    name: Mapped[str] = mapped_column(Text, nullable=False)
    scope: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, default="connected")
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AIProvider(Base):
    """Registered AI provider with breaker state, for the health dashboard."""

    __tablename__ = "ai_provider"

    id: Mapped[uuid.UUID] = _pk()
    name: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    type: Mapped[str] = mapped_column(Text, nullable=False)
    base_url: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, default="unknown")
    breaker_state: Mapped[str] = mapped_column(Text, default="closed")
    last_probe_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
