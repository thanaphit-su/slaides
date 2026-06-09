from __future__ import annotations

import re
import uuid
from dataclasses import dataclass

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from ..db.models import (
    Deck,
    InteractionLog,
    LlmCall,
    Participant,
    Question,
    Section,
    Session as SessionRow,
    SessionSlide,
    Slide,
    SlideWidget,
    Widget,
    WidgetRevision,
)


H1_RE = re.compile(r"^# .*$", re.MULTILINE)
_WIDGET_PLACEHOLDER_RE = re.compile(r"\{\{widget:([a-zA-Z0-9_-]+)\}\}")


@dataclass
class SplitChunk:
    markdown: str


def split_on_h1(markdown: str) -> list[SplitChunk]:
    """Split markdown on `# ` headings. Leading content before the first H1
    is attached to the first chunk (which may have no H1 at all)."""
    if not markdown:
        return [SplitChunk(markdown="")]
    matches = list(H1_RE.finditer(markdown))
    if not matches:
        return [SplitChunk(markdown=markdown)]
    chunks: list[SplitChunk] = []
    first_start = matches[0].start()
    if first_start > 0:
        prefix = markdown[:first_start].rstrip()
        if prefix:
            chunks.append(SplitChunk(markdown=prefix))
    for i, m in enumerate(matches):
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(markdown)
        chunks.append(SplitChunk(markdown=markdown[start:end].rstrip("\n")))
    return chunks


async def shift_positions(session: AsyncSession, deck_id: uuid.UUID, from_position: int, by: int) -> None:
    if by == 0:
        return
    await session.execute(
        update(Slide)
        .where(Slide.deck_id == deck_id, Slide.position >= from_position)
        .values(position=Slide.position + by)
    )


async def replace_slide_markdown(
    session: AsyncSession, slide: Slide, markdown: str, kicker: str | None
) -> list[Slide]:
    """Replace markdown for `slide`. The markdown is stored verbatim; user
    typing never auto-splits a slide. New slides are created via the Add Slide
    ribbons or the explicit insert endpoint. `split_on_h1` remains as a utility
    for future paste/import flows.

    Side effect: reconciles SlideWidget rows against the new markdown. If the
    user manually removes a `{{widget:<placement_id>}}` line, the matching
    placement row is dropped so the slide doesn't keep counting as "already
    has a widget" (which would block subsequent attaches with 409). The
    inverse case — placeholder added to markdown without a corresponding row
    — is left alone; the renderer shows a `WIDGET · #<id>` stub so the user
    sees the broken reference and can fix it.
    """
    slide.markdown = markdown
    if kicker is not None:
        slide.kicker = kicker

    # Reconcile placements: delete any SlideWidget rows whose placement_id is
    # no longer referenced by the new markdown.
    referenced_ids = set(_WIDGET_PLACEHOLDER_RE.findall(markdown))
    existing = (
        await session.execute(
            select(SlideWidget).where(SlideWidget.slide_id == slide.id)
        )
    ).scalars().all()
    for placement in existing:
        if placement.placement_id not in referenced_ids:
            await session.delete(placement)

    await session.flush()
    await session.refresh(slide)
    return [slide]


async def insert_slide(
    session: AsyncSession,
    deck: Deck,
    position: int,
    markdown: str = "",
    kicker: str | None = None,
    section_id: uuid.UUID | None = None,
) -> Slide:
    await shift_positions(session, deck.id, position, 1)
    slide = Slide(
        deck_id=deck.id,
        section_id=section_id,
        position=position,
        kicker=kicker,
        markdown=markdown,
    )
    session.add(slide)
    await session.flush()
    await session.refresh(slide)
    return slide


async def delete_slide(session: AsyncSession, slide: Slide) -> None:
    deck_id = slide.deck_id
    pos = slide.position
    # FKs to slide.id from question, interaction_log, session_slide are nullable
    # but have no ON DELETE action — null them out in the same transaction so
    # historical session/transcript rows survive without FK violation.
    await session.execute(
        update(Question).where(Question.slide_id == slide.id).values(slide_id=None)
    )
    await session.execute(
        update(InteractionLog).where(InteractionLog.slide_id == slide.id).values(slide_id=None)
    )
    await session.execute(
        update(SessionSlide)
        .where(SessionSlide.parent_slide_id == slide.id)
        .values(parent_slide_id=None)
    )
    await session.delete(slide)
    await session.flush()
    # Compact positions above the deleted slide.
    await session.execute(
        update(Slide).where(Slide.deck_id == deck_id, Slide.position > pos).values(position=Slide.position - 1)
    )


