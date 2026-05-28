"""Widget-generation evaluation harness.

Asks the configured LLM to generate widget drafts, then scores each draft
against reference expectations. The legacy Quiet `.swidget` seed directory is
optional; the current always-available cases are synthetic Loud widgets.

Usage:
    cd apps/api
    uv run python -m scripts.eval_widgets [--runs N] [--seed NAME] [--report PATH]

Reads OPENAI_BASE_URL / OPENAI_API_KEY / OPENAI_MODEL from the repo-root .env
via python-dotenv. Reuses the production `widget_generate` system prompt and
`_stream_openai_chunks` HTTP path so the eval measures the real prompt.

The seeds themselves predate the theme contract (they hardcode hex colors and
font names), so the comparison is **semantic**: we want the generated output
to preserve the seeds' behavior + structure + bridge events while ALSO passing
theme compliance (which the seeds fail).
"""

from __future__ import annotations

import argparse
import asyncio
import dataclasses
import json
import os
import re
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Repo paths -----------------------------------------------------------------
SCRIPT_DIR = Path(__file__).resolve().parent
API_DIR = SCRIPT_DIR.parent
REPO_ROOT = API_DIR.parent.parent
SEEDS_DIR = REPO_ROOT / "packages" / "widget-runtime" / "seeds"
REPORTS_DIR = SCRIPT_DIR / "eval_reports"

# Ensure `src/` is importable when running outside `make` ---------------------
sys.path.insert(0, str(API_DIR / "src"))

from dotenv import load_dotenv  # noqa: E402  (after sys.path tweak)

import httpx  # noqa: E402

from slaides.llm.schemas import LlmCompleteRequest  # noqa: E402
from slaides.llm.service import (  # noqa: E402
    _endpoint,
    _messages,
    _scan_behavior_violations,
    _scan_theme_violations,
    _system_prompt,
)
from slaides.widgets.package import unpack as unpack_widget  # noqa: E402

# ---------------------------------------------------------------------------
# Optional seed fingerprint: derived from reading each .swidget file once at
# startup when the legacy seed directory exists. We pull event names and
# expected element types from the reference HTML/JS so the expectations live in
# the seeds themselves rather than being hardcoded.
# ---------------------------------------------------------------------------

def _bridge_aliases(js: str) -> set[str]:
    """Identifiers that bind to `window.slaides` (recursive through aliases).

    Models commonly write `var bridge = window.slaides;` or
    `var s = window.slaides; var b = s;`. We resolve these so the emit / on /
    props detectors below work regardless of nesting.
    """
    roots = {"window.slaides", "bridge"}
    aliases: set[str] = set()
    progressed = True
    while progressed:
        progressed = False
        for m in re.finditer(
            r"(?:var|let|const)\s+([a-zA-Z_$][\w$]*)\s*=\s*([^;]+?)(?:;|$)",
            js,
        ):
            name, rhs = m.group(1), m.group(2)
            if name in aliases or name in {"window"}:
                continue
            # RHS references window.slaides, `bridge`, or any previously-known alias.
            if any(root in rhs for root in roots) or any(
                re.search(rf"\b{re.escape(a)}\b", rhs) for a in aliases
            ):
                aliases.add(name)
                progressed = True
    return aliases


def _read_emits(js: str) -> set[str]:
    js = js or ""
    bases = ["window\\.slaides", "bridge", *(re.escape(a) for a in _bridge_aliases(js))]
    pattern = rf"(?:{'|'.join(bases)})\s*\.\s*emit\s*\(\s*['\"]([a-zA-Z0-9_.-]+)['\"]"
    return set(re.findall(pattern, js))


def _read_subscribes(js: str) -> set[str]:
    js = js or ""
    bases = ["window\\.slaides", "bridge", *(re.escape(a) for a in _bridge_aliases(js))]
    pattern = rf"(?:{'|'.join(bases)})\s*\.\s*on\s*\(\s*['\"]([a-zA-Z0-9_.-]+)['\"]"
    return set(re.findall(pattern, js))


