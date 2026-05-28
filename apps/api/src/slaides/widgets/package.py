from __future__ import annotations

import json
import re
from dataclasses import dataclass


FRONTMATTER_RE = re.compile(
    r"^\s*<!--\s*slaides-widget\s*\n(?P<body>.*?)\n-->\s*",
    re.DOTALL,
)


@dataclass
class WidgetFile:
    name: str
    kind: str
    description: str | None
    html: str
    js: str | None
    css: str | None
    props_schema: dict
    example_props: dict
    behavior: dict
    ai_spec: dict
    tags: list[str]
    version: str


def pack(w: WidgetFile) -> bytes:
    """Serialise a widget as a .swidget file: an HTML document with a JSON
    frontmatter comment up top.
    """
    front = {
        "name": w.name,
        "kind": w.kind,
        "description": w.description,
        "props_schema": w.props_schema,
        "example_props": w.example_props,
        "behavior": w.behavior,
        "ai_spec": w.ai_spec,
        "tags": w.tags,
        "version": w.version,
    }
    out = [
        "<!-- slaides-widget",
        json.dumps(front, indent=2),
        "-->",
        w.html or "",
    ]
    if w.css:
        out.append(f"<style>\n{w.css}\n</style>")
    if w.js:
        out.append(f"<script>\n{w.js}\n</script>")
    return ("\n".join(out) + "\n").encode("utf-8")


def unpack(data: bytes) -> WidgetFile:
    text = data.decode("utf-8")
    m = FRONTMATTER_RE.search(text)
    if not m:
        raise ValueError("widget file missing slaides-widget frontmatter")
    front = json.loads(m.group("body"))
    body = text[m.end():]
    css = _extract_block(body, "style")
    js = _extract_block(body, "script")
    html = _strip_block(body, "style")
    html = _strip_block(html, "script").strip()
    return WidgetFile(
        name=str(front.get("name", "Untitled widget")),
        kind=str(front.get("kind", "custom")),
        description=front.get("description"),
        html=html,
        js=js,
        css=css,
        props_schema=front.get("props_schema") or {},
        example_props=front.get("example_props") or {},
        behavior=front.get("behavior") or {"kind": "quiet"},
        ai_spec=front.get("ai_spec") or {},
        tags=list(front.get("tags") or []),
        version=str(front.get("version", "v0.1")),
    )


def _extract_block(text: str, tag: str) -> str | None:
    m = re.search(rf"<{tag}[^>]*>(.*?)</{tag}>", text, re.DOTALL | re.IGNORECASE)
    return m.group(1).strip() if m else None


def _strip_block(text: str, tag: str) -> str:
    return re.sub(rf"<{tag}[^>]*>.*?</{tag}>", "", text, flags=re.DOTALL | re.IGNORECASE)
