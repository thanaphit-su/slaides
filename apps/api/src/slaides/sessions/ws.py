from __future__ import annotations

import asyncio
import json
import logging
import uuid
from dataclasses import dataclass, field
from typing import Any

from fastapi import APIRouter, HTTPException, Query, WebSocket, WebSocketDisconnect, status
from fastapi.security import HTTPAuthorizationCredentials
from redis import asyncio as aioredis
from sqlalchemy import select
from sqlalchemy.orm.attributes import flag_modified

from ..auth import service as auth_service
from ..auth.supabase import get_supabase_auth
from ..db.base import get_session_factory
from ..db.models import AppUser, Deck, InteractionLog, Participant, SessionSlide
from ..db.models import Session as SessionRow
from ..settings import get_settings
from . import service as session_service
from .schemas import SessionSlideOut

logger = logging.getLogger(__name__)

PRESENCE_TTL = 30
PRESENCE_PREFIX = "sess:{sid}:presence:"
MIRROR_EVENT_TYPES = {
    "slide.changed",
    "session_slide.inserted",
    "session.ended",
    "interaction.tally",
    "interaction_spec.updated",
    "interaction_results.updated",
    "widget.state",
    "widget.reset",
    "widget.update",
}


def channel_name(session_id: uuid.UUID) -> str:
    return f"sess:{session_id}"


def _event_visible_to_role(decoded: Any, role: str) -> bool:
    if role != "mirror":
        return True
    return isinstance(decoded, dict) and decoded.get("type") in MIRROR_EVENT_TYPES


@dataclass(eq=False)
class _Connection:
    socket: Any
    role: str  # 'host' | 'participant' | 'mirror'
    participant_id: uuid.UUID | None
    participant_ref: str | None
    queue: asyncio.Queue[str] = field(default_factory=lambda: asyncio.Queue(maxsize=512))


@dataclass
class _SessionState:
    connections: set[_Connection] = field(default_factory=set)
    subscriber_task: asyncio.Task | None = None
    pubsub: Any = None


