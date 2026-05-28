from __future__ import annotations

import hashlib
import json
import re
import time
import uuid
from collections.abc import AsyncIterator

import httpx
from fastapi import HTTPException, status
from redis import asyncio as aioredis
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.models import AppUser, LlmCall, Workspace
from ..settings import get_settings
from .crypto import decrypt_workspace_secret
from .schemas import LlmCompleteRequest

# Detects hardcoded color literals — hex (`#fff`, `#0b0d10`, `#0b0d10ff`),
# functional notations (`rgb(...)`, `rgba(...)`, `hsl(...)`, `hsla(...)`).
_HEX_COLOR = re.compile(r"#[0-9a-fA-F]{3}(?:[0-9a-fA-F]{3,5})?\b")
_FUNCTIONAL_COLOR = re.compile(r"\b(?:rgb|rgba|hsl|hsla)\s*\(")

# Detects CSS named-color keywords used as the value side of a color-bearing
# property (e.g. `color: white`, `background-color: red`). Anchoring on the
# property name keeps content text like the literal word "red" inside a poll
# choice from triggering. The keyword list is CSS Level 2 basic colors plus
# the most-likely-to-appear extended set; the full ~150-name CSS4 list adds
# false-positive risk without catching anything the model actually emits.
_NAMED_COLOR_PROPS = (
    r"(?:color|background(?:-color)?|border(?:-[a-z]+)*|outline(?:-color)?|"
    r"fill|stroke|caret-color|box-shadow|text-shadow)"
)
_NAMED_COLOR_KEYWORDS = (
    r"black|silver|gray|grey|white|maroon|red|purple|fuchsia|magenta|green|"
    r"lime|olive|yellow|navy|blue|teal|aqua|cyan|orange|pink|brown|gold|"
    r"transparent"
)
_NAMED_COLOR = re.compile(
    # Anchor the property to a CSS-declaration boundary: start-of-string, `{`,
    # `;`, a quote (for inline style="..."), or a newline. Without this, prose
    # like "Pick a color: red" would trigger.
    rf"(?:^|[{{;\"']|\n)\s*{_NAMED_COLOR_PROPS}\s*:\s*[^;{{}}]*?"
    rf"\b(?P<name>{_NAMED_COLOR_KEYWORDS})\b",
    re.IGNORECASE | re.MULTILINE,
)

# Detects hardcoded font-family strings the AI keeps emitting alongside the
# tokens. Match well-known family names regardless of quoting.
_FONT_FAMILY_LITERAL = re.compile(
    r"font-family\s*:\s*[^;{}]*?"  # the value side of font-family
    r"(?P<name>['\"]?(?:Inter|Newsreader|IBM\s+Plex\s+Mono|Roboto|Helvetica(?:\s+Neue)?|Arial|Georgia|Courier(?:\s+New)?|Times(?:\s+New\s+Roman)?|Segoe\s+UI|San\s+Francisco)['\"]?)",
    re.IGNORECASE,
)

# External resource pulls — sandboxed iframes can't be assumed to have network
# access, and the host already provides fonts. Flag any of them.
_AT_IMPORT = re.compile(r"@import\s+(?:url\()?", re.IGNORECASE)
_LINK_STYLESHEET = re.compile(r"<link[^>]+rel\s*=\s*['\"]?stylesheet", re.IGNORECASE)
_REMOTE_SCRIPT = re.compile(r"<script[^>]+src\s*=\s*['\"]\s*https?://", re.IGNORECASE)

# Generated widgets shouldn't cap their layout to a fixed pixel/em width — the
# host iframe owns the viewport size, and `max-width: 600px` (or similar)
# leaves dead space on either side on wide slides. Allow percentage / viewport
# caps (`max-width: 100%`, `100vw`, `none`) so legitimate "don't overflow the
# container" patterns still work; flag only absolute caps the model tends to
# bake in by reflex.
_LAYOUT_FIXED_MAX_WIDTH = re.compile(
    r"max-width\s*:\s*(?P<value>\d+(?:\.\d+)?(?:px|rem|em|ch))\b",
    re.IGNORECASE,
)


def _scan_theme_violations(text: str, max_samples: int = 4) -> list[str]:
    """Return a list of theme-contract violation messages found in the LLM
    output. Empty list means the output is clean."""
    messages: list[str] = []

    color_samples: list[str] = []
    for match in _HEX_COLOR.finditer(text):
        tok = match.group(0)
        if tok not in color_samples:
            color_samples.append(tok)
        if len(color_samples) >= max_samples:
            break
    if len(color_samples) < max_samples:
        for match in _FUNCTIONAL_COLOR.finditer(text):
            tok = match.group(0).rstrip("(").strip()
            if tok not in color_samples:
                color_samples.append(tok)
            if len(color_samples) >= max_samples:
                break
    if len(color_samples) < max_samples:
        for match in _NAMED_COLOR.finditer(text):
            tok = match.group("name").lower()
            if tok not in color_samples:
                color_samples.append(tok)
            if len(color_samples) >= max_samples:
                break
    if color_samples:
        messages.append(
            "Hardcoded color literals — use var(--background|--primary|--accent|...) instead: "
            + ", ".join(color_samples)
        )

    font_samples: list[str] = []
    for match in _FONT_FAMILY_LITERAL.finditer(text):
        name = match.group("name").strip(" '\"")
        if name not in font_samples:
            font_samples.append(name)
        if len(font_samples) >= max_samples:
            break
    if font_samples:
        messages.append(
            "Hardcoded font-family — use var(--font-sans|--font-serif|--font-mono) instead: "
            + ", ".join(font_samples)
        )

    external_kinds: list[str] = []
    if _AT_IMPORT.search(text):
        external_kinds.append("@import")
    if _LINK_STYLESHEET.search(text):
        external_kinds.append("<link rel=stylesheet>")
    if _REMOTE_SCRIPT.search(text):
        external_kinds.append("<script src=https://...>")
    if external_kinds:
        messages.append(
            "External resource(s) — the iframe is sandboxed and the host already loads fonts/styles. Remove: "
            + ", ".join(external_kinds)
        )

    return messages


