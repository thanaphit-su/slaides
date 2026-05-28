from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class SlideWidgetRevisionEmbed(BaseModel):
    id: uuid.UUID
    widget_id: uuid.UUID
    version_number: int
    html: str
    js: str | None
    css: str | None
    props_schema: dict
    example_props: dict
    behavior: dict
    ai_spec: dict
    created_reason: str | None = None


class SlideWidgetEmbed(BaseModel):
    placement_id: str
    widget_id: uuid.UUID
    revision_id: uuid.UUID | None = None
    revision: SlideWidgetRevisionEmbed | None = None
    kind: str
    name: str
    props: dict


class SlideOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    deck_id: uuid.UUID
    section_id: uuid.UUID | None
    position: int
    kicker: str | None
    markdown: str
    updated_at: datetime
    widgets: list[SlideWidgetEmbed] = []


class SectionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    position: int


class SectionCreate(BaseModel):
    title: str
    position: int | None = None


class SectionPatch(BaseModel):
    title: str | None = None
    position: int | None = None


class SectionReorder(BaseModel):
    order: list[uuid.UUID]


class SlideReorderEntry(BaseModel):
    id: uuid.UUID
    section_id: uuid.UUID | None = None


class SlideReorder(BaseModel):
    order: list[SlideReorderEntry]


class DeckListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    subtitle: str | None
    cover: str | None
    updated_at: datetime
    slide_count: int
    preview_kicker: str | None = None
    preview_markdown: str | None = None


class DeckOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    subtitle: str | None
    cover: str | None
    manifest: dict
    created_at: datetime
    updated_at: datetime
    sections: list[SectionOut]
    slides: list[SlideOut]


class DeckCreate(BaseModel):
    title: str | None = None
    subtitle: str | None = None


class DeckPatch(BaseModel):
    title: str | None = None
    subtitle: str | None = None
    cover: str | None = None
    manifest: dict | None = None


class SlideCreate(BaseModel):
    position: int | None = None
    markdown: str = ""
    kicker: str | None = None
    section_id: uuid.UUID | None = None


class SlideUpdate(BaseModel):
    markdown: str
    kicker: str | None = None


class SlideMutationResult(BaseModel):
    """Returned when an update may have split a slide into multiple."""

    slides: list[SlideOut]