class Hub:
    """One-per-process hub fanning Redis pub/sub into per-session sockets."""

    def __init__(self) -> None:
        self._sessions: dict[uuid.UUID, _SessionState] = {}
        self._redis: aioredis.Redis | None = None
        self._lock = asyncio.Lock()

    def set_redis(self, client: aioredis.Redis | None) -> None:
        self._redis = client

    async def _ensure_redis(self) -> aioredis.Redis:
        if self._redis is None:
            url = get_settings().redis_url
            self._redis = aioredis.from_url(url, decode_responses=True)
        return self._redis

    async def aclose(self) -> None:
        for state in list(self._sessions.values()):
            if state.subscriber_task is not None:
                state.subscriber_task.cancel()
        if self._redis is not None:
            try:
                await self._redis.aclose()
            except Exception:  # noqa: BLE001
                pass
            self._redis = None
        self._sessions.clear()

    async def _subscriber(self, session_id: uuid.UUID, pubsub: Any) -> None:
        try:
            async for msg in pubsub.listen():
                if msg.get("type") != "message":
                    continue
                data = msg.get("data")
                if isinstance(data, bytes):
                    data = data.decode("utf-8")
                state = self._sessions.get(session_id)
                if state is None:
                    continue
                # Optional `_role_target` selects which connections receive the
                # event (e.g. "host" only for open-question answer streams).
                role_target: str | None = None
                outbound = data
                try:
                    decoded = json.loads(data)
                except Exception:  # noqa: BLE001
                    decoded = None
                if isinstance(decoded, dict) and "_role_target" in decoded:
                    role_target = decoded.pop("_role_target")
                    outbound = json.dumps(decoded)
                for conn in list(state.connections):
                    if role_target and conn.role != role_target:
                        continue
                    if not role_target and not _event_visible_to_role(decoded, conn.role):
                        continue
                    try:
                        conn.queue.put_nowait(outbound)
                    except asyncio.QueueFull:
                        logger.warning("ws queue full; dropping client")
        except asyncio.CancelledError:
            pass
        finally:
            try:
                await pubsub.unsubscribe(channel_name(session_id))
                aclose = getattr(pubsub, "aclose", None)
                if aclose is not None:
                    await aclose()
                else:
                    await pubsub.close()
            except Exception:  # noqa: BLE001
                pass

    async def publish(self, session_id: uuid.UUID, event: dict[str, Any]) -> None:
        redis = await self._ensure_redis()
        await redis.publish(channel_name(session_id), json.dumps(event))

    async def publish_to_role(
        self, session_id: uuid.UUID, role: str, event: dict[str, Any]
    ) -> None:
        """Publish an event that only connections with the given role will receive.

        Implemented by embedding a `_role_target` key the subscriber strips
        before forwarding to clients.
        """
        redis = await self._ensure_redis()
        await redis.publish(channel_name(session_id), json.dumps({**event, "_role_target": role}))

    async def register(self, session_id: uuid.UUID, conn: _Connection) -> None:
        async with self._lock:
            state = self._sessions.setdefault(session_id, _SessionState())
            state.connections.add(conn)
            if state.subscriber_task is None or state.subscriber_task.done():
                redis = await self._ensure_redis()
                pubsub = redis.pubsub()
                await pubsub.subscribe(channel_name(session_id))
                state.pubsub = pubsub
                state.subscriber_task = asyncio.create_task(self._subscriber(session_id, pubsub))

    async def unregister(self, session_id: uuid.UUID, conn: _Connection) -> None:
        async with self._lock:
            state = self._sessions.get(session_id)
            if state is None:
                return
            state.connections.discard(conn)
            if not state.connections and state.subscriber_task is not None:
                state.subscriber_task.cancel()
                state.subscriber_task = None
                state.pubsub = None
                self._sessions.pop(session_id, None)

    async def close_role(self, session_id: uuid.UUID, role: str) -> None:
        async with self._lock:
            state = self._sessions.get(session_id)
            conns = [conn for conn in (state.connections if state else set()) if conn.role == role]
        for conn in conns:
            close = getattr(conn.socket, "close", None)
            if close is None:
                continue
            try:
                result = close()
                if result is not None:
                    await result
            except Exception:  # noqa: BLE001
                pass

    async def close_role_for_sessions(self, session_ids: list[uuid.UUID], role: str) -> None:
        for session_id in session_ids:
            await self.close_role(session_id, role)

    async def presence_count(self, session_id: uuid.UUID) -> int:
        redis = await self._ensure_redis()
        pattern = PRESENCE_PREFIX.format(sid=session_id) + "*"
        count = 0
        async for _ in redis.scan_iter(match=pattern, count=200):
            count += 1
        return count

    async def ping(self) -> bool:
        redis = await self._ensure_redis()
        return bool(await redis.ping())

    async def heartbeat(self, session_id: uuid.UUID, participant_ref: str) -> None:
        redis = await self._ensure_redis()
        key = PRESENCE_PREFIX.format(sid=session_id) + participant_ref
        await redis.set(key, "1", ex=PRESENCE_TTL)

    async def drop_presence(self, session_id: uuid.UUID, participant_ref: str) -> None:
        redis = await self._ensure_redis()
        key = PRESENCE_PREFIX.format(sid=session_id) + participant_ref
        try:
            await redis.delete(key)
        except Exception:  # noqa: BLE001
            pass


hub = Hub()


async def broadcast_slide_changed(
    session_id: uuid.UUID, slide_id: uuid.UUID, is_session_slide: bool
) -> None:
    await hub.publish(
        session_id,
        {
            "type": "slide.changed",
            "payload": {"slide_id": str(slide_id), "is_session_slide": is_session_slide},
        },
    )


async def broadcast_session_slide_inserted(session_id: uuid.UUID, row: SessionSlide) -> None:
    payload = SessionSlideOut.model_validate(row).model_dump(mode="json")
    await hub.publish(session_id, {"type": "session_slide.inserted", "payload": payload})


async def broadcast_session_ended(session_id: uuid.UUID) -> None:
    await hub.publish(session_id, {"type": "session.ended", "payload": {}})


async def broadcast_interaction_tally(
    session_id: uuid.UUID, session_slide_id: uuid.UUID, results: dict, spec_state: dict | None
) -> None:
    await hub.publish(
        session_id,
        {
            "type": "interaction.tally",
            "payload": {
                "session_slide_id": str(session_slide_id),
                "results": results,
                "spec_state": spec_state,
            },
        },
    )


