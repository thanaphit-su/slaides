from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import TypeDecorator, CHAR

from .base import Base


class GUID(TypeDecorator):
    """UUID portable across Postgres (native) and SQLite (CHAR(36))."""

    impl = CHAR
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            from sqlalchemy.dialects.postgresql import UUID

            return dialect.type_descriptor(UUID(as_uuid=True))
        return dialect.type_descriptor(CHAR(36))

    def process_bind_param(self, value, dialect):
        if value is None:
            return value
        if dialect.name == "postgresql":
            return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))
        return str(value) if isinstance(value, uuid.UUID) else str(uuid.UUID(str(value)))

    def process_result_value(self, value, dialect):
        if value is None:
            return value
        return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))


def _uuid() -> uuid.UUID:
    return uuid.uuid4()


class Workspace(Base):
    __tablename__ = "workspace"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    llm_base_url: Mapped[str] = mapped_column(String(500), default="https://api.openai.com/v1")
    llm_key_enc: Mapped[bytes | None] = mapped_column(nullable=True)
    llm_model: Mapped[str | None] = mapped_column(String(200), default="gpt-4.1-mini")
    llm_models: Mapped[list] = mapped_column(JSON, default=list)
    llm_capability_models: Mapped[dict] = mapped_column(JSON, default=dict)
    log_llm_prompts_for_transcript: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AppUser(Base):
    __tablename__ = "app_user"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=_uuid)
    workspace_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("workspace.id"), nullable=False)
    supabase_user_id: Mapped[uuid.UUID | None] = mapped_column(GUID(), unique=True, nullable=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    role: Mapped[str] = mapped_column(String(40), default="instructor")
    approval_status: Mapped[str] = mapped_column(String(40), nullable=False, default="approved")
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Deck(Base):
    __tablename__ = "deck"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=_uuid)
    workspace_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("workspace.id"), nullable=False)
    owner_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("app_user.id"), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False, default="Untitled")
    subtitle: Mapped[str | None] = mapped_column(String(500), nullable=True)
    cover: Mapped[str | None] = mapped_column(String(120), nullable=True)
    manifest: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    sections: Mapped[list["Section"]] = relationship(
        back_populates="deck", cascade="all, delete-orphan", order_by="Section.position"
    )
    slides: Mapped[list["Slide"]] = relationship(
        back_populates="deck", cascade="all, delete-orphan", order_by="Slide.position"
    )


class Section(Base):
    __tablename__ = "section"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=_uuid)
    deck_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("deck.id", ondelete="CASCADE"), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    deck: Mapped[Deck] = relationship(back_populates="sections")

    __table_args__ = (Index("ix_section_deck_position", "deck_id", "position"),)


class Slide(Base):
    __tablename__ = "slide"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=_uuid)
    deck_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("deck.id", ondelete="CASCADE"), nullable=False)
    section_id: Mapped[uuid.UUID | None] = mapped_column(GUID(), ForeignKey("section.id"), nullable=True)
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    kicker: Mapped[str | None] = mapped_column(String(300), nullable=True)
    markdown: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    deck: Mapped[Deck] = relationship(back_populates="slides")

    __table_args__ = (Index("ix_slide_deck_position", "deck_id", "position"),)