async def delete_deck(session: AsyncSession, deck: Deck) -> None:
    """Delete a deck and every runtime row that keeps a hard reference to it.

    Deck.sections and Deck.slides are covered by ORM delete-orphan cascades, but
    session/runtime tables intentionally do not have Deck relationships. Clean
    them here so a deck delete cannot roll back after the API has already
    reported success.
    """
    deck_id = deck.id
    slide_ids = list(
        (
            await session.execute(select(Slide.id).where(Slide.deck_id == deck_id))
        ).scalars()
    )
    session_ids = list(
        (
            await session.execute(select(SessionRow.id).where(SessionRow.deck_id == deck_id))
        ).scalars()
    )

    if slide_ids:
        await session.execute(
            update(Question).where(Question.slide_id.in_(slide_ids)).values(slide_id=None)
        )
        await session.execute(
            update(InteractionLog)
            .where(InteractionLog.slide_id.in_(slide_ids))
            .values(slide_id=None)
        )
        await session.execute(
            update(SessionSlide)
            .where(SessionSlide.parent_slide_id.in_(slide_ids))
            .values(parent_slide_id=None)
        )
        await session.execute(delete(SlideWidget).where(SlideWidget.slide_id.in_(slide_ids)))

    # Widgets v2 — widgets are deck-local now. Cascade-from-deck would delete
    # them when the deck row goes, but session_slide.widget_id and
    # interaction_log.widget_id reference widget.id without ON DELETE SET NULL,
    # so we must null those refs first to preserve transcript history.
    deck_widget_ids = list(
        (await session.execute(select(Widget.id).where(Widget.deck_id == deck_id))).scalars()
    )
    if deck_widget_ids:
        await session.execute(
            update(SessionSlide)
            .where(SessionSlide.widget_id.in_(deck_widget_ids))
            .values(widget_id=None)
        )
        await session.execute(
            update(InteractionLog)
            .where(InteractionLog.widget_id.in_(deck_widget_ids))
            .values(widget_id=None)
        )
        await session.execute(delete(Widget).where(Widget.id.in_(deck_widget_ids)))

    if session_ids:
        await session.execute(
            update(LlmCall).where(LlmCall.session_id.in_(session_ids)).values(session_id=None)
        )
        await session.execute(delete(Question).where(Question.session_id.in_(session_ids)))
        await session.execute(delete(InteractionLog).where(InteractionLog.session_id.in_(session_ids)))
        await session.execute(delete(SessionSlide).where(SessionSlide.session_id.in_(session_ids)))
        await session.execute(delete(Participant).where(Participant.session_id.in_(session_ids)))
        await session.execute(delete(SessionRow).where(SessionRow.id.in_(session_ids)))

    # Delete deck-owned rows in FK-safe order. Relying on the Deck.sections
    # ORM cascade can delete sections before slides, which Postgres rejects
    # because slide.section_id has no ON DELETE SET NULL/CASCADE action.
    await session.execute(delete(Slide).where(Slide.deck_id == deck_id))
    await session.execute(delete(Section).where(Section.deck_id == deck_id))
    await session.execute(delete(Deck).where(Deck.id == deck_id))
    await session.flush()


async def reload_deck(session: AsyncSession, deck_id: uuid.UUID) -> Deck | None:
    result = await session.execute(select(Deck).where(Deck.id == deck_id))
    return result.scalar_one_or_none()


async def reorder_slides(
    session: AsyncSession,
    deck: Deck,
    order: list[tuple[uuid.UUID, uuid.UUID | None]],
) -> list[Slide]:
    """Replace slide positions (and optionally section_id) according to `order`.

    `order` is a list of (slide_id, section_id) tuples in the new top-to-bottom
    order. Every existing slide on the deck must be present exactly once;
    `section_id` may be None for unsectioned. Section ids that do not belong to
    the deck are rejected.
    """
    existing = (
        await session.execute(select(Slide).where(Slide.deck_id == deck.id))
    ).scalars()
    existing_list = list(existing)
    existing_ids = {s.id for s in existing_list}
    order_ids = {entry[0] for entry in order}
    if existing_ids != order_ids or len(order) != len(existing_list):
        raise ValueError("order must contain exactly the existing slide ids")
    # Validate section_ids belong to the deck.
    valid_section_ids = {
        s.id
        for s in (
            await session.execute(select(Section).where(Section.deck_id == deck.id))
        ).scalars()
    }
    for _, sid in order:
        if sid is not None and sid not in valid_section_ids:
            raise ValueError("section_id does not belong to this deck")
    by_id = {s.id: s for s in existing_list}
    for new_pos, (slide_id, section_id) in enumerate(order):
        slide = by_id[slide_id]
        slide.position = new_pos
        slide.section_id = section_id
    await session.flush()
    return await list_slides(session, deck.id)


async def list_slides(session: AsyncSession, deck_id: uuid.UUID) -> list[Slide]:
    result = await session.execute(
        select(Slide).where(Slide.deck_id == deck_id).order_by(Slide.position)
    )
    return list(result.scalars())


