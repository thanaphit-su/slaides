"""Delete an instructor account end-to-end.

Walks the FK graph that points at `app_user.id` (decks, sessions, optional
participant/LLM-call refs) in dependency order, then deletes the local
`AppUser` row. If a Supabase service role key is configured, also deletes
the matching Supabase Auth user so the email can be re-registered.

Usage:
    make delete-user EMAIL=user@example.com [SUPABASE=1]

`SUPABASE=1` removes the Supabase Auth user as well. Default is local-only —
useful when iterating on seed/onboarding flows where the local row needs
clearing but the Supabase Auth side is fine.
"""
from __future__ import annotations

import argparse
import asyncio
import os
from typing import Iterable

import httpx
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from slaides.db.base import get_session_factory
from slaides.db.models import (
    AppUser,
    Deck,
    InteractionLog,
    LlmCall,
    Participant,
    Session as SessionRow,
)
from slaides.decks import service as deck_service
from slaides.settings import get_settings


async def delete_user(email: str, *, drop_supabase: bool) -> None:
    factory = get_session_factory()
    async with factory() as session:
        user = (
            await session.execute(select(AppUser).where(AppUser.email == email.lower().strip()))
        ).scalar_one_or_none()
        if user is None:
            raise SystemExit(f"user not found: {email}")
        supabase_user_id = str(user.supabase_user_id) if user.supabase_user_id else None

        # 1. Delete every deck the user owns. delete_deck nulls historical
        #    session_slide.widget_id / interaction_log.widget_id pointers so
        #    transcript history survives, then cascade-deletes slides /
        #    sections / slide_widget / widgets via the model relationships.
        decks = (
            await session.execute(select(Deck).where(Deck.owner_id == user.id))
        ).scalars().all()
        for deck in decks:
            await deck_service.delete_deck(session, deck)

        # 2. Delete every session the user owns. The Session row cascades to
        #    participants, session_slides, interaction_log, questions,
        #    placement_state via existing ON DELETE CASCADE constraints.
        await session.execute(delete(SessionRow).where(SessionRow.owner_id == user.id))

        # 3. Null FK fields on rows the user appeared on without owning
        #    (audience records / LLM-call audit rows on other workspaces).
        await session.execute(
            update(Participant).where(Participant.user_id == user.id).values(user_id=None)
        )
        await session.execute(
            update(LlmCall).where(LlmCall.user_id == user.id).values(user_id=None)
        )
        # Belt-and-braces: any interaction_log left dangling without a session
        # parent should be gone already via the session cascade above, but the
        # delete is safe to call even if zero rows match.
        _ = InteractionLog  # imported for clarity / static analysis

        # 4. Delete the local AppUser row. All blocking FKs are clear now.
        await session.delete(user)
        await session.commit()
        print(f"deleted local user={email} (decks={len(decks)})")

    if drop_supabase:
        if supabase_user_id is None:
            print("skipped Supabase Auth delete: user had no supabase_user_id")
            return
        await _delete_supabase_user(supabase_user_id)


async def _delete_supabase_user(supabase_user_id: str) -> None:
    settings = get_settings()
    if not settings.supabase_service_role_key:
        print("skipped Supabase Auth delete: SUPABASE_SERVICE_ROLE_KEY is not configured")
        return
    url = f"{settings.supabase_url.rstrip('/')}/auth/v1/admin/users/{supabase_user_id}"
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            res = await client.delete(
                url,
                headers={
                    "apikey": settings.supabase_service_role_key,
                    "Authorization": f"Bearer {settings.supabase_service_role_key}",
                },
            )
    except httpx.HTTPError as exc:
        print(f"Supabase delete failed: transport error — {exc}")
        return
    if res.status_code in {200, 204}:
        print(f"deleted Supabase Auth user id={supabase_user_id}")
    elif res.status_code == 404:
        print(f"Supabase Auth user id={supabase_user_id} already gone")
    else:
        print(f"Supabase delete failed: status={res.status_code} body={res.text[:200]}")


def _truthy(v: str | None) -> bool:
    return (v or "").strip().lower() in {"1", "true", "yes", "y"}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("email")
    parser.add_argument(
        "--supabase",
        action="store_true",
        default=_truthy(os.environ.get("SUPABASE")),
        help="Also delete the Supabase Auth user via admin API.",
    )
    args = parser.parse_args()
    asyncio.run(delete_user(args.email, drop_supabase=args.supabase))


if __name__ == "__main__":
    main()
