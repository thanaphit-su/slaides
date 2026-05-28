from __future__ import annotations

import io
import json
import re
import uuid
import zipfile
from dataclasses import dataclass


@dataclass
class PackagedSlide:
    position: int
    kicker: str | None
    markdown: str


@dataclass
class PackagedSection:
    title: str
    position: int


@dataclass
class Packaged:
    title: str
    subtitle: str | None
    manifest: dict
    sections: list[PackagedSection]
    slides: list[PackagedSlide]


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
        manifest = {
            "title": packed.title,
            "subtitle": packed.subtitle,
            "manifest": packed.manifest,
            "sections": [{"title": s.title, "position": s.position} for s in packed.sections],
            "format_version": "0.1",
        }
        zf.writestr("deck.json", json.dumps(manifest, indent=2))
        for s in packed.slides:
            filename = f"slides/{s.position:02d}-{_slug(_first_h1(s.markdown))}.md"
            body = ""
            if s.kicker:
                body += f"<!-- kicker: {s.kicker} -->\n"
            body += s.markdown
            if not body.endswith("\n"):
                body += "\n"
            zf.writestr(filename, body)
    return buf.getvalue()


def unpack(data: bytes) -> Packaged:
    buf = io.BytesIO(data)
    with zipfile.ZipFile(buf, "r") as zf:
        try:
            manifest = json.loads(zf.read("deck.json").decode("utf-8"))
        except KeyError as exc:
            raise ValueError("missing deck.json in .slaides archive") from exc
        slide_entries = sorted(
            (n for n in zf.namelist() if n.startswith("slides/") and n.endswith(".md")),
            key=lambda n: n,
        )
        slides: list[PackagedSlide] = []
        for idx, name in enumerate(slide_entries):
            raw = zf.read(name).decode("utf-8")
            kicker, body = _extract_kicker(raw)
            slides.append(PackagedSlide(position=idx, kicker=kicker, markdown=body))
        sections_raw = manifest.get("sections") or []
        sections = [
            PackagedSection(title=str(s.get("title", "Untitled")), position=int(s.get("position", i)))
            for i, s in enumerate(sections_raw)
        ]
        return Packaged(
            title=str(manifest.get("title", "Untitled")),
            subtitle=manifest.get("subtitle"),
            manifest=manifest.get("manifest") or {},
            sections=sections,
            slides=slides,
        )


def _extract_kicker(raw: str) -> tuple[str | None, str]:
    line, _, rest = raw.partition("\n")
    m = re.match(r"^\s*<!--\s*kicker:\s*(.*?)\s*-->\s*$", line)
    if m:
        return m.group(1) or None, rest
    return None, raw
