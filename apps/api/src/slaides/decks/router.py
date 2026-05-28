from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth.deps import current_user
from ..db.deps import db_session
from ..db.models import AppUser, Deck, Section, Slide
from . import package, service
from .schemas import (
    DeckCreate,
    DeckListItem,
    DeckOut,
    DeckPatch,
    SectionCreate,
    SectionOut,
    SectionPatch,
    SectionReorder,
    SlideCreate,
    SlideMutationResult,
    SlideOut,
    SlideReorder,
    SlideUpdate,
    SlideWidgetEmbed,
)

router = APIRouter(prefix="/decks", tags=["decks"])


async def _load_deck(session: AsyncSession, user: AppUser, deck_id: uuid.UUID) -> Deck:
    deck = (await session.execute(select(Deck).where(Deck.id == deck_id))).scalar_one_or_none()
    if deck is None or deck.workspace_id != user.workspace_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="deck not found")
    return deck


async def _deck_out(session: AsyncSession, deck: Deck) -> DeckOut:
    await session.refresh(deck)
    slides = await service.list_slides(session, deck.id)
    sections = await service.list_sections(session, deck.id)
    placements = await service.load_widget_placements(session, [s.id for s in slides])
    slide_outs = []
    for s in slides:
        out = SlideOut.model_validate(s)
        out.widgets = [SlideWidgetEmbed(**p) for p in placements.get(s.id, [])]
        slide_outs.append(out)
    return DeckOut(
        id=deck.id,
        title=deck.title,
        subtitle=deck.subtitle,
        cover=deck.cover,
        manifest=deck.manifest or {},
        created_at=deck.created_at,
        updated_at=deck.updated_at,
        sections=[SectionOut.model_validate(s) for s in sections],
        slides=slide_outs,
    )


@router.get("", response_model=list[DeckListItem])
async def list_decks(
    user: AppUser = Depends(current_user),
    session: AsyncSession = Depends(db_session),
) -> list[DeckListItem]:
    slide_counts = (
        select(Slide.deck_id, func.count(Slide.id).label("slide_count"))
        .group_by(Slide.deck_id)
        .subquery()
    )
    rows = await session.execute(
        select(Deck, func.coalesce(slide_counts.c.slide_count, 0))
        .where(Deck.workspace_id == user.workspace_id, Deck.owner_id == user.id)
        .outerjoin(slide_counts, slide_counts.c.deck_id == Deck.id)
        .order_by(Deck.updated_at.desc())
    )
    deck_rows = rows.all()
    first_slides: dict[uuid.UUID, Slide] = {}
    deck_ids = [deck.id for deck, _count in deck_rows]
    if deck_ids:
        slide_rows = await session.execute(
            select(Slide)
            .where(Slide.deck_id.in_(deck_ids))
            .order_by(Slide.deck_id, Slide.position)
        )
        for slide in slide_rows.scalars().all():
            first_slides.setdefault(slide.deck_id, slide)

    out: list[DeckListItem] = []
    for deck, count in deck_rows:
        first_slide = first_slides.get(deck.id)
        out.append(
            DeckListItem(
                id=deck.id,
                title=deck.title,
                subtitle=deck.subtitle,
                cover=deck.cover,
                updated_at=deck.updated_at,
                slide_count=int(count or 0),
                preview_kicker=first_slide.kicker if first_slide else None,
                preview_markdown=first_slide.markdown if first_slide else None,
            )
        )
    return out


@router.post("", response_model=DeckOut, status_code=status.HTTP_201_CREATED)
async def create_deck(
    body: DeckCreate,
    user: AppUser = Depends(current_user),
    session: AsyncSession = Depends(db_session),
) -> DeckOut:
    deck = Deck(
        workspace_id=user.workspace_id,
        owner_id=user.id,
        title=(body.title or "Untitled").strip() or "Untitled",
        subtitle=(body.subtitle or None),
    )
    session.add(deck)
    await session.flush()
    section = Section(deck_id=deck.id, title="Untitled section", position=0)
    session.add(section)
    await session.flush()
    slide = Slide(deck_id=deck.id, section_id=section.id, position=0, markdown="# Untitled\n")
    session.add(slide)
    await session.flush()
    return await _deck_out(session, deck)


@router.get("/{deck_id}", response_model=DeckOut)
async def get_deck(
    deck_id: uuid.UUID,
    user: AppUser = Depends(current_user),
    session: AsyncSession = Depends(db_session),
) -> DeckOut:
    deck = await _load_deck(session, user, deck_id)
    return await _deck_out(session, deck)


