from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth.deps import current_user
from ..db.deps import db_session
from ..db.models import AppUser, Deck, Section, Slide, SlideWidget, Widget, WidgetRevision
from ..db.models import Session as SessionRow
from ..sessions import service as session_service
from ..sessions.ws import hub as session_ws_hub
from . import package, service
from .schemas import (
    DeckCreate,
    DeckListItem,
    DeckOut,
    DeckPatch,
    MirrorAccessSettings,
    SectionCreate,
    SectionOut,
    SectionPatch,
    SectionReorder,
    SlideCreate,
    SlideMutationResult,
    SlideNotesUpdate,
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


async def _load_owned_deck(session: AsyncSession, user: AppUser, deck_id: uuid.UUID) -> Deck:
    deck = await _load_deck(session, user, deck_id)
    if deck.owner_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="deck not found")
    return deck


async def _deck_out(session: AsyncSession, deck: Deck) -> DeckOut:
    await session.refresh(deck)
    slides = await service.list_slides(session, deck.id)
    sections = await service.list_sections(session, deck.id)
    slide_outs = await _slides_out_with_widgets(session, slides)
    return DeckOut(
        id=deck.id,
        title=deck.title,
        subtitle=deck.subtitle,
        cover=deck.cover,
        manifest=deck.manifest or {},
        created_at=deck.created_at,
        updated_at=deck.updated_at,
        mirror_access=MirrorAccessSettings(
            mode=deck.mirror_access_mode or "owner",
            allowed_emails=list(deck.mirror_allowed_emails or []),
        ),
        sections=[SectionOut.model_validate(s) for s in sections],
        slides=slide_outs,
    )


async def _slides_out_with_widgets(session: AsyncSession, slides: list[Slide]) -> list[SlideOut]:
    placements = await service.load_widget_placements(session, [s.id for s in slides])
    slide_outs = []
    for s in slides:
        out = SlideOut.model_validate(s)
        out.widgets = [SlideWidgetEmbed(**p) for p in placements.get(s.id, [])]
        slide_outs.append(out)
    return slide_outs


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


@router.patch("/{deck_id}/mirror-access", response_model=MirrorAccessSettings)
async def update_mirror_access(
    deck_id: uuid.UUID,
    body: MirrorAccessSettings,
    user: AppUser = Depends(current_user),
    session: AsyncSession = Depends(db_session),
) -> MirrorAccessSettings:
    deck = await _load_owned_deck(session, user, deck_id)
    settings = MirrorAccessSettings.model_validate(body.model_dump())
    prior_mode = deck.mirror_access_mode or "owner"
    prior_allowed = list(deck.mirror_allowed_emails or [])
    access_changed = prior_mode != settings.mode or prior_allowed != (
        settings.allowed_emails if settings.mode == "allowed" else []
    )
    active_session_ids: list[uuid.UUID] = []
    if access_changed:
        active_sessions = (
            await session.execute(
                select(SessionRow).where(
                    SessionRow.deck_id == deck.id,
                    SessionRow.ended_at.is_(None),
                )
            )
        ).scalars().all()
        for row in active_sessions:
            row.mirror_token = session_service.generate_mirror_token()
            active_session_ids.append(row.id)
    deck.mirror_access_mode = settings.mode
    deck.mirror_allowed_emails = settings.allowed_emails if settings.mode == "allowed" else []
    await session.flush()
    if active_session_ids:
        await session_ws_hub.close_role_for_sessions(active_session_ids, "mirror")
    return MirrorAccessSettings(
        mode=deck.mirror_access_mode,
        allowed_emails=list(deck.mirror_allowed_emails or []),
    )


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
                presenter_notes=sl.presenter_notes,
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
    return SlideMutationResult(slides=await _slides_out_with_widgets(session, affected))