def _read_prop_keys(js_html: str) -> set[str]:
    """Return all `props.<key>` reads — handles direct access, single aliasing
    (`var p = window.slaides.props`), and two-level aliasing
    (`var s = window.slaides; var p = s.props`)."""
    js_html = js_html or ""
    bridge_aliases = _bridge_aliases(js_html) | {"window.slaides", "bridge"}
    # Direct: <bridgeOrAlias>.props.<key> or <...>.props['key']
    direct_keys: set[str] = set()
    for base in bridge_aliases:
        b = base if base == "window.slaides" else re.escape(base)
        for m in re.finditer(
            rf"{b}\s*\.\s*props\s*\.\s*([a-zA-Z_][\w]*)", js_html
        ):
            direct_keys.add(m.group(1))
        for m in re.finditer(
            rf"{b}\s*\.\s*props\s*\[\s*['\"]([a-zA-Z_][\w]*)['\"]\s*\]", js_html
        ):
            direct_keys.add(m.group(1))
    # Aliased: `var p = <bridge>.props` -> resolve `p.<key>`
    prop_aliases: set[str] = set()
    for base in bridge_aliases:
        b = base if base == "window.slaides" else re.escape(base)
        for m in re.finditer(
            rf"(?:var|let|const)\s+([a-zA-Z_$][\w$]*)\s*=\s*[^;]*?{b}\s*\.\s*props",
            js_html,
        ):
            prop_aliases.add(m.group(1))
    for alias in prop_aliases:
        for m in re.finditer(rf"\b{re.escape(alias)}\s*\.\s*([a-zA-Z_][\w]*)", js_html):
            direct_keys.add(m.group(1))
        for m in re.finditer(
            rf"\b{re.escape(alias)}\s*\[\s*['\"]([a-zA-Z_][\w]*)['\"]\s*\]", js_html
        ):
            direct_keys.add(m.group(1))
    return direct_keys


# Structural feature predicates: each predicate takes the HTML body string and
# returns True/False. The seed's HTML is matched against the same predicates
# during bootstrap so we know what to expect.
STRUCTURAL_PREDICATES: dict[str, dict[str, Any]] = {
    "poll": {
        "list_container": lambda h: bool(re.search(r"<ul\b", h, re.IGNORECASE)),
        "multiple_buttons_or_items": lambda h: len(re.findall(r"<button|<li\b", h, re.IGNORECASE)) >= 1,
    },
    "question": {
        "textarea": lambda h: bool(re.search(r"<textarea\b", h, re.IGNORECASE)),
        "submit_button": lambda h: bool(re.search(r"<button\b", h, re.IGNORECASE)),
        "replies_container": lambda h: bool(re.search(r"<(ul|ol|div)\b[^>]*id\s*=\s*['\"]?replies", h, re.IGNORECASE))
        or bool(re.search(r"<ul\b|<ol\b", h, re.IGNORECASE)),
    },
    "plotter": {
        "canvas": lambda h: bool(re.search(r"<canvas\b", h, re.IGNORECASE)),
        "input": lambda h: bool(re.search(r"<input\b", h, re.IGNORECASE)),
    },
    "wordcloud": {
        "input_or_form": lambda h: bool(re.search(r"<input\b|<form\b", h, re.IGNORECASE)),
        "output_container": lambda h: bool(re.search(r"<div\b", h, re.IGNORECASE)),
    },
}


@dataclass
class SeedSpec:
    """Reference fingerprint for one widget under test.

    Sourced from either an optional `.swidget` seed file or a synthetic in-code
    definition (the Loud cases added in Step 4). Synthetic cases set
    `expected_behavior` so the
    behavior_contract dimension runs; legacy seed cases leave it as None and
    are scored against the bridge_contract dimension instead."""

    name: str
    kind: str
    description: str
    props_schema: dict[str, Any]
    tags: list[str]
    emits: set[str]
    subscribes: set[str]
    structural: dict[str, bool]
    user_prompt: str
    behavioral_hint: str
    # Widgets v2 Step 4 — when set, the case is a Loud-widget eval. Holds the
    # expected `behavior.kind` and acceptable aggregator(s); empty `aggregator`
    # means "any of the five canonical ones is fine."
    expected_behavior: dict[str, Any] | None = None
    # The "kind" the model is allowed to echo back. Loud-poll synthetic cases
    # set this to "poll" so a returned `kind: "poll"` doesn't trip the
    # metadata check; structural predicates also resolve through this.
    accepted_kinds: set[str] = field(default_factory=set)


