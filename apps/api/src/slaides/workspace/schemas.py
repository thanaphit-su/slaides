from __future__ import annotations

import uuid

from pydantic import BaseModel, Field


class LlmModelConfig(BaseModel):
    id: str = Field(min_length=1, max_length=200)
    supports_image_input: bool = False
    max_context_window: int | None = Field(default=None, ge=1)
    max_output_tokens: int | None = Field(default=None, ge=1)
    temperature: float | None = Field(default=None, ge=0, le=2)
    top_p: float | None = Field(default=None, ge=0, le=1)
    frequency_penalty: float | None = Field(default=None, ge=-2, le=2)
    presence_penalty: float | None = Field(default=None, ge=-2, le=2)


class WorkspaceOut(BaseModel):
    id: uuid.UUID
    name: str
    llm_base_url: str
    llm_model: str | None
    llm_caps: dict
    llm_models: list[LlmModelConfig] = Field(default_factory=list)
    llm_capability_models: dict[str, str | None] = Field(default_factory=dict)
    llm_key_configured: bool = False


class WorkspacePatch(BaseModel):
    llm_base_url: str | None = Field(default=None, max_length=500)
    llm_api_key: str | None = Field(default=None, max_length=2000)
    llm_model: str | None = Field(default=None, max_length=200)
    llm_caps: dict[str, bool] | None = None
    llm_models: list[LlmModelConfig] | None = None
    llm_capability_models: dict[str, str | None] | None = None