async def list_sections(session: AsyncSession, deck_id: uuid.UUID) -> list[Section]:
    result = await session.execute(
        select(Section).where(Section.deck_id == deck_id).order_by(Section.position)
    )
    return list(result.scalars())


async def shift_section_positions(
    session: AsyncSession, deck_id: uuid.UUID, from_position: int, by: int
) -> None:
    if by == 0:
        return
    await session.execute(
        update(Section)
        .where(Section.deck_id == deck_id, Section.position >= from_position)
        .values(position=Section.position + by)
    )


async def insert_section(
    session: AsyncSession, deck: Deck, title: str, position: int | None
) -> Section:
    existing = await list_sections(session, deck.id)
    if position is None:
        position = len(existing)
    position = max(0, min(position, len(existing)))
    await shift_section_positions(session, deck.id, position, 1)
    section = Section(deck_id=deck.id, title=title, position=position)
    session.add(section)
    await session.flush()
    await session.refresh(section)
    return section


async def update_section(
    session: AsyncSession,
    section: Section,
    *,
    title: str | None = None,
    position: int | None = None,
) -> Section:
    if title is not None:
        cleaned = title.strip()
        if cleaned:
            section.title = cleaned
    if position is not None:
        existing = await list_sections(session, section.deck_id)
        max_pos = max(0, len(existing) - 1)
        target = max(0, min(position, max_pos))
        current = section.position
        if target != current:
            if target < current:
                await session.execute(
                    update(Section)
                    .where(
                        Section.deck_id == section.deck_id,
                        Section.position >= target,
                        Section.position < current,
                    )
                    .values(position=Section.position + 1)
                )
            else:
                await session.execute(
                    update(Section)
                    .where(
                        Section.deck_id == section.deck_id,
                        Section.position > current,
                        Section.position <= target,
                    )
                    .values(position=Section.position - 1)
                )
            section.position = target
    await session.flush()
    await session.refresh(section)
    return section


async def delete_section(session: AsyncSession, section: Section) -> None:
    deck_id = section.deck_id
    pos = section.position
    # Slide.section_id is FK without ON DELETE SET NULL — null out slides
    # in the same transaction before deleting so we don't hit a FK violation
    # and so historical slides survive as unsectioned (rather than cascading).
    await session.execute(
        update(Slide).where(Slide.section_id == section.id).values(section_id=None)
    )
    await session.delete(section)
    await session.flush()
    # Compact positions above the deleted section.
    await session.execute(
        update(Section)
        .where(Section.deck_id == deck_id, Section.position > pos)
        .values(position=Section.position - 1)
    )


async def reorder_sections(
    session: AsyncSession, deck: Deck, order: list[uuid.UUID]
) -> list[Section]:
    existing = await list_sections(session, deck.id)
    existing_ids = {s.id for s in existing}
    if set(order) != existing_ids or len(order) != len(existing):
        raise ValueError("order must contain exactly the existing section ids")
    by_id = {s.id: s for s in existing}
    for new_pos, sid in enumerate(order):
        by_id[sid].position = new_pos
    await session.flush()
    return await list_sections(session, deck.id)


async def load_widget_placements(
    session: AsyncSession, slide_ids: list[uuid.UUID]
) -> dict[uuid.UUID, list[dict]]:
    """Return slide_id -> list of widget placement dicts, ordered by position."""
    if not slide_ids:
        return {}
    placement_revision = aliased(WidgetRevision)
    current_revision = aliased(WidgetRevision)
    result = await session.execute(
        select(SlideWidget, Widget, placement_revision, current_revision)
        .join(Widget, Widget.id == SlideWidget.widget_id)
        .outerjoin(placement_revision, placement_revision.id == SlideWidget.revision_id)
        .outerjoin(current_revision, current_revision.id == Widget.current_revision_id)
        .where(SlideWidget.slide_id.in_(slide_ids))
        .order_by(SlideWidget.position)
    )
    out: dict[uuid.UUID, list[dict]] = {}
    for link, widget, placement_rev, current_rev in result.all():
        render_revision = current_rev or placement_rev
        out.setdefault(link.slide_id, []).append(
            {
                "placement_id": link.placement_id,
                "widget_id": widget.id,
                "revision_id": render_revision.id if render_revision is not None else link.revision_id,
                "revision": (
                    {
                        "id": render_revision.id,
                        "widget_id": render_revision.widget_id,
                        "version_number": render_revision.version_number,
                        "html": render_revision.html or "",
                        "js": render_revision.js,
                        "css": render_revision.css,
                        "props_schema": render_revision.props_schema or {},
                        "example_props": render_revision.example_props or {},
                        "behavior": render_revision.behavior or {"kind": "quiet"},
                        "ai_spec": render_revision.ai_spec or {},
                        "created_reason": render_revision.created_reason,
                    }
                    if render_revision is not None
                    else None
                ),
                "kind": widget.kind,
                "name": widget.name,
                "props": link.props or {},
            }
        )
    return out