# Friendly per-seed user prompts (what a real instructor might type). The
# context dict ferries the structural expectation so the model has enough to
# match the seed's shape without the eval cheating by giving away the answer.
USER_PROMPTS: dict[str, dict[str, str]] = {
    "poll": {
        "prompt": "A live single-choice poll with four options. Each option has a horizontal bar that fills as votes come in, and the running tally updates in real time.",
        "hint": "Bind the question and options to props. Emit a vote event when the user clicks an option; listen for a vote.broadcast event to update everyone's tallies.",
    },
    "question": {
        "prompt": "An open question with a textarea where the audience types short replies. Submitted replies appear stacked beneath the prompt.",
        "hint": "Bind the prompt text to a prop. Emit a text event on submit; listen for text.broadcast to append other people's replies to the list.",
    },
    "plotter": {
        "prompt": "A live function plotter: an input field where you type a math expression like x*x-1, and a canvas that re-renders the curve as you type.",
        "hint": "Read the initial expression from a prop. Re-render the canvas on each keystroke. Emit a plotter.update event with the current expression so other viewers stay in sync.",
    },
    "wordcloud": {
        "prompt": "A live word cloud: viewers submit one-word answers to a prompt, and each new word appears in the cloud at a size proportional to its frequency.",
        "hint": "Bind the prompt to a prop. Emit a text event on submit; listen for text.broadcast and grow the matching word's font size. Anchor the cloud inside a container with aria-live.",
    },
}


def load_seed(path: Path) -> SeedSpec:
    pkg = unpack_widget(path.read_bytes())
    spec_meta = USER_PROMPTS.get(pkg.kind, {"prompt": f"Build a {pkg.kind} widget.", "hint": ""})
    return SeedSpec(
        name=pkg.name,
        kind=pkg.kind,
        description=pkg.description or "",
        props_schema=pkg.props_schema or {},
        tags=list(pkg.tags or []),
        emits=_read_emits(pkg.js or ""),
        subscribes=_read_subscribes(pkg.js or ""),
        structural={k: pred(pkg.html or "") for k, pred in STRUCTURAL_PREDICATES.get(pkg.kind, {}).items()},
        user_prompt=spec_meta["prompt"],
        behavioral_hint=spec_meta["hint"],
    )


# ---------------------------------------------------------------------------
# Widgets v2 Step 4 — synthetic Loud-widget cases. No .swidget seed exists for
# these because the Loud protocol postdates the seeds; the expectations live
# in code instead. The scoring path remains the same.
# ---------------------------------------------------------------------------


def loud_poll_spec() -> SeedSpec:
    return SeedSpec(
        name="Loud election poll",
        kind="loud-poll",
        description="A shared single-choice poll whose tally aggregates across the whole audience.",
        props_schema={
            "question": {"type": "string", "default": "Pick one"},
            "choices": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"},
                        "label": {"type": "string"},
                    },
                },
                "default": [
                    {"id": "a", "label": "Option A"},
                    {"id": "b", "label": "Option B"},
                ],
            },
        },
        tags=["loud", "poll"],
        emits=set(),
        subscribes=set(),
        # Re-use the existing poll structural predicate — a Loud poll still
        # wants a list of clickable options.
        structural={k: True for k in STRUCTURAL_PREDICATES["poll"]},
        user_prompt=(
            "A live single-choice election poll where every audience member's vote "
            "shows up on everyone else's screen in real time. Each option has a bar "
            "that fills proportional to its share of the tally."
        ),
        behavioral_hint=(
            "This is a LOUD widget — declare behavior.kind = 'loud' with "
            "aggregator = 'tally'. Read the question + choices from props. "
            "Audience clicks a choice → call window.slaides.contribute(choiceId). "
            "Subscribe via window.slaides.on('state', cb) and re-render bars from "
            "state.tally on every event."
        ),
        expected_behavior={"kind": "loud", "aggregator": "tally"},
        accepted_kinds={"loud-poll", "poll"},
    )


