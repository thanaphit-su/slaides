from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, status
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from .auth.router import router as auth_router
from .auth.supabase import get_supabase_auth
from .decks.router import import_router as decks_import_router
from .decks.router import router as decks_router
from .llm.router import router as llm_router
from .sessions.router import router as sessions_router
from .sessions.ws import hub as ws_hub
from .sessions.ws import router as sessions_ws_router
from .db.base import get_session_factory
from .settings import get_settings
from .widgets.router import deck_widget_router as widgets_deck_router
from .widgets.router import import_router as widgets_import_router
from .widgets.router import router as widgets_router
from .widgets.router import slide_router as widgets_slide_router
from .workspace.router import router as workspace_router
from .analytics.router import router as analytics_router


@asynccontextmanager
async def _lifespan(_app: FastAPI) -> AsyncIterator[None]:
    try:
        yield
    finally:
        await ws_hub.aclose()
        await get_supabase_auth().aclose()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="SLAIDES API", version="0.1.0", lifespan=_lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/healthz")
    async def healthz() -> dict:
        return {"ok": True}

    @app.get("/readyz")
    async def readyz():
        checks = {"database": False, "redis": False}
        try:
            factory = get_session_factory()
            async with factory() as session:
                await session.execute(text("select 1"))
            checks["database"] = True
        except Exception:
            checks["database"] = False

        try:
            checks["redis"] = await ws_hub.ping()
        except Exception:
            checks["redis"] = False

        ok = all(checks.values())
        code = status.HTTP_200_OK if ok else status.HTTP_503_SERVICE_UNAVAILABLE
        return JSONResponse(status_code=code, content={"ok": ok, "checks": checks})

    app.include_router(auth_router, prefix="/api/v1")
    app.include_router(workspace_router, prefix="/api/v1")
    app.include_router(decks_router, prefix="/api/v1")
    app.include_router(decks_import_router, prefix="/api/v1")
    app.include_router(widgets_router, prefix="/api/v1")
    app.include_router(widgets_deck_router, prefix="/api/v1")
    app.include_router(widgets_import_router, prefix="/api/v1")
    app.include_router(widgets_slide_router, prefix="/api/v1")
    app.include_router(sessions_router, prefix="/api/v1")
    app.include_router(llm_router, prefix="/api/v1")
    app.include_router(sessions_ws_router)
    app.include_router(analytics_router, prefix="/api/v1")
    return app


app = create_app()