def _scan_layout_violations(text: str, max_samples: int = 4) -> list[str]:
    """Flag fixed-pixel `max-width` declarations on widget CSS. The host
    iframe owns the viewport, so a hardcoded `max-width: 600px` cap leaves
    dead space on either side of the widget when it's placed on a wide
    slide. We can't reliably tell "root container" from "nested element"
    without a real CSS parser, so we surface every absolute-unit cap and
    let the user / next iteration sort it out."""
    samples: list[str] = []
    for match in _LAYOUT_FIXED_MAX_WIDTH.finditer(text):
        tok = match.group("value")
        if tok not in samples:
            samples.append(tok)
        if len(samples) >= max_samples:
            break
    if samples:
        return [
            "Fixed widget max-width — the iframe owns the layout; use "
            "`max-width: 100%` (or no cap) so wide slides don't get padded "
            "with dead space on either side. Found: " + ", ".join(samples)
        ]
    return []


_LOUD_AGGREGATORS = {"tally", "latest_per_participant", "append", "set_union", "keyed_tally"}


def _scan_behavior_violations(
    draft_text: str,
    *,
    current: dict | None = None,
) -> list[str]:
    """Widgets v2 Step 4 — flag widgets whose declared behavior doesn't match
    their actual code. Quiet widgets that call `contribute()` and Loud widgets
    that never call `contribute()` are both broken; surface a warning so the
    user can decide before applying.

    In adjust mode, the LLM returns a partial draft (only the fields it's
    changing). Scanning the draft alone would miss the case where the JS is
    rewritten without `contribute()` while the persisted widget stays Loud —
    exactly the dead-Loud state the validator exists to catch. Callers in
    adjust mode pass `current` (the existing widget's `behavior`, `html`,
    `js`); the scan runs against the merged shape.
    """
    messages: list[str] = []

    try:
        draft = _widget_workflow_draft(draft_text) or json.loads(_extract_first_json_object(draft_text))
    except (ValueError, json.JSONDecodeError):
        return messages
    if not isinstance(draft, dict):
        return messages

    merged_source: dict = dict(current) if isinstance(current, dict) else {}
    for key in ("behavior", "js", "html"):
        if key in draft:
            merged_source[key] = draft[key]

    behavior = merged_source.get("behavior")
    js = str(merged_source.get("js") or "")
    html = str(merged_source.get("html") or "")
    body = js + "\n" + html

    has_contribute = "slaides.contribute" in body or ".contribute(" in body
    has_state_subscription = "slaides.on('state'" in body or 'slaides.on("state"' in body

    if not isinstance(behavior, dict):
        if has_contribute:
            messages.append(
                "Widget calls slaides.contribute() but declares no `behavior` — add "
                '`behavior: { "kind": "loud", "aggregator": "<one-of-five>" }`.'
            )
        return messages

    kind = behavior.get("kind")
    if kind == "quiet":
        if has_contribute:
            messages.append(
                "Quiet widget calls slaides.contribute() — that call is rejected at "
                'runtime. Either remove the call or change behavior.kind to "loud".'
            )
        return messages

    if kind == "loud":
        aggregator = behavior.get("aggregator")
        if aggregator not in _LOUD_AGGREGATORS:
            messages.append(
                f"Loud widget declared aggregator {aggregator!r} — must be one of "
                + ", ".join(sorted(_LOUD_AGGREGATORS))
            )
        if not has_contribute:
            messages.append(
                "Loud widget never calls slaides.contribute() — the audience can't "
                "actually contribute to the shared state."
            )
        if not has_state_subscription:
            messages.append(
                "Loud widget never subscribes to slaides.on('state', …) — it will "
                "miss the server-aggregated tally and stay blank for the audience."
            )
        if not isinstance(behavior.get("contribution_schema"), dict):
            messages.append(
                "Loud widget is missing behavior.contribution_schema — declare the "
                "shape the server should expect (e.g. `{ \"type\": \"string\" }`)."
            )
        return messages

    if kind is not None:
        messages.append(f"Unknown behavior.kind {kind!r} — must be 'quiet' or 'loud'.")
    return messages