def loud_wordcloud_spec() -> SeedSpec:
    return SeedSpec(
        name="Loud word cloud",
        kind="loud-wordcloud",
        description="A shared word cloud aggregating one-word submissions across the audience.",
        props_schema={
            "prompt": {"type": "string", "default": "Pick a word"},
            "max_word_length": {"type": "integer", "default": 24, "minimum": 1, "maximum": 60},
        },
        tags=["loud", "wordcloud"],
        emits=set(),
        subscribes=set(),
        structural={k: True for k in STRUCTURAL_PREDICATES["wordcloud"]},
        user_prompt=(
            "A live word cloud: viewers each submit one word in response to a prompt, "
            "and the cloud grows as new words arrive — duplicate submissions make the "
            "matching word bigger. Everyone sees the same cloud."
        ),
        behavioral_hint=(
            "This is a LOUD widget — declare behavior.kind = 'loud' with "
            "aggregator = 'set_union'. Read the prompt from props. On submit call "
            "window.slaides.contribute(word). Subscribe via window.slaides.on('state', cb) "
            "and re-render the cloud from state.counts (a {word: count} map)."
        ),
        expected_behavior={"kind": "loud", "aggregator": "set_union"},
        accepted_kinds={"loud-wordcloud", "wordcloud"},
    )


def loud_specs() -> list[SeedSpec]:
    return [loud_poll_spec(), loud_wordcloud_spec()]


# ---------------------------------------------------------------------------
# LLM call (production prompt path, no rate limits, no DB writes)
# ---------------------------------------------------------------------------


async def call_llm(*, base_url: str, api_key: str, model: str, prompt: str, context: dict) -> str:
    """Issue a widget_generate request using the **production** message shape.

    Uses _system_prompt("widget_generate") and _messages(body) directly so the
    eval measures the real WIDGET_THEME_CONTRACT prompt. The HTTP transport is
    inlined here (rather than via _stream_openai_chunks) because we want a
    byte-buffer SSE parser that tolerates aiter_lines() boundary quirks on
    very long widget-generation responses.
    """
    body = LlmCompleteRequest(
        purpose="widget_generate",
        prompt=prompt,
        context=context,
        model_override=None,
    )
    payload = {
        "model": model,
        "messages": _messages(body),
        "stream": True,
    }
    out: list[str] = []
    async with httpx.AsyncClient(timeout=httpx.Timeout(180.0, connect=15.0)) as client:
        async with client.stream(
            "POST",
            _endpoint(base_url),
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json=payload,
        ) as response:
            if response.status_code >= 400:
                detail = await response.aread()
                raise RuntimeError(
                    f"endpoint returned {response.status_code}: {detail.decode('utf-8', 'ignore')[:400]}"
                )
            buf = ""
            async for chunk in response.aiter_text():
                buf += chunk
                # SSE messages are separated by a blank line. Drain whole
                # messages, leave any tail in the buffer.
                while "\n\n" in buf:
                    message, buf = buf.split("\n\n", 1)
                    data_lines = []
                    for line in message.splitlines():
                        if line.startswith("data:"):
                            data_lines.append(line[5:].lstrip())
                    if not data_lines:
                        continue
                    raw = "\n".join(data_lines)
                    if raw == "[DONE]":
                        return "".join(out)
                    try:
                        data = json.loads(raw)
                    except json.JSONDecodeError:
                        # Some providers occasionally emit non-JSON keepalives
                        # or partial frames; skip rather than abort.
                        continue
                    choice = (data.get("choices") or [{}])[0]
                    delta = (choice.get("delta") or {}).get("content") or ""
                    if delta:
                        out.append(delta)
    return "".join(out)


