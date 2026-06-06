from __future__ import annotations

from urllib.parse import urlsplit

from ..db.models import Workspace
from .schemas import InterpretQuickOption

# Cap the allowlist so a misconfiguration can't bloat every session snapshot.
MAX_CDN_ALLOWLIST = 20


def normalise_cdn_origin(value: str) -> str | None:
    """Reduce a user-entered URL to a bare ``scheme://host[:port]`` origin.

    Returns ``None`` for anything that isn't an http(s) origin so callers can
    reject it. Paths, query strings, and fragments are stripped — the CSP only
    matches on origin.
    """
    raw = (value or "").strip()
    if not raw:
        return None
    parts = urlsplit(raw)
    if parts.scheme not in ("http", "https") or not parts.netloc:
        return None
    return f"{parts.scheme}://{parts.netloc.lower()}"


def clean_cdn_allowlist(values: list[str]) -> list[str]:
    """Normalise, de-duplicate (order-preserving), and cap a CDN allowlist."""
    seen: set[str] = set()
    cleaned: list[str] = []
    for value in values:
        if not isinstance(value, str):
            continue
        origin = normalise_cdn_origin(value)
        if origin is None or origin in seen:
            continue
        seen.add(origin)
        cleaned.append(origin)
        if len(cleaned) >= MAX_CDN_ALLOWLIST:
            break
    return cleaned


def normalise_cdn_allowlist(ws: Workspace) -> list[str]:
    raw = ws.widget_cdn_allowlist if isinstance(ws.widget_cdn_allowlist, list) else []
    return clean_cdn_allowlist(raw)


def normalise_interpret_quick_options(ws: Workspace) -> list[InterpretQuickOption]:
    raw_options = ws.interpret_quick_options if isinstance(ws.interpret_quick_options, list) else []
    options: list[InterpretQuickOption] = []
    for raw in raw_options[:3]:
        if not isinstance(raw, dict):
            continue
        try:
            options.append(InterpretQuickOption.model_validate(raw))
        except Exception:
            continue
    return options