def _scan_props_contract_violations(draft_text: str) -> list[str]:
    """Surface widgets that declared `props_schema` keys but don't actually
    read them — i.e. hardcoded content in HTML or JS that defeats the
    reusability story. Best-effort heuristic: pulls the JSON draft, looks at
    declared property keys, and warns when none of them are referenced
    anywhere in the assembled JS / HTML."""
    messages: list[str] = []

    try:
        draft = _widget_workflow_draft(draft_text) or json.loads(_extract_first_json_object(draft_text))
    except (ValueError, json.JSONDecodeError):
        return messages
    if not isinstance(draft, dict):
        return messages

    schema = draft.get("props_schema")
    if not isinstance(schema, dict):
        return messages
    properties = schema.get("properties") if isinstance(schema.get("properties"), dict) else schema
    if not isinstance(properties, dict):
        return messages
    declared_keys = [k for k in properties.keys() if isinstance(k, str)]
    if not declared_keys:
        return messages

    js = str(draft.get("js") or "")
    html = str(draft.get("html") or "")
    body = js + "\n" + html

    if not any(needle in body for needle in ("window.slaides.props", "slaides.props", ".props")):
        messages.append(
            "Widget declared props_schema but never reads window.slaides.props. "
            f"Declared keys: {', '.join(declared_keys)}. Move user-visible content into props."
        )
        return messages

    missing = [
        key
        for key in declared_keys
        if key not in body and f'"{key}"' not in body and f"'{key}'" not in body
    ]
    if missing:
        messages.append(
            "Props declared but never read in HTML/JS: " + ", ".join(missing)
        )
    return messages


def _extract_first_json_object(text: str) -> str:
    """Return the first balanced top-level JSON object substring in `text`.

    Models often wrap the JSON in code fences or prose; this is a permissive
    extractor used only for post-stream introspection (failures are silent).
    """
    start = text.find("{")
    if start < 0:
        return ""
    depth = 0
    in_string = False
    escape = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return ""


def _parse_widget_workflow(text: str) -> dict:
    try:
        data = json.loads(_extract_first_json_object(text))
    except json.JSONDecodeError as exc:
        raise ValueError("workflow response must be valid JSON") from exc
    if not isinstance(data, dict):
        raise ValueError("workflow response must be an object")
    kind = data.get("type")
    if kind not in {"question", "plan", "step", "reflection", "draft"}:
        raise ValueError("workflow response type must be question, plan, step, reflection, or draft")
    if kind == "question":
        if not isinstance(data.get("question"), str):
            raise ValueError("question response requires question")
        if not isinstance(data.get("options"), list) or not data["options"]:
            raise ValueError("question response requires options")
    if kind == "draft" and not isinstance(data.get("widget"), dict):
        raise ValueError("draft response requires widget")
    return data


def _widget_workflow_draft(text: str) -> dict | None:
    try:
        workflow = _parse_widget_workflow(text)
    except ValueError:
        return None
    if workflow.get("type") != "draft":
        return None
    widget = workflow.get("widget")
    return widget if isinstance(widget, dict) else None


# Redis client for cross-worker rate limiting. Lazily initialized; tests inject
# fakeredis via `set_redis()` from conftest.
_redis: aioredis.Redis | None = None

# Window keys live ~1.5x the bucket size so consecutive minutes can't collide
# during clock skew while still self-expiring without explicit cleanup.
_RATE_WINDOW_TTL = 90


def set_redis(client: aioredis.Redis | None) -> None:
    global _redis
    _redis = client


async def _get_redis() -> aioredis.Redis:
    global _redis
    if _redis is None:
        _redis = aioredis.from_url(get_settings().redis_url, decode_responses=True)
    return _redis


PURPOSE_LABELS = {
    "inline_write": "Inline content writing",
    "interpret": "Interpret selected text",
    "widget_generate": "Generate a SLAIDES widget",
    "summarise": "Summarise transcript",
}
ROUTABLE_PURPOSES = {"inline_write", "interpret", "widget_generate"}


def _sse(event: str, payload: dict) -> bytes:
    return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n".encode("utf-8")


def _model_library(workspace: Workspace) -> list[dict]:
    raw_models = workspace.llm_models if isinstance(workspace.llm_models, list) else []
    models: list[dict] = []
    seen: set[str] = set()
    for raw in raw_models:
        if not isinstance(raw, dict):
            continue
        model_id = str(raw.get("id") or "").strip()
        if not model_id or model_id in seen:
            continue
        item = dict(raw)
        item["id"] = model_id
        models.append(item)
        seen.add(model_id)
    fallback_id = (workspace.llm_model or "gpt-4.1-mini").strip() or "gpt-4.1-mini"
    if fallback_id not in seen:
        models.insert(0, {"id": fallback_id})
    return models


def _capability_assignments(workspace: Workspace, models: list[dict]) -> dict[str, str | None]:
    raw_assignments = workspace.llm_capability_models if isinstance(workspace.llm_capability_models, dict) else {}
    model_ids = {str(m.get("id")) for m in models}
    fallback = str(workspace.llm_model or (models[0].get("id") if models else "gpt-4.1-mini")).strip()
    if fallback not in model_ids:
        fallback = str(models[0].get("id") if models else "gpt-4.1-mini")
    resolved: dict[str, str | None] = {}
    for purpose in ROUTABLE_PURPOSES:
        if purpose in raw_assignments and raw_assignments[purpose] is None:
            # Explicitly disabled.
            resolved[purpose] = None
            continue
        assigned = raw_assignments.get(purpose)
        resolved[purpose] = assigned if isinstance(assigned, str) and assigned in model_ids else fallback
    return resolved