@router.patch("/{deck_id}/slides/{slide_id}/notes", response_model=SlideOut)
async def update_slide_notes(
    deck_id: uuid.UUID,
    slide_id: uuid.UUID,
    body: SlideNotesUpdate,
    user: AppUser = Depends(current_user),
    session: AsyncSession = Depends(db_session),
) -> SlideOut:
    deck = await _load_deck(session, user, deck_id)
    slide = (
        await session.execute(select(Slide).where(Slide.id == slide_id, Slide.deck_id == deck.id))
    ).scalar_one_or_none()
    if slide is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="slide not found")
    slide.presenter_notes = body.presenter_notes
    await session.flush()
    await session.refresh(slide)
    return (await _slides_out_with_widgets(session, [slide]))[0]


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
    return await _slides_out_with_widgets(session, slides)


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
    section_key_by_id = {s.id: f"section-{i}" for i, s in enumerate(sections)}
    slide_key_by_id = {s.id: f"slide-{i}" for i, s in enumerate(slides)}
    placement_rows = (
        await session.execute(
            select(SlideWidget, Widget, WidgetRevision)
            .join(Widget, Widget.id == SlideWidget.widget_id)
            .outerjoin(WidgetRevision, WidgetRevision.id == SlideWidget.revision_id)
            .where(SlideWidget.slide_id.in_([s.id for s in slides]))
            .order_by(SlideWidget.position)
        )
    ).all()
    widget_by_id: dict[uuid.UUID, Widget] = {}
    revision_by_id: dict[uuid.UUID, WidgetRevision] = {}
    for link, widget, revision in placement_rows:
        widget_by_id[widget.id] = widget
        if revision is not None:
            revision_by_id[revision.id] = revision

    current_revision_ids = {
        w.current_revision_id
        for w in widget_by_id.values()
        if w.current_revision_id is not None
    }
    missing_current_revision_ids = current_revision_ids - set(revision_by_id)
    if missing_current_revision_ids:
        current_revisions = (
            await session.execute(
                select(WidgetRevision).where(
                    WidgetRevision.id.in_(missing_current_revision_ids)
                )
            )
        ).scalars()
        for revision in current_revisions:
            revision_by_id[revision.id] = revision

    widget_key_by_id = {widget_id: f"widget-{i}" for i, widget_id in enumerate(widget_by_id)}
    revision_key_by_id = {
        revision_id: f"revision-{i}" for i, revision_id in enumerate(revision_by_id)
    }
    packed = package.Packaged(
        title=deck.title,
        subtitle=deck.subtitle,
        manifest=deck.manifest or {},
        sections=[
            package.PackagedSection(
                key=section_key_by_id[s.id],
                title=s.title,
                position=s.position,
            )
            for s in sections
        ],
        slides=[
            package.PackagedSlide(
                key=slide_key_by_id[s.id],
                position=s.position,
                section_key=section_key_by_id.get(s.section_id) if s.section_id else None,
                kicker=s.kicker,
                markdown=s.markdown,
                presenter_notes=s.presenter_notes,
            )
            for s in slides
        ],
        widgets=[
            package.PackagedWidget(
                key=widget_key_by_id[w.id],
                name=w.name,
                kind=w.kind,
                description=w.description,
                tags=list(w.tags or []),
                version=w.version,
                derived_from_key=None,
                current_revision_key=(
                    revision_key_by_id.get(w.current_revision_id)
                    if w.current_revision_id
                    else None
                ),
            )
            for w in widget_by_id.values()
        ],
        widget_revisions=[
            package.PackagedWidgetRevision(
                key=revision_key_by_id[r.id],
                widget_key=widget_key_by_id[r.widget_id],
                version_number=r.version_number,
                html=r.html or "",
                js=r.js,
                css=r.css,
                props_schema=r.props_schema or {},
                example_props=r.example_props or {},
                behavior=r.behavior or {"kind": "quiet"},
                ai_spec=r.ai_spec or {},
                created_reason=r.created_reason,
            )
            for r in revision_by_id.values()
        ],
        placements=[
            package.PackagedPlacement(
                slide_key=slide_key_by_id[link.slide_id],
                placement_id=link.placement_id,
                widget_key=widget_key_by_id[link.widget_id],
                revision_key=revision_key_by_id.get(link.revision_id) if link.revision_id else None,
                props=link.props or {},
                position=link.position,
            )
            for link, _widget, _revision in placement_rows
        ],
        excluded={"widget_ai_threads": True},
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
    section_by_key: dict[str, Section] = {}
    for i, s in enumerate(packed.sections):
        key = s.key or f"section-{i}"
        section = Section(deck_id=deck.id, title=s.title, position=s.position)
        section_by_key[key] = section
        session.add(section)
    await session.flush()
    slide_by_key: dict[str, Slide] = {}
    for i, s in enumerate(packed.slides):
        key = s.key or f"slide-{i}"
        slide = Slide(
            deck_id=deck.id,
            section_id=section_by_key[s.section_key].id if s.section_key in section_by_key else None,
            position=s.position,
            kicker=s.kicker,
            markdown=s.markdown,
            presenter_notes=s.presenter_notes,
        )
        slide_by_key[key] = slide
        session.add(slide)
    await session.flush()

    widget_by_key: dict[str, Widget] = {}
    for w in packed.widgets or []:
        widget = Widget(
            deck_id=deck.id,
            derived_from_id=None,
            name=w.name,
            kind=w.kind,
            description=w.description,
            html="",
            js=None,
            css=None,
            props_schema={},
            tags=list(w.tags or []),
            version=w.version,
            behavior={"kind": "quiet"},
        )
        widget_by_key[w.key] = widget
        session.add(widget)
    await session.flush()

    revision_by_key: dict[str, WidgetRevision] = {}
    for r in packed.widget_revisions or []:
        widget = widget_by_key.get(r.widget_key)
        if widget is None:
            continue
        revision = WidgetRevision(
            widget_id=widget.id,
            version_number=r.version_number,
            html=r.html or "",
            js=r.js,
            css=r.css,
            props_schema=r.props_schema or {},
            example_props=r.example_props or {},
            behavior=r.behavior or {"kind": "quiet"},
            ai_spec=r.ai_spec or {},
            created_reason=r.created_reason or "import",
        )
        revision_by_key[r.key] = revision
        session.add(revision)
    await session.flush()

    for w in packed.widgets or []:
        widget = widget_by_key[w.key]
        revision = revision_by_key.get(w.current_revision_key or "")
        if revision is not None:
            widget.current_revision_id = revision.id
            widget.html = revision.html
            widget.js = revision.js
            widget.css = revision.css
            widget.props_schema = revision.props_schema
            widget.behavior = revision.behavior
    await session.flush()

    for p in packed.placements or []:
        slide = slide_by_key.get(p.slide_key)
        widget = widget_by_key.get(p.widget_key)
        if slide is None or widget is None:
            continue
        revision = revision_by_key.get(p.revision_key or "")
        session.add(
            SlideWidget(
                slide_id=slide.id,
                placement_id=p.placement_id,
                widget_id=widget.id,
                revision_id=revision.id if revision is not None else None,
                props=p.props or {},
                position=p.position,
            )
        )
    await session.flush()
    return await _deck_out(session, deck)
