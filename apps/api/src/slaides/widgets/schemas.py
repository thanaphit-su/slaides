from __future__ import annotations

import uuid

from pydantic import BaseModel, ConfigDict, Field


class WidgetOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    deck_id: uuid.UUID
    derived_from_id: uuid.UUID | None = None
    name: str
    kind: str
    description: str | None
    html: str
    js: str | None
    css: str | None
    props_schema: dict
    tags: list[str]
    version: str
    behavior: dict = Field(default_factory=lambda: {"kind": "quiet"})
    current_revision_id: uuid.UUID | None = None
    example_props: dict = Field(default_factory=dict)
    ai_spec: dict = Field(default_factory=dict)


class WidgetSummary(BaseModel):
    """Lightweight shape for library listings."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    deck_id: uuid.UUID
    derived_from_id: uuid.UUID | None = None
    name: str
    kind: str
    description: str | None
    tags: list[str]
    version: str
    behavior: dict = Field(default_factory=lambda: {"kind": "quiet"})


class WidgetCreate(BaseModel):
    name: str
    kind: str
    description: str | None = None
    html: str = ""
    js: str | None = None
    css: str | None = None
    props_schema: dict = {}
    example_props: dict = Field(default_factory=dict)
    ai_spec: dict = Field(default_factory=dict)
    tags: list[str] = []
    behavior: dict | None = None


class WidgetPatch(BaseModel):
    name: str | None = None
    kind: str | None = None
    description: str | None = None
    html: str | None = None
    js: str | None = None
    css: str | None = None
    props_schema: dict | None = None
    example_props: dict | None = None
    ai_spec: dict | None = None
    tags: list[str] | None = None
    behavior: dict | None = None


class WidgetRevisionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

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


class SlideWidgetRevisionOut(BaseModel):
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


class WidgetAiThreadCreate(BaseModel):
    title: str | None = None
    compact_summary: dict = Field(default_factory=dict)


class WidgetAiMessageCreate(BaseModel):
    role: str
    message_type: str
    content: dict = Field(default_factory=dict)
    revision_id: uuid.UUID | None = None


class WidgetAiMessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    thread_id: uuid.UUID
    role: str
    message_type: str
    content: dict
    revision_id: uuid.UUID | None = None


class WidgetAiThreadOut(BaseModel):
    id: uuid.UUID
    widget_id: uuid.UUID
    title: str | None = None
    compact_summary: dict
    messages: list[WidgetAiMessageOut] = Field(default_factory=list)


class WidgetCopyRequest(BaseModel):
    """Copy a widget from another deck into the URL's target deck. The new
    row keeps `derived_from_id` pointing at the source for informational
    lineage — never enforces cascade or propagation."""

    source_widget_id: uuid.UUID


class SlideWidgetOut(BaseModel):
    placement_id: str
    widget_id: uuid.UUID
    revision_id: uuid.UUID | None = None
    revision: SlideWidgetRevisionOut | None = None
    kind: str
    name: str
    props: dict
    position: int


class SlideWidgetCreate(BaseModel):
    placement_id: str
    widget_id: uuid.UUID
    props: dict = {}


class SlideWidgetPatch(BaseModel):
    """Edit a placement's per-instance props. Validated against the widget's
    props_schema before being persisted."""

    props: dict
