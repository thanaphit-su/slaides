from __future__ import annotations

from ..db.models import Workspace
from .schemas import InterpretQuickOption


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