def _resolve_model(workspace: Workspace, body: LlmCompleteRequest) -> tuple[dict | None, str | None]:
    models = _model_library(workspace)
    by_id = {str(model.get("id")): model for model in models}
    selected_id = body.model_override.strip() if body.model_override else None
    if body.purpose in ROUTABLE_PURPOSES:
        assigned = _capability_assignments(workspace, models).get(body.purpose)
        if assigned is None:
            return None, f"{PURPOSE_LABELS.get(body.purpose, body.purpose)} is disabled"
        selected_id = selected_id or assigned
    else:
        selected_id = selected_id or (workspace.llm_model or (models[0].get("id") if models else "gpt-4.1-mini"))
    selected_id = str(selected_id or "").strip()
    if not selected_id:
        return None, "LLM model is required"
    model = by_id.get(selected_id, {"id": selected_id})
    if body.images and not bool(model.get("supports_image_input")):
        return None, f"{selected_id} is not configured for image input"
    return model, None


def _model_parameters(model: dict) -> dict:
    mapping = {
        "max_output_tokens": "max_tokens",
        "temperature": "temperature",
        "top_p": "top_p",
        "frequency_penalty": "frequency_penalty",
        "presence_penalty": "presence_penalty",
    }
    params: dict = {}
    for local_key, api_key in mapping.items():
        value = model.get(local_key)
        if value is not None and value != "":
            params[api_key] = value
    return params


async def enforce_rate_limit(workspace_id: uuid.UUID, purpose: str, user_id: uuid.UUID | None) -> None:
    """Fixed-window per-minute rate limit, shared across uvicorn workers via Redis.

    Uses INCR + EXPIRE on an epoch-minute bucket key so the window self-expires
    without needing a sliding-window Lua script.
    """
    settings = get_settings()
    redis = await _get_redis()
    bucket = int(time.time() // 60)

    ws_key = f"llm:rate:ws:{workspace_id}:{bucket}"
    ws_count = await redis.incr(ws_key)
    if ws_count == 1:
        await redis.expire(ws_key, _RATE_WINDOW_TTL)
    if ws_count > settings.llm_workspace_rate_limit:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="workspace LLM rate limit exceeded",
        )

    if purpose == "widget_generate" and user_id is not None:
        widget_key = f"llm:rate:widget:{workspace_id}:{user_id}:{bucket}"
        widget_count = await redis.incr(widget_key)
        if widget_count == 1:
            await redis.expire(widget_key, _RATE_WINDOW_TTL)
        if widget_count > settings.llm_widget_user_rate_limit:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="widget generation rate limit exceeded",
            )


def _endpoint(base_url: str) -> str:
    base = base_url.rstrip("/")
    if base.endswith("/chat/completions"):
        return base
    return f"{base}/chat/completions"