@router.patch("/{deck_id}", response_model=DeckOut)
async def patch_deck(
    deck_id: uuid.UUID,
    body: DeckPatch,
    user: AppUser = Depends(current_user),
    session: AsyncSession = Depends(db_session),
) -> DeckOut:
    deck = await _load_deck(session, user, deck_id)
    if body.title is not None:
        deck.title = body.title.strip() or deck.title
    if body.subtitle is not None:
        deck.subtitle = body.subtitle or None
    if body.cover is not None:
        deck.cover = body.cover or None
    if body.manifest is not None:
        deck.manifest = body.manifest
    await session.flush()
    return await _deck_out(session, deck)


@router.delete("/{deck_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_deck(
    deck_id: uuid.UUID,
    user: AppUser = Depends(current_user),
    session: AsyncSession = Depends(db_session),
) -> Response:
    deck = await _load_deck(session, user, deck_id)
    await service.delete_deck(session, deck)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{deck_id}/duplicate", response_model=DeckOut)
async def duplicate_deck(
    deck_id: uuid.UUID,
    user: AppUser = Depends(current_user),
    session: AsyncSession = Depends(db_session),
) -> DeckOut:
    deck = await _load_deck(session, user, deck_id)
    sections = await service.list_sections(session, deck.id)
    slides = await service.list_slides(session, deck.id)
    copy = Deck(
        workspace_id=deck.workspace_id,
        owner_id=user.id,
        title=f"{deck.title} (copy)",
        subtitle=deck.subtitle,
        cover=deck.cover,
        manifest=deck.manifest or {},
    )
    session.add(copy)
    await session.flush()
    section_map: dict[uuid.UUID, uuid.UUID] = {}
    for s in sections:
        new_section = Section(deck_id=copy.id, title=s.title, position=s.position)
        session.add(new_section)
        await session.flush()
        section_map[s.id] = new_section.id
    for sl in slides:
        new_section_id = section_map.get(sl.section_id) if sl.section_id else None
        session.add(
            Slide(
                deck_id=copy.id,
                section_id=new_section_id,
                position=sl.position,
                kicker=sl.kicker,
                markdown=sl.markdown,
            )
        )
    await session.flush()
    return await _deck_out(session, copy)


@router.post("/{deck_id}/slides", response_model=SlideOut, status_code=status.HTTP_201_CREATED)
async def create_slide(
    deck_id: uuid.UUID,
    body: SlideCreate,
    user: AppUser = Depends(current_user),
    session: AsyncSession = Depends(db_session),
) -> SlideOut:
    deck = await _load_deck(session, user, deck_id)
    slides = await service.list_slides(session, deck.id)
    position = body.position if body.position is not None else len(slides)
    position = max(0, min(position, len(slides)))
    slide = await service.insert_slide(
        session, deck, position, markdown=body.markdown or "", kicker=body.kicker, section_id=body.section_id
    )
    return SlideOut.model_validate(slide)


@router.put("/{deck_id}/slides/{slide_id}", response_model=SlideMutationResult)
async def update_slide(
    deck_id: uuid.UUID,
    slide_id: uuid.UUID,
    body: SlideUpdate,
    user: AppUser = Depends(current_user),
    session: AsyncSession = Depends(db_session),
) -> SlideMutationResult:
    deck = await _load_deck(session, user, deck_id)
    slide = (
        await session.execute(select(Slide).where(Slide.id == slide_id, Slide.deck_id == deck.id))
    ).scalar_one_or_none()
    if slide is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="slide not found")
    affected = await service.replace_slide_markdown(session, slide, body.markdown, body.kicker)
    return SlideMutationResult(slides=[SlideOut.model_validate(s) for s in affected])


async def _load_section(
    session: AsyncSession, deck: Deck, section_id: uuid.UUID
) -> Section:
    section = (
        await session.execute(
            select(Section).where(Section.id == section_id, Section.deck_id == deck.id)
        )
    ).scalar_one_or_none()
    if section is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="section not found")
    return section


@router.post(
    "/{deck_id}/sections",
    response_model=SectionOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_section(
    deck_id: uuid.UUID,
    body: SectionCreate,
    user: AppUser = Depends(current_user),
    session: AsyncSession = Depends(db_session),
) -> SectionOut:
    deck = await _load_deck(session, user, deck_id)
    title = body.title.strip()
    if not title:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="title is required")
    section = await service.insert_section(session, deck, title=title, position=body.position)
    return SectionOut.model_validate(section)


