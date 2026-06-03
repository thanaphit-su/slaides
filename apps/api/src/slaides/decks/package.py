from __future__ import annotations

import io
import json
import re
import zipfile
from dataclasses import dataclass


@dataclass
class PackagedSlide:
    position: int
    kicker: str | None
    markdown: str
    key: str | None = None
    section_key: str | None = None


@dataclass
class PackagedSection:
    title: str
    position: int
    key: str | None = None


@dataclass
class PackagedWidget:
    key: str
    name: str
    kind: str
    description: str | None
    tags: list[str]
    version: str
    derived_from_key: str | None
    current_revision_key: str | None


@dataclass
class PackagedWidgetRevision:
    key: str
    widget_key: str
    version_number: int
    html: str
    js: str | None
    css: str | None
    props_schema: dict
    example_props: dict
    behavior: dict
    ai_spec: dict
    created_reason: str | None


@dataclass
class PackagedPlacement:
    slide_key: str
    placement_id: str
    widget_key: str
    revision_key: str | None
    props: dict
    position: int


@dataclass
class Packaged:
    title: str
    subtitle: str | None
    manifest: dict
    sections: list[PackagedSection]
    slides: list[PackagedSlide]
    widgets: list[PackagedWidget] | None = None
    widget_revisions: list[PackagedWidgetRevision] | None = None
    placements: list[PackagedPlacement] | None = None
    excluded: dict | None = None


_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _slug(text: str) -> str:
    s = _SLUG_RE.sub("-", (text or "untitled").lower()).strip("-")
    return s[:60] or "slide"


def _first_h1(markdown: str) -> str:
    for line in markdown.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return "untitled"


def pack(packed: Packaged) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        slide_entries = []
        for idx, s in enumerate(packed.slides):
            key = s.key or f"slide-{idx}"
            filename = f"slides/{s.position:02d}-{_slug(_first_h1(s.markdown))}.md"
            slide_entries.append(
                {
                    "key": key,
                    "file": filename,
                    "position": s.position,
                    "section_key": s.section_key,
                    "kicker": s.kicker,
                }
            )
            body = ""
            if s.kicker:
                body += f"<!-- kicker: {s.kicker} -->\n"
            body += s.markdown
            if not body.endswith("\n"):
                body += "\n"
            zf.writestr(filename, body)
        manifest = {
            "title": packed.title,
            "subtitle": packed.subtitle,
            "manifest": packed.manifest,
            "sections": [
                {"key": s.key or f"section-{i}", "title": s.title, "position": s.position}
                for i, s in enumerate(packed.sections)
            ],
            "slides": slide_entries,
            "widgets": [w.__dict__ for w in (packed.widgets or [])],
            "widget_revisions": [r.__dict__ for r in (packed.widget_revisions or [])],
            "placements": [p.__dict__ for p in (packed.placements or [])],
            "excluded": packed.excluded or {"widget_ai_threads": True},
            "format_version": "0.2",
        }
        zf.writestr("deck.json", json.dumps(manifest, indent=2))
    return buf.getvalue()


def unpack(data: bytes) -> Packaged:
    buf = io.BytesIO(data)
    with zipfile.ZipFile(buf, "r") as zf:
        try:
            manifest = json.loads(zf.read("deck.json").decode("utf-8"))
        except KeyError as exc:
            raise ValueError("missing deck.json in .slaides archive") from exc
        if manifest.get("format_version") == "0.2":
            sections = [
                PackagedSection(
                    key=str(s.get("key") or f"section-{i}"),
                    title=str(s.get("title", "Untitled")),
                    position=int(s.get("position", i)),
                )
                for i, s in enumerate(manifest.get("sections") or [])
            ]
            slides: list[PackagedSlide] = []
            for i, s in enumerate(manifest.get("slides") or []):
                filename = str(s.get("file") or "")
                raw = zf.read(filename).decode("utf-8")
                file_kicker, body = _extract_kicker(raw)
                slides.append(
                    PackagedSlide(
                        key=str(s.get("key") or f"slide-{i}"),
                        position=int(s.get("position", i)),
                        section_key=s.get("section_key"),
                        kicker=s.get("kicker") if s.get("kicker") is not None else file_kicker,
                        markdown=body,
                    )
                )
            return Packaged(
                title=str(manifest.get("title", "Untitled")),
                subtitle=manifest.get("subtitle"),
                manifest=manifest.get("manifest") or {},
                sections=sections,
                slides=slides,
                widgets=[PackagedWidget(**w) for w in (manifest.get("widgets") or [])],
                widget_revisions=[
                    PackagedWidgetRevision(**r) for r in (manifest.get("widget_revisions") or [])
                ],
                placements=[PackagedPlacement(**p) for p in (manifest.get("placements") or [])],
                excluded=manifest.get("excluded") or {},
            )
        slide_entries = sorted(
            (n for n in zf.namelist() if n.startswith("slides/") and n.endswith(".md")),
            key=lambda n: n,
        )
        slides: list[PackagedSlide] = []
        for idx, name in enumerate(slide_entries):
            raw = zf.read(name).decode("utf-8")
            kicker, body = _extract_kicker(raw)
            slides.append(PackagedSlide(key=f"slide-{idx}", position=idx, kicker=kicker, markdown=body))
        sections_raw = manifest.get("sections") or []
        sections = [
            PackagedSection(
                key=f"section-{i}",
                title=str(s.get("title", "Untitled")),
                position=int(s.get("position", i)),
            )
            for i, s in enumerate(sections_raw)
        ]
        return Packaged(
            title=str(manifest.get("title", "Untitled")),
            subtitle=manifest.get("subtitle"),
            manifest=manifest.get("manifest") or {},
            sections=sections,
            slides=slides,
            widgets=[],
            widget_revisions=[],
            placements=[],
            excluded={},
        )


def _extract_kicker(raw: str) -> tuple[str | None, str]:
    line, _, rest = raw.partition("\n")
    m = re.match(r"^\s*<!--\s*kicker:\s*(.*?)\s*-->\s*$", line)
    if m:
        return m.group(1) or None, rest
    return None, raw
