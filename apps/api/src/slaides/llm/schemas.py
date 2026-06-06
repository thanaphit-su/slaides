from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

LlmPurpose = Literal["inline_write", "interpret", "widget_generate", "summarise"]


class LlmImageInput(BaseModel):
    data_url: str = Field(min_length=1, max_length=8_000_000)
    name: str | None = Field(default=None, max_length=200)
    mime_type: str | None = Field(default=None, max_length=80)


class LlmFileInput(BaseModel):
    content: str = Field(min_length=1, max_length=200_000)
    name: str | None = Field(default=None, max_length=200)
    mime_type: str | None = Field(default=None, max_length=80)


class LlmCompleteRequest(BaseModel):
    purpose: LlmPurpose
    prompt: str = Field(min_length=1, max_length=12000)
    context: dict = Field(default_factory=dict)
    model_override: str | None = Field(default=None, max_length=200)
    images: list[LlmImageInput] = Field(default_factory=list, max_length=6)
    files: list[LlmFileInput] = Field(default_factory=list, max_length=6)