WIDGET_THEME_CONTRACT = """\
THEME CONTRACT — REQUIRED. The iframe injects these CSS variables on :root.
You MUST use them with `var(--token)` for ALL colors, fonts, and radii.

Forbidden in html, css, and inline style attributes:
  * Literal color values: hex (`#0f172a`, `#fff`), `rgb(...)`, `rgba(...)`,
    `hsl(...)`, `hsla(...)`, and named CSS colors (white, black, red, etc.).
    There is NO exception. This rule covers:
      - background colors (incl. hover / active / pressed states)
      - text colors
      - border colors
      - box-shadow colors (use `0 4px 6px -1px var(--accent-soft)` or skip the shadow)
      - translucent overlays — for a translucent wash use `background: var(--accent-soft)`
        or `var(--muted)`; do NOT reach for `rgba(255,255,255,0.2)` etc.
    If you find yourself wanting `rgba(...)`, the answer is `var(--accent-soft)`.
  * Hardcoded font-family strings such as 'Inter', 'Newsreader', 'IBM Plex Mono',
    'Roboto', 'Helvetica', 'Georgia', 'Arial', 'Courier', or any other named
    font. Always use `font-family: var(--font-sans|--font-serif|--font-mono)`.
  * `@import` statements of any kind (especially Google Fonts /
    `fonts.googleapis.com`). The host already loads Inter, Newsreader, and IBM
    Plex Mono and exposes them via the font variables below — never re-import
    them.
  * `<link rel="stylesheet">` or remote `<script>` tags. The iframe is sandboxed
    and must be fully self-contained.

The host already sets a sensible body background, foreground color, and base
font (`font-family: var(--font-sans)`). Only override these when the design
genuinely calls for it.

Available tokens (use with var(--name)):
  Color:
    --background          page surface
    --foreground          default text on --background
    --card                raised surface
    --card-foreground     text on --card
    --popover             floating surface (menus, tooltips)
    --popover-foreground  text on --popover
    --primary             primary action color
    --primary-foreground  text on --primary
    --secondary           muted surface
    --secondary-foreground
    --muted               quiet background
    --muted-foreground    secondary text
    --accent              brand accent (links, focus rings, highlights)
    --accent-foreground   text on --accent
    --accent-soft         translucent accent fill (good for shadow / hover wash)
    --destructive         error / destructive action
    --destructive-foreground
    --border              standard border / divider
    --border-strong       stronger border / hover state
    --input               input/textarea border
    --ring                focus ring
  Type:
    --font-sans   the editorial sans (Inter family) — body/UI
    --font-serif  the editorial serif (Newsreader family) — display
    --font-mono   the editorial mono (IBM Plex Mono family) — numbers, code
  Geometry:
    --radius, --radius-sm, --radius-lg

These variables flip automatically when the host swaps light/dark — so any
widget you build will follow the host theme without changes.

LAYOUT CONTRACT — the host iframe owns the viewport. Your widget's root
container must FILL the iframe horizontally; the host crops the visual
column to whatever the slide layout dictates. Concretely:

  * Forbidden on the root container (the outermost `<section>` / `<div>`
    in `html`): `max-width: <fixed px/rem/em>`, `width: <fixed px/rem/em>`,
    and `margin: 0 auto` (or any horizontal-centering margin). These leave
    dead space on either side of the widget on wide slides.
  * Allowed: `max-width: 100%`, `max-width: 100vw`, `width: 100%`. Use
    these if you specifically want to clamp to the iframe.
  * Nested elements (a heading column, a button row, an avatar grid) CAN
    still cap their own width — the rule only applies to the root wrapper.

If the design genuinely needs a narrow column for readability, set
`padding-inline` on the root and let inner blocks be `max-width: 60ch`
or similar. The widget should still fill the iframe.

BRIDGE CONTRACT — canonical event names. The widget's only communication with
the host is `window.slaides.emit(type, payload)` (outbound) and
`window.slaides.on(type, callback)` (inbound). Use the canonical event names
below — do NOT invent kind-prefixed names like 'poll.vote' or 'plotter.move'.
The host fans events out to every other viewer of the session by re-emitting
the same payload on the `<type>.broadcast` channel.

  | widget kind                 | emit on user action | subscribe to              |
  | --------------------------- | ------------------- | ------------------------- |
  | poll / single-choice        | `vote` `{choice}`   | `vote.broadcast` `{choice}` |
  | open question / textarea    | `text` `{text}`     | `text.broadcast` `{text}` |
  | wordcloud / one-word        | `text` `{text}`     | `text.broadcast` `{text}` |
  | slider / continuous value   | `value` `{value}`   | `value.broadcast` `{value}` |
  | plotter / live expression   | `plotter.update` `{expression}` | (none required) |
  | anything else interactive   | a short lowercase verb (`vote`, `text`, `value`) over a kind-prefix |

The general rule: emit a short lowercase verb on the user's first-class action;
subscribe to `<verb>.broadcast` to receive the same action from other viewers
and update the shared visualization (tally, list of replies, word cloud size,
etc.). Local optimistic updates should be avoided — the broadcast is the
authoritative tally.

IDENTITY — `window.slaides.participant` carries the audience member's identity
baked at iframe mount:

    {
      id: null,
      display_name: string | null,  // the name they typed at session join
      anon: boolean,                 // they opted out of name display
    }

Prefer `slaides.participant.display_name` over asking the user to retype their
name inside the widget. Fall back gracefully when it is `null` (presenter view,
preview, or a fully anonymous join) — e.g. show "Anonymous" or skip the
greeting. If `slaides.participant.anon` is `true`, do NOT render the name even
when one is present; treat the participant as Anonymous in any leaderboard or
public list. The widget will be re-mounted on rejoin, so identity is stable
for the lifetime of a session for that participant.

BEHAVIOR CONTRACT — REQUIRED. Every widget declares whether it's Quiet (local
to each viewer; no server contact) or Loud (audience contributions aggregate
into a single shared state via the server). The behavior shows up in the
top-level `behavior` field of the JSON document you return:

    "behavior": { "kind": "quiet" }
    "behavior": { "kind": "loud", "aggregator": "<one-of-five>",
                  "contribution_schema": { "type": "..." } }

Quiet (`kind: "quiet"`):
  - DO NOT call `window.slaides.contribute(...)` — it is rejected at runtime.
  - Use `window.slaides.setState({...})` / `getState()` for per-viewer scratch
    state. That state lives in `sessionStorage`; it persists across reloads
    but never leaves the viewer's tab.
  - Examples: interactive plot/formula explorer, self-paced flashcards,
    anything where each audience member's interaction is private to them.

Loud (`kind: "loud"`): five aggregators are supported, each with a different
state shape the audience widget renders from. ONE widget = ONE aggregator —
pick the closest fit:

  | aggregator              | state shape                                   | use cases                                            |
  | ----------------------- | --------------------------------------------- | ---------------------------------------------------- |
  | tally                   | { tally: {choice → int}, voters: int }        | election poll, Kahoot-style quiz, image vote         |
  | latest_per_participant  | { values: {ref → value} }                     | sentiment slider, map pin, multi-criteria rating     |
  | append                  | { entries: [{ref, value, ts}], total: int }   | Q&A thread, open ideas, draw-together strokes        |
  | set_union               | { counts: {value → int} }                     | word cloud, "list 3 words that describe X"           |
  | keyed_tally             | { items: [{id, ref, value, ts, votes, voters}]| brainstorm board, idea jam (item + votes per item)  |

Loud bridge surface (call these from the widget JS):

    // Send a contribution. The server aggregates + broadcasts back.
    window.slaides.contribute(value);

    // Receive the current aggregated state, including initial state on mount.
    window.slaides.on('state', function (msg) {
      // msg.state = the projection shaped per the declared aggregator
      // msg.state_version = monotonic integer; ignore lower versions on reconnect
      // msg.closed = boolean (the host paused/ended this placement)
      // re-render UI from msg.state here
    });

Authoritative state lives on the server. NEVER optimistically update the local
UI from the contribution side — render only from the `state` event so every
viewer sees the same projection.

Concrete loud-poll skeleton (one of many shapes the model can produce):

    var p = (window.slaides && window.slaides.props) || {};
    var choices = Array.isArray(p.choices) ? p.choices : [];
    function render(state) {
      var tally = (state && state.tally) || {};
      // … paint each option's bar from tally[choice.id] || 0 …
    }
    window.slaides.on && window.slaides.on('state', function (msg) {
      render(msg.state || {});
    });
    // user clicks an option → contribute the choice id
    document.addEventListener('click', function (ev) {
      var id = ev.target.getAttribute && ev.target.getAttribute('data-choice');
      if (id) window.slaides.contribute(id);
    });

For Loud widgets `props_schema` MUST declare the contribution shape under
`behavior.contribution_schema` so the server can reject malformed payloads:

    "behavior": {
      "kind": "loud",
      "aggregator": "tally",
      "contribution_schema": { "type": "string" }
    }

PROPS CONTRACT — REQUIRED. Every user-visible piece of content (the question
text, choice labels, prompt strings, axis labels, colors-as-data, etc.) MUST
live in `props_schema` with a sensible default — NEVER hardcoded in the HTML.
The widget runs the same code on every slide; per-slide content comes from the
placement's props.

`props_schema` MUST follow this strict JSON-Schema subset (the form renderer
and server validator agree on it; anything else is silently ignored):

    {
      "properties": {
        "<key>": {
          "type": "string" | "number" | "integer" | "boolean" | "array" | "object",
          "default": <value of the declared type>,        // required for every key
          "description": "<short hint shown next to the form field>",
          "enum": [<allowed values>]?,                    // primitives only
          "items": <nested schema>?,                       // when type == "array"
          "properties": { "<sub_key>": <nested schema> }?, // when type == "object"
          "minLength": <int>?, "maxLength": <int>?,
          "minimum": <num>?, "maximum": <num>?
        },
        ...
      }
    }

SLAIDES extension: `"enum.from": "<other_prop>.<key>"` resolves a dynamic enum
from a sibling array. Example: a quiz declares `correct_answer` whose options
come from the current `choices[].id`:

    "correct_answer": {
      "type": "string",
      "enum.from": "choices.id"
    }

Use this defensive read pattern at the top of every script so missing props
or older placements don't crash:

    var p = (window.slaides && window.slaides.props) || {};
    var question = p.question || 'Default question';
    var choices  = Array.isArray(p.choices) ? p.choices : [];

Subscribe to prop updates so re-editing from the Props panel takes effect
without a reload:

    window.slaides && window.slaides.on && window.slaides.on('props', function (next) {
      // re-render with next.* values
    });

CONCRETE EXAMPLE for a multiple-choice poll:

    "props_schema": {
      "properties": {
        "question": {
          "type": "string",
          "default": "Pick one",
          "description": "Question shown to the audience"
        },
        "choices": {
          "type": "array",
          "default": [
            {"id": "a", "label": "Option A"},
            {"id": "b", "label": "Option B"}
          ],
          "items": {
            "type": "object",
            "properties": {
              "id":    {"type": "string"},
              "label": {"type": "string"}
            }
          }
        }
      }
    }

The HTML for the same widget contains NO question text and NO choice labels —
the JS reads them from props and renders. If you find yourself typing the
phrase "Pick one" into the HTML, stop: move it to `props_schema.<key>.default`
and read it from `window.slaides.props`.

CANVAS / IMPERATIVE PAINT — `<canvas>` 2D context APIs (`ctx.strokeStyle`,
`ctx.fillStyle`, etc.) need real color strings, not `var(--*)`. Read theme
colors at script start like this and pass the resolved strings to canvas:

    var css = getComputedStyle(document.documentElement);
    var colorAccent = css.getPropertyValue('--accent').trim();
    var colorBorder = css.getPropertyValue('--border').trim();
    ctx.strokeStyle = colorAccent;
    ctx.fillStyle   = colorBorder;

Do NOT hardcode hex inside canvas paint code — that's still a violation of the
forbidden-color rule above.

SEMANTIC SKELETONS — preferred HTML shape per common kind. Use these as a
starting point so screen readers and the bridge contract work correctly:

  poll:
    <section class="poll" aria-live="polite">
      <header><span class="kicker">POLL</span><h2 id="q"></h2></header>
      <ul id="options" role="listbox" aria-label="poll options"></ul>
      <footer><span id="status"></span></footer>
    </section>
    Each option is a `<li><button type="button" aria-pressed="false">…</button></li>`.

  open question:
    <section class="question">
      <header><span class="kicker">QUESTION</span><h2 id="q"></h2></header>
      <form id="form"><textarea id="reply"></textarea><button id="send" type="submit">Send</button></form>
      <ul id="replies"></ul>
    </section>

  plotter:
    <section class="plotter">
      <header><span class="kicker">FUNCTION</span><div class="row">y = <input id="expr"/></div></header>
      <canvas id="chart" width="560" height="220"></canvas>
      <div id="err" role="status"></div>
    </section>

  wordcloud:
    <section class="cloud">
      <header><span class="kicker">WORDCLOUD</span><h2 id="prompt"></h2></header>
      <form id="form"><input id="word" maxlength="24" autocomplete="off"/><button type="submit">Add</button></form>
      <div id="bag" aria-live="polite"></div>
    </section>

  multi-question quiz (multiple questions, one at a time):
    <section class="quiz">
      <header><span class="kicker">QUIZ</span><h2 id="title"></h2></header>
      <!-- The HTML must NOT hardcode the questions / choices. Leave the
           interior empty and have JS render the current question from
           `slaides.props.questions[currentIndex]`. -->
      <div id="stage" aria-live="polite"></div>
      <footer><span id="progress"></span></footer>
    </section>

  Worked multi-question quiz JS (Quiet — each viewer's score is local):

    var slaides = window.slaides;
    var idx = 0, score = 0;
    function render() {
      var p = slaides.props || {};
      var qs = Array.isArray(p.questions) ? p.questions : [];   // <-- READ THE PROP
      var stage = document.getElementById('stage');
      var progress = document.getElementById('progress');
      document.getElementById('title').textContent = p.title || '';
      if (idx >= qs.length) {
        stage.innerHTML = `<p>Done. Score: ${score} / ${qs.length}</p>`;
        progress.textContent = '';
        return;
      }
      var q = qs[idx];
      var choices = (q.choices || []).map(function (c) {
        return `<li><button type="button" data-id="${c.id}">${c.label}</button></li>`;
      }).join('');
      stage.innerHTML = `<p>${q.prompt}</p><ul>${choices}</ul>`;
      progress.textContent = (idx + 1) + ' / ' + qs.length;
      stage.querySelectorAll('button[data-id]').forEach(function (btn) {
        btn.addEventListener('click', function () {
          if (btn.dataset.id === String(q.correct_answer)) score++;
          idx++;
          render();
        });
      });
    }
    render();
    slaides.on && slaides.on('props', render);

CRITICAL FOR MULTI-QUESTION WIDGETS: the questions array MUST come from
`slaides.props` — never hardcode them in HTML. If `props_schema` declares
`questions: { type: "array", items: {...} }` but the JS never reads
`slaides.props.questions`, the widget renders only static chrome (e.g. just
the title + QUIZ badge) and looks broken. Audit your JS before finishing:
for every property declared in `props_schema`, there must be a corresponding
read from `slaides.props` in the JS.

Use semantic HTML (`<ul>` for lists, `<form>` + `<button type="submit">` for
inputs, `aria-live` for dynamic regions). Don't replace these with `<div>`
soup.

FORMS — when you use `<form>`, the submit handler MUST call
`e.preventDefault()` immediately, then route the contribution through
`window.slaides.contribute(value)` (Loud) or local state (Quiet). The iframe
runs in a sandboxed frame: a form is never allowed to navigate or submit to a
real endpoint — the host CSP `form-action 'none'` blocks it at the platform
layer. Without `preventDefault`, the browser still tries to submit and you
lose the user's input. Example:

    document.getElementById('form').addEventListener('submit', function (e) {
      e.preventDefault();                              // <-- required
      var value = document.getElementById('reply').value.trim();
      if (!value) return;
      window.slaides.contribute(value);
      e.target.reset();
    });

JS STRING LITERALS — multi-line strings MUST use backtick template literals
(or `+` concatenation). Never put a literal newline inside `'...'` or `"..."` —
JavaScript rejects it at PARSE TIME with
`SyntaxError: Invalid or unexpected token`, so the whole IIFE throws and NO
event handlers attach. Symptom: the audience clicks "Start" and nothing
happens. There is no recovery from this in the runtime; you must emit
syntactically valid JS or the widget is dead on arrival.

Broken (your widget won't run AT ALL — every button is dead):

    panel.innerHTML = '
      <div>...</div>
    ';

Correct (template literal — preferred):

    panel.innerHTML = `
      <div>${label}</div>
      <span>${count}</span>
    `;

Or correct (single-line concatenation):

    panel.innerHTML =
      '<div>' + label + '</div>' +
      '<span>' + count + '</span>';

The host will run a parse check on the JS field before applying. If your JS
fails to parse, an error chip appears in the chat and the apply is refused.
"""