async def broadcast_interaction_spec_updated(
    session_id: uuid.UUID, session_slide_id: uuid.UUID, spec: dict
) -> None:
    await hub.publish(
        session_id,
        {
            "type": "interaction_spec.updated",
            "payload": {"session_slide_id": str(session_slide_id), "spec": spec},
        },
    )


async def broadcast_interaction_results_updated(
    session_id: uuid.UUID, session_slide_id: uuid.UUID, results: dict
) -> None:
    """Broadcast `results` changes that audiences should see (e.g. promoted answers)."""
    await hub.publish(
        session_id,
        {
            "type": "interaction_results.updated",
            "payload": {"session_slide_id": str(session_slide_id), "results": results},
        },
    )


async def broadcast_open_answer_to_host(
    session_id: uuid.UUID, session_slide_id: uuid.UUID, answer: dict
) -> None:
    await hub.publish_to_role(
        session_id,
        "host",
        {
            "type": "question_answer.new",
            "payload": {"session_slide_id": str(session_slide_id), "answer": answer},
        },
    )


# ---- Widgets v2 Step 4 — iframe-widget contribute path ----
#
# Per-(participant, placement) rate limit (fixed minute bucket via Redis INCR).
# Mirrors the LLM limiter — defaults chosen so casual interaction is unaffected
# and a misbehaving widget can't flood the WS hub.
_CONTRIBUTE_PER_MINUTE = 60
_CONTRIBUTE_TTL = 90