# ---------------------------------------------------------------------------
# Draft parsing (ports parseDraft() from WidgetCollection.vue)
# ---------------------------------------------------------------------------


FENCE_RE = re.compile(r"^```(?:json)?\s*(.*?)\s*```$", re.IGNORECASE | re.DOTALL)


def strip_code_fence(text: str) -> str:
    trimmed = text.strip()
    m = FENCE_RE.match(trimmed)
    return m.group(1).strip() if m else trimmed


def parse_draft(text: str) -> dict[str, Any] | None:
    raw = strip_code_fence(text)
    # Some models prepend an explanation before the JSON; try to extract the
    # outermost JSON object if a plain json.loads fails.
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        first = raw.find("{")
        last = raw.rfind("}")
        if first == -1 or last <= first:
            return None
        try:
            return json.loads(raw[first : last + 1])
        except json.JSONDecodeError:
            return None


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------


@dataclass
class DimensionResult:
    name: str
    passed: bool
    detail: str = ""


@dataclass
class RunResult:
    seed_kind: str
    run_index: int
    elapsed_ms: int
    dimensions: list[DimensionResult] = field(default_factory=list)
    parse_ok: bool = True
    raw_text: str = ""
    draft: dict[str, Any] | None = None
    error: str | None = None

    @property
    def score(self) -> float:
        if not self.dimensions:
            return 0.0
        return sum(1.0 for d in self.dimensions if d.passed) / len(self.dimensions)


def score_metadata(draft: dict[str, Any], spec: SeedSpec) -> DimensionResult:
    name = str(draft.get("name") or "").strip()
    kind = str(draft.get("kind") or "").strip().lower()
    props_schema = draft.get("props_schema") or {}
    tags = draft.get("tags") or []
    missing: list[str] = []
    if not name:
        missing.append("name")
    acceptable = spec.accepted_kinds or {spec.kind}
    if kind not in acceptable:
        missing.append(f"kind not in {sorted(acceptable)!r} (got {kind!r})")
    if not isinstance(props_schema, dict):
        missing.append("props_schema not an object")
    else:
        # `props_schema` is allowed to nest under `.properties` or be the
        # properties dict itself.
        declared = props_schema.get("properties") if isinstance(props_schema.get("properties"), dict) else props_schema
        for required_key in spec.props_schema.keys():
            if not isinstance(declared, dict) or required_key not in declared:
                missing.append(f"props_schema missing {required_key!r}")
    if not isinstance(tags, list) or len(tags) == 0:
        missing.append("tags empty")
    return DimensionResult("metadata", passed=not missing, detail="; ".join(missing))


def score_theme_compliance(draft: dict[str, Any]) -> DimensionResult:
    blob = (draft.get("html") or "") + "\n" + (draft.get("css") or "") + "\n" + (draft.get("js") or "")
    warnings = _scan_theme_violations(blob)
    return DimensionResult("theme_compliance", passed=not warnings, detail=" | ".join(warnings))


def score_bridge_contract(draft: dict[str, Any], spec: SeedSpec) -> DimensionResult:
    js = (draft.get("js") or "") + "\n" + (draft.get("html") or "")  # some models inline scripts
    got_emits = _read_emits(js)
    got_subs = _read_subscribes(js)
    missing: list[str] = []
    for e in spec.emits:
        if e not in got_emits:
            missing.append(f"emit({e!r}) missing")
    for s in spec.subscribes:
        if s not in got_subs:
            missing.append(f"on({s!r}) missing")
    return DimensionResult("bridge_contract", passed=not missing, detail="; ".join(missing))


def score_structural(draft: dict[str, Any], spec: SeedSpec) -> DimensionResult:
    html = draft.get("html") or ""
    # For Loud cases (`loud-poll`, `loud-wordcloud`) the predicate set lives
    # under the base kind. Try the literal kind first, fall back to any base
    # name in `accepted_kinds`.
    predicates = STRUCTURAL_PREDICATES.get(spec.kind)
    if predicates is None:
        for k in spec.accepted_kinds:
            if k in STRUCTURAL_PREDICATES:
                predicates = STRUCTURAL_PREDICATES[k]
                break
    predicates = predicates or {}
    missing: list[str] = []
    for name, pred in predicates.items():
        if spec.structural.get(name) and not pred(html):
            missing.append(name)
    return DimensionResult("structural_sketch", passed=not missing, detail="; ".join(missing))