def _system_prompt(purpose: str) -> str:
    if purpose == "widget_generate":
        return (
            "You generate and revise SLAIDES widgets. Return only compact JSON in this envelope: "
            '{"type":"question","question":"Should this be private or shared with the room?",'
            '"options":[{"id":"quiet","label":"Private per viewer","value":{"behavior":{"kind":"quiet"}}},'
            '{"id":"loud","label":"Shared live results","value":{"behavior":{"kind":"loud"}}}]} '
            "when behavior or requirements are ambiguous; or "
            '{"type":"draft","plan":["choose behavior","write props schema","write widget source"],'
            '"reflection":"The widget uses props for all user-visible copy.",'
            '"widget":{"name":"Poll","kind":"poll","html":"<section></section>","js":"","css":"",'
            '"props_schema":{},"tags":[],"behavior":{"kind":"quiet"}},'
            '"ai_spec":{"intent":"Private poll draft"},"example_props":{}} '
            "when you are confident. Never answer with plain prose. "
            "Use vanilla HTML/CSS/JS. The widget runs in a sandboxed iframe and can call "
            "window.slaides.emit(event, payload) and window.slaides.on(event, callback). "
            "Do not include markdown fences.\n\n"
            + WIDGET_THEME_CONTRACT
        )
    if purpose == "interpret":
        return "Explain selected slide text clearly and briefly. Preserve the instructor's tone."
    if purpose == "inline_write":
        return "Help rewrite or continue slide copy. Return only the text the instructor can insert."
    return "Summarise session transcript material into concise, useful notes."


