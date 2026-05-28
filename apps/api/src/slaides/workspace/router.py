from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from ..auth.deps import current_user
from ..db.deps import db_session
from ..db.models import AppUser, Workspace
from ..llm.crypto import encrypt_workspace_secret
from .schemas import LlmModelConfig, WorkspaceOut, WorkspacePatch

router = APIRouter(prefix="/workspace", tags=["workspace"])

DEFAULT_LLM_CAPS = {
    "inline_write": True,
    "interpret": True,
    "widget_generate": True,
}


def _clean_model_id(model_id: str | None) -> str:
    model = (model_id or "gpt-4.1-mini").strip()
    if not model:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="LLM model is required")
    return model


def _normalise_models(ws: Workspace) -> list[LlmModelConfig]:
    raw_models = ws.llm_models if isinstance(ws.llm_models, list) else []
    models: list[LlmModelConfig] = []
    seen: set[str] = set()
    for raw in raw_models:
        if not isinstance(raw, dict):
            continue
        try:
            model = LlmModelConfig.model_validate(raw)
        except Exception:
            continue
        model_id = model.id.strip()
        if not model_id or model_id in seen:
            continue
        models.append(model.model_copy(update={"id": model_id}))
        seen.add(model_id)

    fallback_id = _clean_model_id(ws.llm_model)
    if fallback_id not in seen:
        models.insert(0, LlmModelConfig(id=fallback_id))
    return models


def _normalise_capability_models(ws: Workspace, models: list[LlmModelConfig]) -> dict[str, str | None]:
    model_ids = {m.id for m in models}
    fallback = _clean_model_id(ws.llm_model)
    if fallback not in model_ids:
        fallback = models[0].id if models else "gpt-4.1-mini"
    raw_assignments = ws.llm_capability_models if isinstance(ws.llm_capability_models, dict) else {}
    result: dict[str, str | None] = {}
    for key in DEFAULT_LLM_CAPS:
        if key in raw_assignments and raw_assignments[key] is None:
            # Explicitly disabled.
            result[key] = None
            continue
        assigned = raw_assignments.get(key)
        result[key] = assigned if isinstance(assigned, str) and assigned in model_ids else fallback
    return result


def _caps_from_assignments(assignments: dict[str, str | None]) -> dict[str, bool]:
    return {key: assignments.get(key) is not None for key in DEFAULT_LLM_CAPS}


def _workspace_out(ws: Workspace) -> WorkspaceOut:
    models = _normalise_models(ws)
    capability_models = _normalise_capability_models(ws, models)
    return WorkspaceOut(
        id=ws.id,
        name=ws.name,
        llm_base_url=ws.llm_base_url,
        llm_model=ws.llm_model,
        llm_caps=_caps_from_assignments(capability_models),
        llm_models=models,
        llm_capability_models=capability_models,
        llm_key_configured=bool(ws.llm_key_enc),
        log_llm_prompts_for_transcript=ws.log_llm_prompts_for_transcript,
    )


@router.get("", response_model=WorkspaceOut)
async def get_workspace(
    user: AppUser = Depends(current_user),
    session: AsyncSession = Depends(db_session),
) -> WorkspaceOut:
    ws = (
        await session.execute(select(Workspace).where(Workspace.id == user.workspace_id))
    ).scalar_one_or_none()
    if ws is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="workspace missing")
    return _workspace_out(ws)


@router.patch("", response_model=WorkspaceOut)
async def patch_workspace(
    body: WorkspacePatch,
    user: AppUser = Depends(current_user),
    session: AsyncSession = Depends(db_session),
) -> WorkspaceOut:
    ws = (
        await session.execute(select(Workspace).where(Workspace.id == user.workspace_id))
    ).scalar_one_or_none()
    if ws is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="workspace missing")

    if body.llm_base_url is not None:
        base = body.llm_base_url.strip().rstrip("/")
        if not base.startswith(("http://", "https://")):
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="invalid LLM base URL")
        ws.llm_base_url = base

    if body.llm_model is not None:
        ws.llm_model = _clean_model_id(body.llm_model)

    if body.llm_models is not None:
        new_models: list[dict] = []
        seen: set[str] = set()
        for model in body.llm_models:
            model_id = _clean_model_id(model.id)
            if model_id in seen:
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"duplicate LLM model: {model_id}")
            seen.add(model_id)
            new_models.append(model.model_copy(update={"id": model_id}).model_dump(exclude_none=True))
        if not new_models:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="at least one LLM model is required")
        ws.llm_models = new_models
        flag_modified(ws, "llm_models")
        if ws.llm_model not in seen:
            ws.llm_model = new_models[0]["id"]

    assignments = dict(ws.llm_capability_models or {})

    if body.llm_caps is not None:
        # Booleans flip the capability map entry between an assigned model
        # (or fallback) and explicit None. We need the current model id set
        # to validate fallbacks.
        models_after_update = _normalise_models(ws)
        model_ids = {m.id for m in models_after_update}
        fallback = _clean_model_id(ws.llm_model)
        if fallback not in model_ids:
            fallback = models_after_update[0].id if models_after_update else fallback
        for key, value in body.llm_caps.items():
            if key not in DEFAULT_LLM_CAPS:
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"unknown LLM capability: {key}")
            if value:
                # Re-enable: keep any existing assignment, else use fallback.
                if assignments.get(key) is None:
                    assignments[key] = fallback
            else:
                assignments[key] = None

    if body.llm_capability_models is not None:
        models_after_update = _normalise_models(ws)
        model_ids = {m.id for m in models_after_update}
        for key, model_id in body.llm_capability_models.items():
            if key not in DEFAULT_LLM_CAPS:
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"unknown LLM capability: {key}")
            if model_id is None or model_id == "":
                assignments[key] = None
                continue
            if model_id not in model_ids:
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"unknown LLM model: {model_id}")
            assignments[key] = model_id

    ws.llm_capability_models = assignments
    flag_modified(ws, "llm_capability_models")

    if body.llm_api_key is not None:
        key = body.llm_api_key.strip()
        ws.llm_key_enc = encrypt_workspace_secret(ws.id, key) if key else None

    if body.log_llm_prompts_for_transcript is not None:
        ws.log_llm_prompts_for_transcript = body.log_llm_prompts_for_transcript

    await session.flush()
    await session.refresh(ws)
    return _workspace_out(ws)
