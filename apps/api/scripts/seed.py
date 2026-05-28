"""Seed a single workspace, instructor user, the Field Notes deck, and 4 widgets.

Idempotent: re-running it leaves data unchanged.
"""
from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone
import httpx
from fastapi import HTTPException
from sqlalchemy import select

from slaides.auth.supabase import SupabaseSession, get_supabase_auth
from slaides.db.base import get_session_factory
from slaides.db.models import AppUser, Deck, Section, Slide, Workspace
from slaides.onboarding.service import create_tutorial_for
from slaides.settings import get_settings
DEMO_EMAIL = "you@studio.press"
DEMO_PASSWORD = "slaides"
DEMO_DISPLAY_NAME = "Field Notes"


FIELD_NOTES_SLIDES = [
    {
        "kicker": "Lesson Two — The Atom of Every Neural Net",
        "markdown": """# A line is the smallest possible *brain* you can build.

Before transformers, before attention, before billion-parameter language models — there was a line. Drawing it *well* is the entire game.

15 min read · 4 interactives · some calculus, mostly intuition""",
    },
    {
        "kicker": "§ 02 — Simple Linear",
        "markdown": """# What even *is* a function?

A **function** is a rule: feed it a number, get a number back. Write the rule once, and it works for every input.

If you squint, every model in this book is a fancier version of *this*: a knob you can turn to make a line argue with the world.""",
    },
    {
        "kicker": "§ 03 — Simple Linear",
        "markdown": """# Drawing a line through *noise*

Given a cloud of points, which line is "best"?

The trick is to define "best" precisely. Once you have a number you're trying to make small, the rest is just arithmetic.""",
    },
    {
        "kicker": "§ 04 — Simple Linear",
        "markdown": """# Measuring *error*

Sum the gaps. Square them so positive and negative don't cancel. Average them so larger datasets don't look worse than they are.

That is **mean squared error**, and it is the most consequential equation in this book.""",
    },
    {
        "kicker": "§ 05 — Simple Linear",
        "markdown": """# Why this matters for *LLMs*

A transformer is, very approximately, a *huge* pile of these lines, taught to disagree productively. The math you saw in the last four slides is the math GPT does — just with more knobs.

> "All models are wrong, some are useful." — George Box""",
    },
    {
        "kicker": "§ 06 — Training",
        "markdown": """# Gradient descent, *by hand*

Pick a knob. Nudge it. Did the error go down? Keep going. Did it go up? Try the other direction.

That's it. That's the algorithm.""",
    },
    {
        "kicker": "§ 07 — Training",
        "markdown": """# When to *stop*

The honest answer: when the model starts memorising instead of generalising. We'll measure that next chapter with a held-out set.""",
    },
]


async def _ensure_supabase_demo_user() -> uuid.UUID | None:
    settings = get_settings()
    if not settings.supabase_anon_key:
        print("skipped Supabase Auth seed: SUPABASE_ANON_KEY is not configured")
        return None

    try:
        session = await get_supabase_auth().sign_in(DEMO_EMAIL, DEMO_PASSWORD)
        return _session_user_id(session)
    except HTTPException as exc:
        if exc.status_code != 401:
            print(f"skipped Supabase Auth seed: {exc.detail}")
            return None
        if not settings.supabase_service_role_key:
            print("skipped Supabase Auth seed: SUPABASE_SERVICE_ROLE_KEY is not configured")
            return None

    await _admin_create_supabase_user()
    try:
        session = await get_supabase_auth().sign_in(DEMO_EMAIL, DEMO_PASSWORD)
        return _session_user_id(session)
    except HTTPException as exc:
        print(f"created Supabase Auth user, but sign-in did not return a session: {exc.detail}")
        return None


def _session_user_id(session: SupabaseSession) -> uuid.UUID | None:
    try:
        return uuid.UUID(session.user_id)
    except ValueError:
        print(f"skipped Supabase Auth link: invalid Supabase user id {session.user_id!r}")
        return None


async def _admin_create_supabase_user() -> None:
    settings = get_settings()
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            res = await client.post(
                f"{settings.supabase_url.rstrip('/')}/auth/v1/admin/users",
                headers={
                    "apikey": settings.supabase_service_role_key,
                    "Authorization": f"Bearer {settings.supabase_service_role_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "email": DEMO_EMAIL,
                    "password": DEMO_PASSWORD,
                    "email_confirm": True,
                    "user_metadata": {"display_name": DEMO_DISPLAY_NAME},
                },
            )
    except httpx.HTTPError as exc:
        print(f"skipped Supabase Auth seed: {exc}")
        return
    if res.status_code in {200, 201}:
        print(f"seeded Supabase Auth user={DEMO_EMAIL}")
        return
    if res.status_code == 422 and "already" in res.text.lower():
        return
    print(f"skipped Supabase Auth seed: admin create failed status={res.status_code}")


async def main() -> None:
    supabase_user_id = await _ensure_supabase_demo_user()
    now = datetime.now(timezone.utc)
    factory = get_session_factory()
    async with factory() as session:
        ws = (
            await session.execute(select(Workspace).where(Workspace.name == "Studio Press"))
        ).scalar_one_or_none()
        if ws is None:
            ws = Workspace(name="Studio Press")
            session.add(ws)
            await session.flush()

        user = (
            await session.execute(select(AppUser).where(AppUser.email == DEMO_EMAIL))
        ).scalar_one_or_none()
        if user is None:
            user = AppUser(
                workspace_id=ws.id,
                supabase_user_id=supabase_user_id,
                email=DEMO_EMAIL,
                display_name=DEMO_DISPLAY_NAME,
                role="owner",
                approval_status="approved",
                approved_at=now,
            )
            session.add(user)
            await session.flush()
        else:
            if supabase_user_id is not None:
                user.supabase_user_id = supabase_user_id
            user.approval_status = "approved"
            if user.approved_at is None:
                user.approved_at = now

        # The Field Notes deck must exist BEFORE seed widgets so each widget
        # can be scoped to it (Widgets v2 — widgets are deck-local).
        deck = (
            await session.execute(select(Deck).where(Deck.title == "Field Notes", Deck.owner_id == user.id))
        ).scalar_one_or_none()
        if deck is None:
            deck = Deck(
                workspace_id=ws.id,
                owner_id=user.id,
                title="Field Notes",
                subtitle="Sketches from the math we use to teach machines.",
                cover="fieldnotes",
                manifest={"theme": "editorial-press"},
            )
            session.add(deck)
            await session.flush()

            foundations = Section(deck_id=deck.id, title="Foundations", position=0)
            training = Section(deck_id=deck.id, title="Training a Model", position=1)
            session.add_all([foundations, training])
            await session.flush()

            for idx, blob in enumerate(FIELD_NOTES_SLIDES):
                section_id = foundations.id if idx < 5 else training.id
                session.add(
                    Slide(
                        deck_id=deck.id,
                        section_id=section_id,
                        position=idx,
                        kicker=blob["kicker"],
                        markdown=blob["markdown"],
                    )
                )
            await session.flush()

        # Tutorial deck — provisioned via the same path every approved
        # instructor takes. Idempotent: skips if the demo user already has
        # a tutorial deck on this workspace.
        tutorial = await create_tutorial_for(session, user)
        await session.flush()

        await session.commit()
        print(
            f"seeded workspace={ws.id} user={user.email} "
            f"field-notes={deck.title} tutorial={tutorial.title}"
        )


if __name__ == "__main__":
    asyncio.run(main())