class Widget(Base):
    __tablename__ = "widget"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=_uuid)
    # Widgets v2 — deck-local ownership. Widgets always belong to exactly one
    # deck; cross-deck reuse goes through an explicit copy that snapshots the
    # source. `derived_from_id` is a soft pointer (no FK cascade) for lineage.
    deck_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("deck.id", ondelete="CASCADE"), nullable=False)
    derived_from_id: Mapped[uuid.UUID | None] = mapped_column(GUID(), nullable=True)
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    kind: Mapped[str] = mapped_column(String(60), nullable=False)
    description: Mapped[str | None] = mapped_column(String(600), nullable=True)
    html: Mapped[str] = mapped_column(Text, nullable=False, default="")
    js: Mapped[str | None] = mapped_column(Text, nullable=True)
    css: Mapped[str | None] = mapped_column(Text, nullable=True)
    props_schema: Mapped[dict] = mapped_column(JSON, default=dict)
    tags: Mapped[dict] = mapped_column(JSON, default=list)  # JSON array, portable across PG/SQLite
    version: Mapped[str] = mapped_column(String(40), default="v0.1")
    behavior: Mapped[dict] = mapped_column(JSON, default=lambda: {"kind": "quiet"}, nullable=False)
    # Soft during migration backfill, then enforced by the 0015 migration in
    # Postgres. SQLite remains soft for test/dev because its batch table rebuild
    # path is fragile with legacy defaults. `use_alter` avoids a hard create
    # order cycle with `widget_revision.widget_id -> widget.id`.
    current_revision_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(),
        ForeignKey("widget_revision.id", use_alter=True, name="fk_widget_current_revision"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class WidgetRevision(Base):
    __tablename__ = "widget_revision"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=_uuid)
    widget_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("widget.id", ondelete="CASCADE"), nullable=False
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    html: Mapped[str] = mapped_column(Text, nullable=False, default="")
    js: Mapped[str | None] = mapped_column(Text, nullable=True)
    css: Mapped[str | None] = mapped_column(Text, nullable=True)
    props_schema: Mapped[dict] = mapped_column(JSON, default=dict)
    example_props: Mapped[dict] = mapped_column(JSON, default=dict)
    behavior: Mapped[dict] = mapped_column(JSON, default=lambda: {"kind": "quiet"}, nullable=False)
    ai_spec: Mapped[dict] = mapped_column(JSON, default=dict)
    created_reason: Mapped[str | None] = mapped_column(String(120), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint("widget_id", "version_number", name="uq_widget_revision_version"),
        Index("ix_widget_revision_widget", "widget_id", "version_number"),
    )


class WidgetAiThread(Base):
    __tablename__ = "widget_ai_thread"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=_uuid)
    widget_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("widget.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str | None] = mapped_column(String(200), nullable=True)
    compact_summary: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class WidgetAiMessage(Base):
    __tablename__ = "widget_ai_message"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=_uuid)
    thread_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("widget_ai_thread.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[str] = mapped_column(String(30), nullable=False)
    message_type: Mapped[str] = mapped_column(String(30), nullable=False)
    content: Mapped[dict] = mapped_column(JSON, default=dict)
    revision_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("widget_revision.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (Index("ix_widget_ai_message_thread_created", "thread_id", "created_at"),)


class SlideWidget(Base):
    __tablename__ = "slide_widget"

    slide_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("slide.id", ondelete="CASCADE"), primary_key=True
    )
    placement_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    widget_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("widget.id"), nullable=False)
    revision_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("widget_revision.id"), nullable=True
    )
    props: Mapped[dict] = mapped_column(JSON, default=dict)
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class Session(Base):
    __tablename__ = "session"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=_uuid)
    deck_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("deck.id"), nullable=False)
    owner_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("app_user.id"), nullable=False)
    workspace_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("workspace.id"), nullable=False)
    code: Mapped[str] = mapped_column(String(40), nullable=False, unique=True)
    salt: Mapped[str] = mapped_column(String(64), nullable=False)
    # NB: no FK — can hold a deck slide.id OR a session_slide.id (FAB-inserted interaction slide).
    current_slide_id: Mapped[uuid.UUID | None] = mapped_column(GUID(), nullable=True)
    config: Mapped[dict] = mapped_column(JSON, default=dict)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_preview: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    __table_args__ = (Index("ix_session_workspace", "workspace_id"),)


class Participant(Base):
    __tablename__ = "participant"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=_uuid)
    session_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("session.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[uuid.UUID | None] = mapped_column(GUID(), ForeignKey("app_user.id"), nullable=True)
    email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    display_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    anon: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    ref: Mapped[str] = mapped_column(String(64), nullable=False)
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    left_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        UniqueConstraint("session_id", "ref", name="uq_participant_session_ref"),
        Index("ix_participant_session", "session_id"),
    )