@router.patch("/{deck_id}/sections/{section_id}", response_model=SectionOut)
async def patch_section(
    deck_id: uuid.UUID,
    section_id: uuid.UUID,
    body: SectionPatch,
    user: AppUser = Depends(current_user),
    session: AsyncSession = Depends(db_session),
) -> SectionOut:
    deck = await _load_deck(session, user, deck_id)
    section = await _load_section(session, deck, section_id)
    section = await service.update_section(
        session, section, title=body.title, position=body.position
    )
    return SectionOut.model_validate(section)


@router.delete("/{deck_id}/sections/{section_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_section(
    deck_id: uuid.UUID,
    section_id: uuid.UUID,
    user: AppUser = Depends(current_user),
    session: AsyncSession = Depends(db_session),
) -> Response:
    deck = await _load_deck(session, user, deck_id)
    section = await _load_section(session, deck, section_id)
    await service.delete_section(session, section)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{deck_id}/sections/reorder", response_model=list[SectionOut])
async def reorder_sections(
    deck_id: uuid.UUID,
    body: SectionReorder,
    user: AppUser = Depends(current_user),
    session: AsyncSession = Depends(db_session),
) -> list[SectionOut]:
    deck = await _load_deck(session, user, deck_id)
    try:
        sections = await service.reorder_sections(session, deck, body.order)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return [SectionOut.model_validate(s) for s in sections]


@router.post("/{deck_id}/slides/reorder", response_model=list[SlideOut])
async def reorder_slides(
    deck_id: uuid.UUID,
    body: SlideReorder,
    user: AppUser = Depends(current_user),
    session: AsyncSession = Depends(db_session),
) -> list[SlideOut]:
    deck = await _load_deck(session, user, deck_id)
    try:
        slides = await service.reorder_slides(
            session, deck, [(entry.id, entry.section_id) for entry in body.order]
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    placements = await service.load_widget_placements(session, [s.id for s in slides])
    out: list[SlideOut] = []
    for s in slides:
        item = SlideOut.model_validate(s)
        item.widgets = [SlideWidgetEmbed(**p) for p in placements.get(s.id, [])]
        out.append(item)
    return out


@router.delete("/{deck_id}/slides/{slide_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_slide(
    deck_id: uuid.UUID,
    slide_id: uuid.UUID,
    user: AppUser = Depends(current_user),
    session: AsyncSession = Depends(db_session),
) -> Response:
    deck = await _load_deck(session, user, deck_id)
    slide = (
        await session.execute(select(Slide).where(Slide.id == slide_id, Slide.deck_id == deck.id))
    ).scalar_one_or_none()
    if slide is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="slide not found")
    await service.delete_slide(session, slide)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{deck_id}/export")
async def export_deck(
    deck_id: uuid.UUID,
    user: AppUser = Depends(current_user),
    session: AsyncSession = Depends(db_session),
) -> Response:
    deck = await _load_deck(session, user, deck_id)
    sections = await service.list_sections(session, deck.id)
    slides = await service.list_slides(session, deck.id)
    packed = package.Packaged(
        title=deck.title,
        subtitle=deck.subtitle,
        manifest=deck.manifest or {},
        sections=[package.PackagedSection(title=s.title, position=s.position) for s in sections],
        slides=[
            package.PackagedSlide(position=s.position, kicker=s.kicker, markdown=s.markdown)
            for s in slides
        ],
    )
    body = package.pack(packed)
    safe_title = (deck.title or "deck").replace("/", "-")
    return Response(
        content=body,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{safe_title}.slaides"'},
    )


import_router = APIRouter(prefix="/decks", tags=["decks"])


@import_router.post("/import", response_model=DeckOut, status_code=status.HTTP_201_CREATED)
async def import_deck(
    file: UploadFile = File(...),
    user: AppUser = Depends(current_user),
    session: AsyncSession = Depends(db_session),
) -> DeckOut:
    data = await file.read()
    try:
        packed = package.unpack(data)
    except (ValueError, Exception) as exc:  # noqa: BLE001
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"invalid .slaides archive: {exc}") from exc
    deck = Deck(
        workspace_id=user.workspace_id,
        owner_id=user.id,
        title=packed.title,
        subtitle=packed.subtitle,
        manifest=packed.manifest or {},
    )
    session.add(deck)
    await session.flush()
    section_objs: list[Section] = []
    for s in packed.sections:
        section_objs.append(Section(deck_id=deck.id, title=s.title, position=s.position))
    session.add_all(section_objs)
    await session.flush()
    default_section = section_objs[0].id if section_objs else None
    for s in packed.slides:
        session.add(
            Slide(
                deck_id=deck.id,
                section_id=default_section,
                position=s.position,
                kicker=s.kicker,
                markdown=s.markdown,
            )
        )
    await session.flush()
    return await _deck_out(session, deck)
