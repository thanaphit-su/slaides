from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ..decks.schemas import SectionOut, SlideOut, SlideWidgetEmbed
from ..workspace.schemas import InterpretQuickOption


class SessionCreate(BaseModel):
    deck_id: uuid.UUID


class SessionAdvance(BaseModel):
    slide_id: uuid.UUID
    is_session_slide: bool = False


class SessionSlideOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    session_id: uuid.UUID
    parent_slide_id: uuid.UUID | None
    widget_id: uuid.UUID | None
    position: int
    kind: str
    spec: dict
    results: dict
    inverted_theme: bool
    opened_at: datetime
    closed_at: datetime | None


class ParticipantOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    display_name: str | None
    anon: bool
    ref: str
    joined_at: datetime
    left_at: datetime | None


class QuestionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    slide_id: uuid.UUID | None
    participant_ref: str
    anon: bool
    text: str
    raised_at: datetime
    answered_at: datetime | None


class SessionListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    deck_id: uuid.UUID
    code: str
    started_at: datetime
    ended_at: datetime | None
    deck_title: str = ""
    participant_count: int = 0
    interaction_count: int = 0


class SessionPublic(BaseModel):
    """Pre-auth peek by code — minimal info so the join flow can show deck title."""

    id: uuid.UUID
    code: str
    deck_title: str
    started_at: datetime
    ended_at: datetime | None


class PlacementStateOut(BaseModel):
    """Widgets v2 Step 4 — late-joiner snapshot entry for a Loud iframe widget.
    Mirrors the `widget.state` broadcast shape so the audience can use one
    handler for both the snapshot reads and the live event."""

    placement_id: str
    widget_id: uuid.UUID | None = None
    aggregator: str
    state: dict
    state_version: int
    closed: bool


class SessionSnapshot(BaseModel):
    id: uuid.UUID
    code: str
    deck_id: uuid.UUID
    deck_title: str
    owner_id: uuid.UUID
    started_at: datetime
    ended_at: datetime | None
    current_slide_id: uuid.UUID | None
    sections: list[SectionOut]
    slides: list[SlideOut]
    session_slides: list[SessionSlideOut]
    questions: list[QuestionOut]
    audience_count: int
    interpret_quick_options: list[InterpretQuickOption] = Field(default_factory=list)
    placement_states: list[PlacementStateOut] = []


class MirrorSlideOut(BaseModel):
    id: uuid.UUID
    deck_id: uuid.UUID
    section_id: uuid.UUID | None
    position: int
    kicker: str | None
    markdown: str
    updated_at: datetime
    widgets: list[SlideWidgetEmbed] = Field(default_factory=list)


class MirrorSessionSnapshot(BaseModel):
    id: uuid.UUID
    deck_id: uuid.UUID
    deck_title: str
    started_at: datetime
    ended_at: datetime | None
    current_slide_id: uuid.UUID | None
    sections: list[SectionOut]
    slides: list[MirrorSlideOut]
    session_slides: list[SessionSlideOut]
    placement_states: list[PlacementStateOut] = Field(default_factory=list)


class MirrorLinkOut(BaseModel):
    url: str
    token: str | None = None
    access_mode: Literal["owner", "allowed", "link"]


class PreviewSessionRequest(BaseModel):
    """Spin up a throwaway session + N fake guests for the editor's preview tab.

    The instructor clicks "Preview" in the editor and we mint a real session
    plus N pre-authenticated guests so the same code path the audience hits in
    production runs in the preview tab — no client-side aggregator mirror to
    drift from the Python implementation.
    """

    deck_id: uuid.UUID
    audience_count: int = Field(default=3, ge=1, le=5)


class PreviewFakeGuest(BaseModel):
    participant_id: uuid.UUID
    participant_ref: str
    display_name: str
    token: str


class PreviewSessionResponse(BaseModel):
    session_id: uuid.UUID
    code: str
    fake_guests: list[PreviewFakeGuest]


class OpenInteractionRequest(BaseModel):
    kind: str  # 'poll' | 'question' | 'widget'
    parent_slide_id: uuid.UUID | None = None
    widget_id: uuid.UUID | None = None
    spec: dict = {}
    inverted_theme: bool = False


# ---- Live interaction spec/result shapes (kind = 'poll' or 'question') ----
#
# spec is persisted as JSON on session_slide.spec; results on session_slide.results.
# We validate at the boundary (in the router) using these models, then drop back
# to plain dicts for storage.


class PollChoice(BaseModel):
    id: str = Field(..., min_length=1, max_length=40)
    label: str = Field(..., min_length=1, max_length=200)


class PollConfig(BaseModel):
    allow_other: bool = False
    show_results_live: bool = True
    anonymous: bool = True


class PollState(BaseModel):
    voting_closed: bool = False
    choices_locked: bool = False


class PollSpec(BaseModel):
    type: Literal["poll"]
    question: str = Field(..., min_length=1, max_length=500)
    choices: list[PollChoice] = Field(..., min_length=2, max_length=12)
    config: PollConfig = Field(default_factory=PollConfig)
    state: PollState = Field(default_factory=PollState)

    @field_validator("choices")
    @classmethod
    def _unique_choice_ids(cls, choices: list[PollChoice]) -> list[PollChoice]:
        seen: set[str] = set()
        for c in choices:
            if c.id in seen:
                raise ValueError(f"duplicate choice id: {c.id}")
            seen.add(c.id)
        return choices


class QuestionConfig(BaseModel):
    anonymous: bool = True


class QuestionSpec(BaseModel):
    type: Literal["question"]
    prompt: str = Field(..., min_length=1, max_length=500)
    config: QuestionConfig = Field(default_factory=QuestionConfig)


class RandomAudienceSpec(BaseModel):
    type: Literal["random"]
    count: int = Field(default=1, ge=1, le=50)


class PromotedAnswer(BaseModel):
    id: str
    text: str
    display_name: str | None = None
    anon: bool = True


class InteractionPatch(BaseModel):
    """Partial update of a live interaction's spec. Only top-level fields here.

    For polls, `choices` is only accepted while no vote has landed (server
    enforces). For both kinds, `question` / `prompt` and `config` can be edited
    at any time; `state` is updated via dedicated verbs (close/reopen/lock).
    """

    question: str | None = Field(default=None, max_length=500)
    prompt: str | None = Field(default=None, max_length=500)
    choices: list[PollChoice] | None = Field(default=None, min_length=2, max_length=12)
    config: dict | None = None


class OpenAnswerOut(BaseModel):
    """A single open-question answer surfaced to the presenter's moderation rail."""

    id: int  # interaction_log.id
    text: str
    participant_ref: str
    display_name: str | None = None
    anon: bool = True
    occurred_at: datetime
    promoted: bool = False