def score_props_honored(draft: dict[str, Any], spec: SeedSpec) -> DimensionResult:
    blob = (draft.get("js") or "") + "\n" + (draft.get("html") or "")
    reads_found = _read_prop_keys(blob)
    missing = [k for k in spec.props_schema.keys() if k not in reads_found]
    return DimensionResult("props_honored", passed=not missing, detail="; ".join(f"props.{k}" for k in missing))


def score_behavior_contract(draft: dict[str, Any], spec: SeedSpec) -> DimensionResult:
    """Widgets v2 Step 4 — for Loud-widget cases, verify the generated widget
    declares behavior.kind=='loud' with a supported aggregator AND the JS
    actually calls slaides.contribute() + subscribes to slaides.on('state', …).

    Reuses the production `_scan_behavior_violations` scanner so the eval
    catches the same issues an instructor would see in the warnings strip."""
    expected = spec.expected_behavior or {}
    expected_kind = expected.get("kind")
    expected_aggregator = expected.get("aggregator")

    behavior = draft.get("behavior") or {}
    missing: list[str] = []

    if not isinstance(behavior, dict):
        return DimensionResult(
            "behavior_contract",
            passed=False,
            detail="behavior field missing or not an object",
        )

    if expected_kind and behavior.get("kind") != expected_kind:
        missing.append(f"behavior.kind != {expected_kind!r} (got {behavior.get('kind')!r})")
    if expected_aggregator and behavior.get("aggregator") != expected_aggregator:
        missing.append(
            f"behavior.aggregator != {expected_aggregator!r} (got {behavior.get('aggregator')!r})"
        )

    # Re-use the production scanner so we share the same heuristics the user
    # sees in done.warnings. It operates on raw JSON text.
    try:
        scanner_warnings = _scan_behavior_violations(json.dumps(draft))
    except Exception as exc:  # noqa: BLE001
        scanner_warnings = [f"scanner crash: {exc}"]
    missing.extend(scanner_warnings)

    return DimensionResult("behavior_contract", passed=not missing, detail=" | ".join(missing))


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------


async def run_one(*, base_url: str, api_key: str, model: str, spec: SeedSpec, idx: int) -> RunResult:
    result = RunResult(seed_kind=spec.kind, run_index=idx, elapsed_ms=0)
    context = {
        "kind": spec.kind,
        "tagline": spec.description,
        "props_schema": spec.props_schema,
        "behavioral_hint": spec.behavioral_hint,
        "expected_tags": spec.tags,
    }
    started = time.perf_counter()
    try:
        result.raw_text = await call_llm(
            base_url=base_url, api_key=api_key, model=model, prompt=spec.user_prompt, context=context
        )
    except Exception as exc:  # noqa: BLE001
        result.error = f"{type(exc).__name__}: {exc}"
        result.elapsed_ms = int((time.perf_counter() - started) * 1000)
        return result
    result.elapsed_ms = int((time.perf_counter() - started) * 1000)
    draft = parse_draft(result.raw_text)
    if draft is None:
        result.parse_ok = False
        result.dimensions = [DimensionResult("parse", False, "JSON parse failed")]
        return result
    result.draft = draft
    dims = [
        score_metadata(draft, spec),
        score_theme_compliance(draft),
        score_structural(draft, spec),
        score_props_honored(draft, spec),
    ]
    if spec.expected_behavior is not None:
        # Loud widget — verify behavior contract instead of legacy bridge verbs.
        dims.append(score_behavior_contract(draft, spec))
    else:
        dims.append(score_bridge_contract(draft, spec))
    result.dimensions = dims
    return result