async def _enforce_contribute_rate_limit(
    session_id: uuid.UUID, placement_id: str, participant_ref: str
) -> bool:
    """Returns True if the contribution is within the per-minute budget."""
    import time as _time

    redis = await hub._ensure_redis()  # noqa: SLF001 — same hub the WS path uses
    minute = int(_time.time() // 60)
    key = f"contrib:{session_id}:{placement_id}:{participant_ref}:{minute}"
    count = await redis.incr(key)
    if count == 1:
        await redis.expire(key, _CONTRIBUTE_TTL)
    return count <= _CONTRIBUTE_PER_MINUTE


# ---- Widgets v2 Step 3 — unified contribute/state protocol ----
#
# `widget.state` is the canonical post-contribution event. For Step 3 it lives
# alongside the legacy `interaction.tally` / `interaction_results.updated`
# events so the existing native components keep working unchanged. Loud
# widgets generated in Step 4 will subscribe to `widget.state` exclusively.
async def broadcast_widget_state(
    session_id: uuid.UUID,
    placement_id: str,
    state: dict,
    *,
    state_version: int,
    closed: bool = False,
    role_target: str | None = None,
) -> None:
    """Broadcast a widget's aggregated state.

    `role_target` restricts delivery to connections of that role (e.g. "host"
    for `collect` widgets, where the presenter sees every entry but the audience
    must never receive other participants' answers). Defaults to all connections
    for the standard loud-widget shared projection.
    """
    event = {
        "type": "widget.state",
        "payload": {
            "placement_id": placement_id,
            "state": state,
            "state_version": state_version,
            "closed": closed,
        },
    }
    if role_target is not None:
        await hub.publish_to_role(session_id, role_target, event)
    else:
        await hub.publish(session_id, event)


# Emitted when the presenter edits a widget mid-session and confirms the
# audience-tally reset. Audience iframes drop their cached projection and any
# loud widget's UI returns to its pre-vote state. Per docs/WIDGETS_V2.md the
# raw `interaction_log` contributions are retained — only the aggregated
# `placement_state` projection is cleared.
async def broadcast_widget_reset(
    session_id: uuid.UUID,
    placement_id: str,
) -> None:
    await hub.publish(
        session_id,
        {
            "type": "widget.reset",
            "payload": {"placement_id": placement_id},
        },
    )


def _guest_payload(token: str) -> dict | None:
    try:
        return auth_service.decode_guest(token)
    except Exception:  # noqa: BLE001
        return None


async def _supabase_host_from_token(token: str, row: SessionRow, db) -> AppUser | None:
    try:
        supabase_user_id, email = await get_supabase_auth().get_user(token)
    except HTTPException:
        return None
    try:
        user_uuid = uuid.UUID(supabase_user_id)
    except Exception:  # noqa: BLE001
        return None
    user = (
        await db.execute(select(AppUser).where(AppUser.supabase_user_id == user_uuid))
    ).scalar_one_or_none()
    if user is None:
        user = (
            await db.execute(select(AppUser).where(AppUser.email == email.lower()))
        ).scalar_one_or_none()
        if user is not None and user.supabase_user_id is None:
            user.supabase_user_id = user_uuid
            await db.flush()
            await db.commit()
    if user is None or user.id != row.owner_id:
        return None
    if user.approval_status != "approved":
        return None
    return user


router = APIRouter()


@router.websocket("/ws/sessions/{session_id}")
async def session_ws(
    websocket: WebSocket,
    session_id: uuid.UUID,
    token: str = Query(""),
    role: str | None = Query(None),
    mirror_token: str | None = Query(None),
) -> None:
    payload = _guest_payload(token)
    kind = payload.get("kind") if payload is not None else None
    connection_role: str
    participant_id: uuid.UUID | None = None
    participant_ref: str | None = None

    factory = get_session_factory()
    async with factory() as db:
        row = (
            await db.execute(select(SessionRow).where(SessionRow.id == session_id))
        ).scalar_one_or_none()
        if row is None or row.ended_at is not None:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return
        if role == "mirror":
            deck = (await db.execute(select(Deck).where(Deck.id == row.deck_id))).scalar_one_or_none()
            if deck is None:
                await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
                return
            from .router import _can_view_mirror, _optional_signed_in_user

            creds = (
                HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
                if token
                else None
            )
            user = await _optional_signed_in_user(creds, db)
            token_for_access = mirror_token or token or None
            if not _can_view_mirror(row, deck, user, token_for_access):
                await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
                return
            connection_role = "mirror"
        elif kind == "guest" and payload is not None:
            try:
                participant_id = uuid.UUID(payload["sub"])
                sid_claim = uuid.UUID(payload["sid"])
            except Exception:  # noqa: BLE001
                await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
                return
            if sid_claim != session_id:
                await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
                return
            participant = (
                await db.execute(select(Participant).where(Participant.id == participant_id))
            ).scalar_one_or_none()
            if participant is None or participant.session_id != session_id:
                await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
                return
            participant_ref = participant.ref
            connection_role = "participant"
        else:
            user = await _supabase_host_from_token(token, row, db)
            if user is None:
                await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
                return
            connection_role = "host"

    await websocket.accept()
    conn = _Connection(
        socket=websocket,
        role=connection_role,
        participant_id=participant_id,
        participant_ref=participant_ref,
    )
    await hub.register(session_id, conn)
    if participant_ref:
        await hub.heartbeat(session_id, participant_ref)
        await hub.publish(
            session_id,
            {
                "type": "participant.joined",
                "payload": {"ref": participant_ref, "count": await hub.presence_count(session_id)},
            },
        )

    async def writer() -> None:
        try:
            while True:
                msg = await conn.queue.get()
                await websocket.send_text(msg)
        except (WebSocketDisconnect, RuntimeError):
            pass
        except asyncio.CancelledError:
            pass

    writer_task = asyncio.create_task(writer())

    try:
        # Send initial state snapshot.
        snapshot_msg = json.dumps(
            {
                "type": "session.state",
                "payload": {"current_slide_id": str(row.current_slide_id) if row.current_slide_id else None},
            }
        )
        await websocket.send_text(snapshot_msg)

        while True:
            raw = await websocket.receive_text()
            try:
                event = json.loads(raw)
            except json.JSONDecodeError:
                continue
            await _handle_client_event(session_id, conn, event)
    except WebSocketDisconnect:
        pass
    finally:
        writer_task.cancel()
        await hub.unregister(session_id, conn)
        if participant_ref:
            await hub.drop_presence(session_id, participant_ref)
            try:
                await hub.publish(
                    session_id,
                    {
                        "type": "participant.left",
                        "payload": {
                            "ref": participant_ref,
                            "count": await hub.presence_count(session_id),
                        },
                    },
                )
            except Exception:  # noqa: BLE001
                pass


async def _handle_iframe_contribute(
    session_id: uuid.UUID,
    conn: _Connection,
    placement_id: str,
    value: Any,
) -> bool:
    """Widgets v2 Step 4 — process a `widget.contribute` event whose
    `placement_id` points at a `slide_widget` row (i.e. an AI-generated
    Loud widget mounted on a deck slide), not a session_slide.

    Returns True if the event was handled (success *or* a recoverable error
    like rate-limit / closed placement / shape mismatch). Returns False if
    the placement_id doesn't match an iframe widget at all, so the caller
    can fall through to the native session_slide path.

    Security guards:
      - audience-scope: the placement must belong to a slide in the
        participant's session's deck.
      - aggregator-locked: the widget must declare `behavior.kind == "loud"`
        with a valid aggregator.
      - rate-limit: per-(participant, placement) minute bucket via Redis.
      - state caps: enforced inside the aggregator primitives.
    """
    if conn.role != "participant" or conn.participant_ref is None:
        return False

    factory = get_session_factory()
    async with factory() as db:
        from ..db.models import (
            SlideWidget as _SlideWidget,
            Slide as _Slide,
            Widget as _Widget,
            WidgetRevision as _WidgetRevision,
        )

        # Audience-scope the lookup BEFORE the query, not after. `placement_id`
        # is a free-form String(80) and is only unique per (slide_id, _).
        # Without the deck filter, two decks both carrying e.g. a
        # `{{widget:live-poll}}` placeholder will collide — the SELECT returns
        # whichever row Postgres feels like first, which is often a different
        # deck than the current session's. The downstream deck-mismatch check
        # then returns False and the contribution drops silently. See bug
        # report 2026-05-25: live-poll votes not counted.
        sess = (
            await db.execute(select(SessionRow).where(SessionRow.id == session_id))
        ).scalar_one_or_none()
        if sess is None:
            return False
        link_row = (
            await db.execute(
                select(_SlideWidget, _Slide.deck_id)
                .join(_Slide, _Slide.id == _SlideWidget.slide_id)
                .where(
                    _SlideWidget.placement_id == placement_id,
                    _Slide.deck_id == sess.deck_id,
                )
            )
        ).first()
        if link_row is None:
            return False
        link, slide_deck_id = link_row

        widget = (
            await db.execute(select(_Widget).where(_Widget.id == link.widget_id))
        ).scalar_one_or_none()
        if widget is None:
            return True  # placement points to a deleted widget; nothing to do
        behavior = widget.behavior or {"kind": "quiet"}
        if link.revision_id is not None:
            revision = (
                await db.execute(
                    select(_WidgetRevision).where(
                        _WidgetRevision.id == link.revision_id,
                        _WidgetRevision.widget_id == widget.id,
                    )
                )
            ).scalar_one_or_none()
            if revision is not None:
                behavior = revision.behavior or behavior
        kind = behavior.get("kind")
        if kind not in ("loud", "collect"):
            return True  # quiet widget — contributions are silently dropped
        aggregator = str(behavior.get("aggregator") or "")
        if not aggregator:
            return True

        within_budget = await _enforce_contribute_rate_limit(
            session_id, placement_id, conn.participant_ref
        )
        if not within_budget:
            return True

        from .placement_state_service import contribute_to_placement
        from .aggregators import AggregatorError

        try:
            row, state = await contribute_to_placement(
                db,
                session_id=session_id,
                placement_id=placement_id,
                widget_id=widget.id,
                aggregator=aggregator,
                value=value,
                participant_ref=conn.participant_ref,
            )
        except (AggregatorError, ValueError, RuntimeError):
            # Defensive: invalid contributions / closed placements drop
            # silently — the audience tab has no useful action to take.
            return True
        
        # Log raw contribution to interaction_log for transcript
        db.add(
            InteractionLog(
                session_id=session_id,
                slide_id=link.slide_id,  # From existing SlideWidget lookup
                session_slide_id=None,
                widget_id=widget.id,
                participant_ref=conn.participant_ref,
                kind="widget_contribute",
                payload={"placement_id": placement_id, "value": value},
            )
        )
        await db.commit()

    # `collect` widgets deliver the full entry list to the presenter only — each
    # audience member renders its own answer locally and must never receive the
    # others'. Loud widgets broadcast the shared projection to everyone.
    await broadcast_widget_state(
        session_id,
        placement_id,
        state,
        state_version=int(row.state_version or 0),
        closed=row.closed_at is not None,
        role_target="host" if kind == "collect" else None,
    )
    return True


async def _handle_client_event(
    session_id: uuid.UUID, conn: _Connection, event: dict[str, Any]
) -> None:
    etype = event.get("type")
    payload = event.get("payload") or {}

    if etype == "heartbeat":
        if conn.participant_ref:
            await hub.heartbeat(session_id, conn.participant_ref)
        return

    if conn.role == "mirror":
        return

    if etype in ("interaction.vote", "interaction.text", "interaction.slider", "widget.contribute"):
        if conn.role != "participant" or conn.participant_ref is None:
            return

        # Widgets v2 Step 4 — iframe-widget `widget.contribute` events carry a
        # slide_widget.placement_id (a free-form string, NOT a UUID). Try the
        # iframe path first; fall through to the native path only when the
        # placement_id is UUID-shaped.
        if etype == "widget.contribute":
            placement_id_raw = payload.get("placement_id") or payload.get("session_slide_id")
            if placement_id_raw is not None:
                try:
                    uuid.UUID(str(placement_id_raw))
                    is_uuid = True
                except Exception:  # noqa: BLE001
                    is_uuid = False
                if not is_uuid:
                    handled = await _handle_iframe_contribute(
                        session_id, conn, str(placement_id_raw), payload.get("value")
                    )
                    if handled:
                        return
            value = payload.get("value")
            payload = {**payload, "session_slide_id": placement_id_raw}
            if isinstance(value, str):
                payload.setdefault("text", value)
                payload.setdefault("choice", value)
            elif isinstance(value, (int, float, bool)):
                payload.setdefault("choice", value)
            session_slide_id_raw = placement_id_raw
        else:
            session_slide_id_raw = payload.get("session_slide_id")

        if session_slide_id_raw:
            try:
                ss_id = uuid.UUID(session_slide_id_raw)
            except Exception:  # noqa: BLE001
                return
            factory = get_session_factory()
            async with factory() as db:
                slide = await session_service.load_session_slide(db, ss_id)
                if slide is None or slide.session_id != session_id:
                    return
                spec = slide.spec or {}
                state = (spec.get("state") or {})
                if state.get("voting_closed"):
                    return

                # For `widget.contribute` we infer the legacy verb from the
                # slide's kind so both wire protocols share the routing
                # below.
                routing = etype
                if etype == "widget.contribute":
                    routing = "interaction.vote" if slide.kind == "poll" and isinstance(payload.get("value"), (str, int)) else "interaction.text"

                if routing == "interaction.vote" and slide.kind == "poll":
                    choice = str(payload.get("choice") or "")
                    if not choice:
                        return
                    valid_ids = {c.get("id") for c in (spec.get("choices") or [])}
                    if choice not in valid_ids:
                        return
                    results = await session_service.record_poll_vote(
                        db, slide, conn.participant_ref, choice
                    )
                    spec_state = (slide.spec or {}).get("state")
                    state_version = int((slide.results or {}).get("_state_version") or 0) + 1
                    # Stamp the version on the persisted results so late
                    # joiners pick it up via the snapshot.
                    slide.results = {**(slide.results or {}), "_state_version": state_version}
                    flag_modified(slide, "results")
                    await db.commit()
                    await broadcast_interaction_tally(session_id, ss_id, results, spec_state)
                    await broadcast_widget_state(
                        session_id,
                        str(ss_id),
                        {**results, "spec_state": spec_state},
                        state_version=state_version,
                    )
                    return

                if routing == "interaction.text" and slide.kind == "poll":
                    # "Other…" free-text choice on a poll.
                    if not (spec.get("config") or {}).get("allow_other"):
                        return
                    text = str(payload.get("text") or "").strip()
                    if not text:
                        return
                    results = await session_service.record_poll_other(
                        db, slide, conn.participant_ref, text
                    )
                    spec_state = (slide.spec or {}).get("state")
                    state_version = int((slide.results or {}).get("_state_version") or 0) + 1
                    slide.results = {**(slide.results or {}), "_state_version": state_version}
                    flag_modified(slide, "results")
                    await db.commit()
                    await broadcast_interaction_tally(session_id, ss_id, results, spec_state)
                    await broadcast_widget_state(
                        session_id,
                        str(ss_id),
                        {**results, "spec_state": spec_state},
                        state_version=state_version,
                    )
                    return

                if routing == "interaction.text" and slide.kind == "question":
                    text = str(payload.get("text") or "").strip()
                    if not text:
                        return
                    row = await session_service.record_open_answer(
                        db, slide, conn.participant_ref, text
                    )
                    # Stash the participant info to render display_name on the rail.
                    from sqlalchemy import select as _sel
                    from ..db.models import Participant as _Participant

                    p = (
                        await db.execute(
                            _sel(_Participant).where(
                                _Participant.session_id == session_id,
                                _Participant.ref == conn.participant_ref,
                            )
                        )
                    ).scalar_one_or_none()
                    answer = {
                        "id": int(row.id),
                        "text": str((row.payload or {}).get("text") or ""),
                        "participant_ref": conn.participant_ref,
                        "display_name": None if (p is None or p.anon) else p.display_name,
                        "anon": bool(p.anon) if p else True,
                        "occurred_at": row.occurred_at.isoformat() if row.occurred_at else None,
                        "promoted": False,
                    }
                    state_version = int((slide.results or {}).get("_state_version") or 0) + 1
                    slide.results = {**(slide.results or {}), "_state_version": state_version}
                    flag_modified(slide, "results")
                    await db.commit()
                    # Audience also gets a tiny `total_answers` bump so their
                    # "47 answers so far" counter (if shown) stays live.
                    await broadcast_interaction_results_updated(
                        session_id, ss_id, slide.results
                    )
                    await broadcast_widget_state(
                        session_id,
                        str(ss_id),
                        slide.results,
                        state_version=state_version,
                    )
                    await broadcast_open_answer_to_host(session_id, ss_id, answer)
                    return

                # Spec type doesn't match the event — drop silently.
                return

        # ---- Legacy widget-bridge path (kept for in-deck widget placements). ----
        widget_id_raw = payload.get("widget_id")
        slide_id_raw = payload.get("slide_id")
        try:
            widget_id = uuid.UUID(widget_id_raw) if widget_id_raw else None
            slide_id = uuid.UUID(slide_id_raw) if slide_id_raw else None
        except Exception:  # noqa: BLE001
            return
        factory = get_session_factory()
        async with factory() as db:
            await session_service.log_interaction(
                db,
                session_id=session_id,
                slide_id=slide_id,
                widget_id=widget_id,
                participant_ref=conn.participant_ref,
                kind=etype,
                payload=payload,
            )
            await db.commit()
        await hub.publish(
            session_id,
            {
                "type": etype,
                "payload": {**payload, "ref": conn.participant_ref},
            },
        )
        return

    if etype == "question.raise":
        if conn.role != "participant" or conn.participant_ref is None:
            return
        text = (payload.get("text") or "").strip()
        if not text:
            return
        anon = bool(payload.get("anonymous"))
        slide_id_raw = payload.get("slide_id")
        try:
            slide_id = uuid.UUID(slide_id_raw) if slide_id_raw else None
        except Exception:  # noqa: BLE001
            slide_id = None
        factory = get_session_factory()
        async with factory() as db:
            q = await session_service.add_question(
                db,
                session_id=session_id,
                slide_id=slide_id,
                participant_ref=conn.participant_ref,
                text=text,
                anon=anon,
            )
            await db.commit()
            from .schemas import QuestionOut

            q_payload = QuestionOut.model_validate(q).model_dump(mode="json")
        await hub.publish(session_id, {"type": "question.new", "payload": q_payload})
        return

    if etype == "widget.update":
        if conn.role != "host":
            return
        await hub.publish(session_id, {"type": "widget.update", "payload": payload})
        return

    if etype == "question.answered":
        if conn.role != "host":
            return
        qid_raw = payload.get("question_id")
        try:
            qid = uuid.UUID(qid_raw)
        except Exception:  # noqa: BLE001
            return
        from datetime import datetime, timezone

        from ..db.models import Question

        factory = get_session_factory()
        async with factory() as db:
            q = (await db.execute(select(Question).where(Question.id == qid))).scalar_one_or_none()
            if q is not None and q.session_id == session_id:
                q.answered_at = datetime.now(timezone.utc)
                await db.commit()
        await hub.publish(session_id, {"type": "question.answered", "payload": {"question_id": str(qid)}})
        return