def _messages(body: LlmCompleteRequest) -> list[dict]:
    context = body.context or {}
    content = body.prompt
    if context:
        content = f"{body.prompt}\n\nContext:\n{json.dumps(context, ensure_ascii=False)}"
    user_content: str | list[dict] = content
    if body.images:
        user_content = [{"type": "text", "text": content}]
        for image in body.images:
            user_content.append({"type": "image_url", "image_url": {"url": image.data_url}})
    return [
        {"role": "system", "content": _system_prompt(body.purpose)},
        {"role": "user", "content": user_content},
    ]


async def _stream_openai_chunks(
    *,
    base_url: str,
    api_key: str,
    model: str,
    body: LlmCompleteRequest,
    parameters: dict | None = None,
) -> AsyncIterator[tuple[str, dict | None]]:
    payload = {
        "model": model,
        "messages": _messages(body),
        "stream": True,
    }
    if parameters:
        payload.update(parameters)
    async with httpx.AsyncClient(timeout=httpx.Timeout(60.0, connect=10.0)) as client:
        async with client.stream(
            "POST",
            _endpoint(base_url),
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json=payload,
        ) as response:
            if response.status_code >= 400:
                detail = await response.aread()
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail=f"LLM endpoint returned {response.status_code}: {detail.decode('utf-8', 'ignore')[:500]}",
                )
            async for line in response.aiter_lines():
                if not line.startswith("data:"):
                    continue
                raw = line.removeprefix("data:").strip()
                if not raw:
                    continue
                if raw == "[DONE]":
                    break
                data = json.loads(raw)
                choice = (data.get("choices") or [{}])[0]
                delta = (choice.get("delta") or {}).get("content") or ""
                if delta:
                    yield delta, data.get("usage")