async def main_async(args: argparse.Namespace) -> int:
    load_dotenv(REPO_ROOT / ".env")
    base_url = os.environ.get("OPENAI_BASE_URL")
    api_key = os.environ.get("OPENAI_API_KEY")
    model = os.environ.get("OPENAI_MODEL")
    if not base_url or not api_key or not model:
        print("ERROR: OPENAI_BASE_URL / OPENAI_API_KEY / OPENAI_MODEL must be set in .env or environment.")
        return 2

    seed_files = sorted(SEEDS_DIR.glob("*.swidget"))
    synthetic = loud_specs()
    if args.seed:
        wanted = {s.lower() for s in args.seed}
        seed_files = [p for p in seed_files if p.stem.lower() in wanted]
        synthetic = [s for s in synthetic if s.kind.lower() in wanted]
    if not seed_files and not synthetic and not args.loud_only:
        print(
            "ERROR: no seed widgets matched. Available:",
            [p.stem for p in SEEDS_DIR.glob("*.swidget")] + [s.kind for s in loud_specs()],
        )
        return 2

    if args.loud_only:
        specs = synthetic
    elif args.skip_loud:
        specs = [load_seed(p) for p in seed_files]
    else:
        specs = [load_seed(p) for p in seed_files] + synthetic
    print(f"Loaded {len(specs)} case(s): {[s.kind for s in specs]}")
    print(f"Model: {model}  Endpoint: {base_url}")
    print(f"Runs per seed: {args.runs}\n")

    all_runs: list[RunResult] = []
    for spec in specs:
        print(f"=== {spec.kind} ({spec.name}) ===")
        for i in range(args.runs):
            r = await run_one(base_url=base_url, api_key=api_key, model=model, spec=spec, idx=i)
            all_runs.append(r)
            tag = "ERR" if r.error else ("PARSE-FAIL" if not r.parse_ok else f"{r.score:.2f}")
            failing = "" if r.error or not r.parse_ok else " | ".join(
                f"{d.name}{'✓' if d.passed else '✗'}" for d in r.dimensions
            )
            print(f"  run {i + 1}/{args.runs}: {tag}  ({r.elapsed_ms} ms)  {failing}")
            if r.error:
                print(f"    error: {r.error}")
            elif not r.parse_ok:
                print(f"    raw[:200]: {r.raw_text[:200]!r}")
            else:
                for d in r.dimensions:
                    if not d.passed and d.detail:
                        print(f"    {d.name}: {d.detail[:240]}")
        print()

    write_report(all_runs, specs, model=model, base_url=base_url, runs_per_seed=args.runs)
    summary = summarise(all_runs)
    print("Summary:")
    print(summary)
    return 0


def summarise(runs: list[RunResult]) -> str:
    by_seed: dict[str, list[RunResult]] = {}
    for r in runs:
        by_seed.setdefault(r.seed_kind, []).append(r)
    # Both Quiet seeds and Loud cases share four dimensions; the fifth is
    # `bridge_contract` for Quiet and `behavior_contract` for Loud. We merge
    # them into one "protocol" column so the table stays five-wide.
    lines = [f"{'case':<16} {'runs':<5} {'avg':<6} {'metadata':<10} {'theme':<8} {'protocol':<10} {'structural':<12} {'props':<7}"]
    shared_dims = ["metadata", "theme_compliance", "structural_sketch", "props_honored"]
    protocol_dims = {"bridge_contract", "behavior_contract"}
    for kind, group in by_seed.items():
        usable = [r for r in group if r.parse_ok and not r.error]
        avg = (sum(r.score for r in usable) / len(usable)) if usable else 0.0
        meta = sum(1 for r in usable for x in r.dimensions if x.name == shared_dims[0] and x.passed)
        theme = sum(1 for r in usable for x in r.dimensions if x.name == shared_dims[1] and x.passed)
        struct = sum(1 for r in usable for x in r.dimensions if x.name == shared_dims[2] and x.passed)
        props_ = sum(1 for r in usable for x in r.dimensions if x.name == shared_dims[3] and x.passed)
        proto = sum(1 for r in usable for x in r.dimensions if x.name in protocol_dims and x.passed)
        proto_label_full = next(
            (x.name for r in usable for x in r.dimensions if x.name in protocol_dims),
            "bridge_contract",
        )
        proto_label = proto_label_full.split("_")[0]
        n = len(group)
        proto_cell = f"{proto}/{n} ({proto_label})"
        lines.append(
            f"{kind:<16} {n:<5} {avg:<6.2f} "
            f"{f'{meta}/{n}':<10} {f'{theme}/{n}':<8} {proto_cell:<10} {f'{struct}/{n}':<12} {f'{props_}/{n}':<7}"
        )
    return "\n".join(lines)


