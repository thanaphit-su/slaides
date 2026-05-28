from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone

from sqlalchemy import select

from slaides.db.base import get_session_factory
from slaides.db.models import AppUser
from slaides.onboarding.service import create_tutorial_for


async def approve(email: str) -> None:
    factory = get_session_factory()
    async with factory() as session:
        user = (
            await session.execute(select(AppUser).where(AppUser.email == email.lower().strip()))
        ).scalar_one_or_none()
        if user is None:
            raise SystemExit(f"user not found: {email}")
        user.approval_status = "approved"
        user.approved_at = datetime.now(timezone.utc)
        # Idempotent: returns the existing tutorial deck if one was already
        # provisioned (e.g. via a prior approval run or via the demo seed).
        deck = await create_tutorial_for(session, user)
        await session.commit()
        print(f"approved {user.email} (tutorial deck {deck.id})")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("email")
    args = parser.parse_args()
    asyncio.run(approve(args.email))


if __name__ == "__main__":
    main()