async def stream_completion(
    *,
    session: AsyncSession,
    user: AppUser | None,
    workspace: Workspace,
    body: LlmCompleteRequest,
    session_id: uuid.UUID | None = None,
) -> AsyncIterator[bytes]:
    # Non-routable purposes (e.g. future `summarise`) read directly from the
    # capability map; a `None` value means explicitly disabled.
    if body.purpose not in ROUTABLE_PURPOSES:
        assignments = workspace.llm_capability_models if isinstance(workspace.llm_capability_models, dict) else {}
        if body.purpose in assignments and assignments[body.purpose] is None:
            yield _sse("error", {"detail": f"{PURPOSE_LABELS.get(body.purpose, body.purpose)} is disabled"})
            return

    api_key = decrypt_workspace_secret(workspace.id, workspace.llm_key_enc)
    if not api_key:
        yield _sse("error", {"detail": "LLM API key is not configured"})
        return

    model_config, model_error = _resolve_model(workspace, body)
    if model_error or model_config is None:
        yield _sse("error", {"detail": model_error or "LLM model is not configured"})
        return

    try:
        await enforce_rate_limit(workspace.id, body.purpose, user.id if user else None)
    except HTTPException as exc:
        yield _sse("error", {"detail": exc.detail})
        return
    started = time.perf_counter()
    model = str(model_config.get("id") or workspace.llm_model or "gpt-4.1-mini")
    parameters = _model_parameters(model_config)
    prompt_hash = hashlib.sha256(body.prompt.encode("utf-8")).hexdigest()
    output: list[str] = []
    tokens_in = None
    tokens_out = None

    try:
        async for delta, usage in _stream_openai_chunks(
            base_url=workspace.llm_base_url,
            api_key=api_key,
            model=model,
            body=body,
            parameters=parameters,
        ):
            output.append(delta)
            if usage:
                tokens_in = usage.get("prompt_tokens")
                tokens_out = usage.get("completion_tokens")
            yield _sse("token", {"delta": delta})
        final_text = "".join(output)
        done_payload: dict = {"text": final_text}
        if body.purpose == "widget_generate":
            ctx = body.context or {}
            current_widget = ctx.get("current") if ctx.get("adjust_existing") else None
            warnings = _scan_theme_violations(final_text)
            warnings.extend(_scan_layout_violations(final_text))
            warnings.extend(_scan_props_contract_violations(final_text))
            warnings.extend(
                _scan_behavior_violations(
                    final_text,
                    current=current_widget if isinstance(current_widget, dict) else None,
                )
            )
            if warnings:
                done_payload["warnings"] = warnings
        yield _sse("done", done_payload)
    except HTTPException as exc:
        yield _sse("error", {"detail": exc.detail})
    except Exception as exc:  # noqa: BLE001
        yield _sse("error", {"detail": f"LLM request failed: {exc}"})
    finally:
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        session.add(
            LlmCall(
                workspace_id=workspace.id,
                user_id=user.id if user else None,
                session_id=session_id,
                purpose=body.purpose,
                model=model,
                prompt_hash=prompt_hash,
                prompt_text=None,
                latency_ms=elapsed_ms,
                tokens_in=tokens_in,
                tokens_out=tokens_out,
            )
        )
        await session.flush()