def write_report(
    runs: list[RunResult],
    specs: list[SeedSpec],
    *,
    model: str,
    base_url: str,
    runs_per_seed: int,
) -> Path:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")
    json_path = REPORTS_DIR / f"{ts}.json"
    md_path = REPORTS_DIR / f"{ts}.md"

    json_path.write_text(
        json.dumps(
            {
                "timestamp": ts,
                "model": model,
                "base_url": base_url,
                "runs_per_seed": runs_per_seed,
                "specs": [
                    {
                        "kind": s.kind,
                        "name": s.name,
                        "props": list(s.props_schema.keys()),
                        "emits": sorted(s.emits),
                        "subscribes": sorted(s.subscribes),
                        "structural": s.structural,
                    }
                    for s in specs
                ],
                "runs": [
                    {
                        **{k: v for k, v in dataclasses.asdict(r).items() if k != "dimensions"},
                        "dimensions": [dataclasses.asdict(d) for d in r.dimensions],
                    }
                    for r in runs
                ],
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    md_lines: list[str] = []
    md_lines.append(f"# Widget-generation eval — {ts}")
    md_lines.append("")
    md_lines.append(f"- Model: `{model}`")
    md_lines.append(f"- Endpoint: `{base_url}`")
    md_lines.append(f"- Runs per seed: {runs_per_seed}")
    md_lines.append("")
    md_lines.append("## Summary")
    md_lines.append("```")
    md_lines.append(summarise(runs))
    md_lines.append("```")
    md_lines.append("")
    for kind in sorted({r.seed_kind for r in runs}):
        md_lines.append(f"## {kind}")
        for r in [x for x in runs if x.seed_kind == kind]:
            md_lines.append(f"### run {r.run_index + 1}  ({r.elapsed_ms} ms)")
            if r.error:
                md_lines.append(f"- error: `{r.error}`")
            elif not r.parse_ok:
                md_lines.append(f"- parse failed; raw[:400]: `{r.raw_text[:400]}`")
            else:
                md_lines.append(f"- score: **{r.score:.2f}**")
                for d in r.dimensions:
                    mark = "✓" if d.passed else "✗"
                    detail = f" — {d.detail}" if d.detail else ""
                    md_lines.append(f"  - {mark} {d.name}{detail}")
                if r.draft is not None:
                    excerpt = (r.draft.get("html") or "")[:400]
                    md_lines.append("")
                    md_lines.append("<details><summary>html excerpt</summary>")
                    md_lines.append("")
                    md_lines.append("```html")
                    md_lines.append(excerpt)
                    md_lines.append("```")
                    md_lines.append("</details>")
            md_lines.append("")
    md_path.write_text("\n".join(md_lines), encoding="utf-8")
    print(f"\nReport written: {md_path.relative_to(REPO_ROOT)}")
    return md_path


def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Evaluate widget-generation quality against seed references.")
    p.add_argument("--runs", type=int, default=3, help="Generations per seed (default 3).")
    p.add_argument("--seed", action="append", help="Restrict to seed stem (e.g. --seed poll, --seed loud-poll). Repeatable.")
    p.add_argument("--loud-only", action="store_true", help="Run only the synthetic Loud cases.")
    p.add_argument("--skip-loud", action="store_true", help="Run only the legacy seed-based Quiet cases.")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    raise SystemExit(main())
