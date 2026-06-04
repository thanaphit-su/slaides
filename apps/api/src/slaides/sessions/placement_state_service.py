"""Widgets v2 Step 4 — placement-state read/write helpers.

A Loud widget's audience-visible state lives in the `placement_state` table,
keyed by `(session_id, placement_id)`. Contributions flow through one of the
five aggregator primitives in `aggregators.py`; the result is persisted here
and broadcast via the WS layer as `widget.state`.

Native polls and open questions don't go through this module — they continue
to use `session_slide.results` (added in Step 3). This module is purely for
the AI-generated Loud widgets that arrive in Step 4.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from ..db.models import PlacementState
from .aggregators import (
    AggregatorError,
    apply_contribution,
    tally_public,
)


VALID_AGGREGATORS = {"tally", "latest_per_participant", "append", "set_union", "keyed_tally", "collect"}


def placement_state_select_for_update(session_id: uuid.UUID, placement_id: str):
    return (
        select(PlacementState)
        .where(
            PlacementState.session_id == session_id,
            PlacementState.placement_id == placement_id,
        )
        .with_for_update()
    )


async def load_placement_state(
    session: AsyncSession,
    session_id: uuid.UUID,
    placement_id: str,
) -> PlacementState | None:
    return (
        await session.execute(
            select(PlacementState).where(
                PlacementState.session_id == session_id,
                PlacementState.placement_id == placement_id,
            )
        )
    ).scalar_one_or_none()


async def _load_placement_state_for_update(
    session: AsyncSession,
    session_id: uuid.UUID,
    placement_id: str,
) -> PlacementState | None:
    return (
        await session.execute(placement_state_select_for_update(session_id, placement_id))
    ).scalar_one_or_none()


async def list_session_placement_states(
    session: AsyncSession, session_id: uuid.UUID
) -> list[PlacementState]:
    rows = await session.execute(
        select(PlacementState)
        .where(PlacementState.session_id == session_id)
        .order_by(PlacementState.opened_at)
    )
    return list(rows.scalars())


async def contribute_to_placement(
    session: AsyncSession,
    *,
    session_id: uuid.UUID,
    placement_id: str,
    widget_id: uuid.UUID | None,
    aggregator: str,
    value: object,
    participant_ref: str,
) -> tuple[PlacementState, dict]:
    """Apply a contribution to the placement_state row, creating it on first
    contribution. Returns the row and the audience-visible state projection.

    Raises:
      ValueError: if `aggregator` is not one of the five supported kinds.
      AggregatorError: if the contribution payload doesn't match the
        aggregator's declared shape, or any size cap is exceeded.
      RuntimeError: if the placement has been closed.
    """
    if aggregator not in VALID_AGGREGATORS:
        raise ValueError(f"unsupported aggregator: {aggregator!r}")

    row = await _load_placement_state_for_update(session, session_id, placement_id)
    if row is None:
        row = PlacementState(
            session_id=session_id,
            placement_id=placement_id,
            widget_id=widget_id,
            aggregator=aggregator,
            state={},
            contribution_count=0,
            state_version=0,
        )
        try:
            async with session.begin_nested():
                session.add(row)
                await session.flush()
        except IntegrityError:
            row = await _load_placement_state_for_update(session, session_id, placement_id)
            if row is None:
                raise
    if row.closed_at is not None:
        raise RuntimeError("placement is closed")
    if row.aggregator != aggregator:
        # Sticky after the first write — protects against a widget changing
        # its declared aggregator mid-session and corrupting state shape.
        raise ValueError(
            f"placement aggregator is {row.aggregator!r}, refusing to switch to {aggregator!r}"
        )

    next_state = apply_contribution(aggregator, row.state, value, participant_ref)
    row.state = next_state
    flag_modified(row, "state")
    row.contribution_count = int(row.contribution_count or 0) + 1
    row.state_version = int(row.state_version or 0) + 1
    row.updated_at = datetime.now(timezone.utc)
    await session.flush()
    return row, _project(row)


def _project(row: PlacementState) -> dict:
    """Audience-visible projection. Strips private fields (like tally's
    `_votes` index)."""
    if row.aggregator == "tally":
        return tally_public(row.state)
    return dict(row.state or {})


async def close_placement(
    session: AsyncSession, session_id: uuid.UUID, placement_id: str
) -> PlacementState | None:
    row = await load_placement_state(session, session_id, placement_id)
    if row is None or row.closed_at is not None:
        return row
    row.closed_at = datetime.now(timezone.utc)
    row.state_version = int(row.state_version or 0) + 1
    await session.flush()
    return row


async def reset_placement(
    session: AsyncSession, session_id: uuid.UUID, placement_id: str
) -> PlacementState | None:
    row = await load_placement_state(session, session_id, placement_id)
    if row is None:
        return None
    row.state = {}
    flag_modified(row, "state")
    row.contribution_count = 0
    row.state_version = int(row.state_version or 0) + 1
    row.closed_at = None
    row.updated_at = datetime.now(timezone.utc)
    await session.flush()
    return row


def project_for_snapshot(row: PlacementState) -> dict:
    """Snapshot payload shape for `GET /sessions/:id/audience`. Mirrors the
    `widget.state` broadcast structure so late-joiner code can use one
    handler."""
    return {
        "placement_id": row.placement_id,
        "widget_id": str(row.widget_id) if row.widget_id else None,
        "aggregator": row.aggregator,
        "state": _project(row),
        "state_version": int(row.state_version or 0),
        "closed": row.closed_at is not None,
    }