class Question(Base):
    __tablename__ = "question"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=_uuid)
    session_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("session.id", ondelete="CASCADE"), nullable=False)
    slide_id: Mapped[uuid.UUID | None] = mapped_column(GUID(), ForeignKey("slide.id"), nullable=True)
    participant_ref: Mapped[str] = mapped_column(String(64), nullable=False)
    anon: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    raised_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    answered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (Index("ix_question_session", "session_id", "raised_at"),)


class InteractionLog(Base):
    __tablename__ = "interaction_log"

    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer(), "sqlite"), primary_key=True, autoincrement=True)
    session_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("session.id", ondelete="CASCADE"), nullable=False)
    slide_id: Mapped[uuid.UUID | None] = mapped_column(GUID(), ForeignKey("slide.id"), nullable=True)
    session_slide_id: Mapped[uuid.UUID | None] = mapped_column(GUID(), ForeignKey("session_slide.id"), nullable=True)
    widget_id: Mapped[uuid.UUID | None] = mapped_column(GUID(), ForeignKey("widget.id"), nullable=True)
    participant_ref: Mapped[str] = mapped_column(String(64), nullable=False)
    kind: Mapped[str] = mapped_column(String(60), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("ix_log_session", "session_id", "occurred_at"),
        Index("ix_log_widget", "widget_id"),
        Index("ix_log_session_slide", "session_slide_id"),
    )


class SessionEvent(Base):
    __tablename__ = "session_event"

    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer(), "sqlite"), primary_key=True, autoincrement=True)
    session_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("session.id", ondelete="CASCADE"), nullable=False)
    event_type: Mapped[str] = mapped_column(String(60), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        Index("ix_session_event_session", "session_id", "occurred_at"),
        Index("ix_session_event_type", "session_id", "event_type"),
    )


class SessionSlide(Base):
    __tablename__ = "session_slide"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=_uuid)
    session_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("session.id", ondelete="CASCADE"), nullable=False)
    parent_slide_id: Mapped[uuid.UUID | None] = mapped_column(GUID(), ForeignKey("slide.id"), nullable=True)
    widget_id: Mapped[uuid.UUID | None] = mapped_column(GUID(), ForeignKey("widget.id"), nullable=True)
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    kind: Mapped[str] = mapped_column(String(60), nullable=False)
    spec: Mapped[dict] = mapped_column(JSON, default=dict)
    results: Mapped[dict] = mapped_column(JSON, default=dict)
    inverted_theme: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (Index("ix_session_slide_session", "session_id", "position"),)


class PlacementState(Base):
    """Widgets v2 Step 4 — per-(session, placement) aggregated state for
    Loud widgets. `placement_id` is the `slide_widget.placement_id` string
    for AI-generated widgets, or the `session_slide.id` (stringified) for
    native polls/questions that share the unified protocol.

    Rows are frozen after `closed_at` is set (or the parent session ends).
    The transcript view rebuilds the audience-visible projection by reading
    `state` directly; the raw contributions live on in `interaction_log`.
    """

    __tablename__ = "placement_state"

    session_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("session.id", ondelete="CASCADE"), primary_key=True
    )
    placement_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    widget_id: Mapped[uuid.UUID | None] = mapped_column(GUID(), nullable=True)
    aggregator: Mapped[str] = mapped_column(String(40), nullable=False)
    state: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    contribution_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    state_version: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (Index("ix_placement_state_session", "session_id"),)


class LlmCall(Base):
    __tablename__ = "llm_call"

    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer(), "sqlite"), primary_key=True, autoincrement=True)
    workspace_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("workspace.id"), nullable=False)
    user_id: Mapped[uuid.UUID | None] = mapped_column(GUID(), ForeignKey("app_user.id"), nullable=True)
    session_id: Mapped[uuid.UUID | None] = mapped_column(GUID(), ForeignKey("session.id"), nullable=True)
    purpose: Mapped[str] = mapped_column(String(60), nullable=False)
    model: Mapped[str | None] = mapped_column(String(200), nullable=True)
    prompt_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    prompt_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tokens_in: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tokens_out: Mapped[int | None] = mapped_column(Integer, nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (Index("ix_llm_call_workspace", "workspace_id", "occurred_at"),)
