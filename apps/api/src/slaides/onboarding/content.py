"""Tutorial deck + starter widget pack — pure data.

Slide markdown lives inline; widget bodies live alongside as
`widgets/<kind>.{html,js,css}` so they stay reviewable as plain text
(and so a future "regenerate the starter pack from an LLM run" tool can
rewrite them without touching this module).

Each widget is authored against the same contracts the LLM is held to:

- THEME — no hex colors, no `rgb(...)`, no named colors on color
  properties, no hardcoded font-family names.
- LAYOUT — no fixed-pixel `max-width` caps; widgets fill the iframe.
- BEHAVIOR — Quiet widgets do not call `slaides.contribute(...)`; Loud
  widgets both call `contribute(...)` AND subscribe via
  `slaides.on('state', cb)`.
- PROPS — every widget reads from `window.slaides.props` and supports
  live updates via `slaides.on('props', cb)`.
- BRIDGE — uses `window.slaides` for all host interaction.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_WIDGETS_DIR = Path(__file__).resolve().parent / "widgets"

TUTORIAL_DECK_TITLE = "Welcome to SLAIDES"
TUTORIAL_DECK_SUBTITLE = "A 10-slide tour of editing, widgets, AI, and going live."
TUTORIAL_VERSION = 2


@dataclass(frozen=True)
class StarterWidget:
    """One bundled widget. The `kind` doubles as the placement_id used in
    tutorial slide markdown (`{{widget:<kind>}}`)."""

    kind: str
    name: str
    description: str
    behavior: dict[str, Any]
    props_schema: dict[str, Any]
    tags: tuple[str, ...] = field(default_factory=tuple)

    @property
    def html(self) -> str:
        return (_WIDGETS_DIR / f"{self.kind}.html").read_text(encoding="utf-8")

    @property
    def js(self) -> str:
        return (_WIDGETS_DIR / f"{self.kind}.js").read_text(encoding="utf-8")

    @property
    def css(self) -> str:
        return (_WIDGETS_DIR / f"{self.kind}.css").read_text(encoding="utf-8")


STARTER_WIDGETS: list[StarterWidget] = [
    StarterWidget(
        kind="concept-card",
        name="Concept Card",
        description="Title + definition + example. A presentational card for vocabulary or definitions.",
        behavior={"kind": "quiet"},
        tags=("concept", "definition", "presentational"),
        props_schema={
            "properties": {
                "title": {
                    "type": "string",
                    "description": "Term being defined.",
                    "default": "Widget",
                },
                "definition": {
                    "type": "string",
                    "description": "One-sentence definition.",
                    "default": "A sandboxed interactive embedded in a slide; props customize it.",
                },
                "example": {
                    "type": "string",
                    "description": "A concrete example or usage note.",
                    "default": "Open the right sidebar to add more widgets to this slide.",
                },
            }
        },
    ),
    StarterWidget(
        kind="quick-quiz",
        name="Quick Quiz",
        description="Single-question multiple choice with show-correct feedback. Each viewer answers locally.",
        behavior={"kind": "quiet"},
        tags=("quiz", "self-check", "quiet"),
        props_schema={
            "properties": {
                "question": {
                    "type": "string",
                    "description": "The question prompt.",
                    "default": "Which of these is a Loud widget?",
                },
                "choices": {
                    "type": "array",
                    "description": "Answer choices. The id is referenced by correct_answer.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "string", "minLength": 1},
                            "label": {"type": "string", "minLength": 1},
                        },
                    },
                    "default": [
                        {"id": "a", "label": "Concept Card"},
                        {"id": "b", "label": "Live Poll"},
                        {"id": "c", "label": "Carousel"},
                    ],
                },
                "correct_answer": {
                    "type": "string",
                    "description": "id of the correct choice.",
                    "enum.from": "choices.id",
                    "default": "b",
                },
            }
        },
    ),
    StarterWidget(
        kind="live-poll",
        name="Live Poll",
        description="Loud single-choice poll. Audience votes; bar tally renders in real time.",
        behavior={
            "kind": "loud",
            "aggregator": "tally",
            "contribution_schema": {"type": "string"},
        },
        tags=("poll", "vote", "loud"),
        props_schema={
            "properties": {
                "question": {
                    "type": "string",
                    "description": "The poll question.",
                    "default": "Which feature do you want to see next?",
                },
                "choices": {
                    "type": "array",
                    "description": "Voting options.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "string", "minLength": 1},
                            "label": {"type": "string", "minLength": 1},
                        },
                    },
                    "default": [
                        {"id": "transcripts", "label": "Transcripts"},
                        {"id": "transitions", "label": "Slide transitions"},
                        {"id": "mobile", "label": "Better mobile UX"},
                    ],
                },
            }
        },
    ),
    StarterWidget(
        kind="word-cloud",
        name="Word Cloud",
        description="Loud word collector. Audience submits one word; deduped cloud sizes by appearance order.",
        behavior={
            "kind": "loud",
            "aggregator": "set_union",
            "contribution_schema": {"type": "string", "maxLength": 40},
        },
        tags=("words", "cloud", "loud"),
        props_schema={
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": "Submission prompt shown to the audience.",
                    "default": "In one word, how does this slide feel?",
                },
                "max_length": {
                    "type": "number",
                    "description": "Max characters per submission.",
                    "default": 30,
                    "minimum": 1,
                    "maximum": 60,
                },
            }
        },
    ),
    StarterWidget(
        kind="qa-board",
        name="Q&A Board",
        description="Loud open-question stream. Audience submits questions; latest renders on top.",
        behavior={
            "kind": "loud",
            "aggregator": "append",
            "contribution_schema": {"type": "string", "maxLength": 280},
        },
        tags=("questions", "qa", "loud"),
        props_schema={
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": "Prompt shown above the input.",
                    "default": "Ask anything",
                },
                "placeholder": {
                    "type": "string",
                    "description": "Placeholder in the input.",
                    "default": "Your question…",
                },
            }
        },
    ),
    StarterWidget(
        kind="reaction-wall",
        name="Reaction Wall",
        description="Loud emoji reactions. Per-emoji counter ticks as the audience taps.",
        behavior={
            "kind": "loud",
            "aggregator": "keyed_tally",
            "contribution_schema": {"type": "string"},
        },
        tags=("reactions", "emoji", "loud"),
        props_schema={
            "properties": {
                "keys": {
                    "type": "array",
                    "description": "Available reactions.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "key": {"type": "string", "minLength": 1},
                            "label": {"type": "string", "minLength": 1},
                        },
                    },
                    "default": [
                        {"key": "fire", "label": "🔥"},
                        {"key": "hundred", "label": "💯"},
                        {"key": "thinking", "label": "🤔"},
                        {"key": "heart", "label": "❤️"},
                    ],
                }
            }
        },
    ),
    StarterWidget(
        kind="pulse-check",
        name="Pulse Check",
        description="Loud confidence meter. Audience sets current state (1–N); histogram updates.",
        behavior={
            "kind": "loud",
            "aggregator": "latest_per_participant",
            "contribution_schema": {"type": "string"},
        },
        tags=("pulse", "confidence", "loud"),
        props_schema={
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": "Question above the scale.",
                    "default": "How confident are you with this material?",
                },
                "labels": {
                    "type": "array",
                    "description": "Scale labels left-to-right.",
                    "items": {"type": "string"},
                    "default": ["Lost", "Shaky", "OK", "Solid", "Could teach it"],
                },
            }
        },
    ),
    StarterWidget(
        kind="carousel",
        name="Carousel",
        description="Quiet image carousel. Prev/Next through a list of image URLs with optional captions.",
        behavior={"kind": "quiet"},
        tags=("images", "carousel", "quiet"),
        props_schema={
            "properties": {
                "images": {
                    "type": "array",
                    "description": "List of images to cycle through. Each entry has a URL and optional caption.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "url": {"type": "string", "minLength": 1},
                            "caption": {"type": "string"},
                        },
                    },
                    "default": [
                        {
                            "url": "https://upload.wikimedia.org/wikipedia/commons/thumb/4/47/PNG_transparency_demonstration_1.png/640px-PNG_transparency_demonstration_1.png",
                            "caption": "PNG transparency demo (Wikimedia Commons)",
                        },
                        {
                            "url": "https://upload.wikimedia.org/wikipedia/commons/thumb/3/3a/Cat03.jpg/640px-Cat03.jpg",
                            "caption": "Domestic cat (Wikimedia Commons)",
                        },
                    ],
                },
                "auto_advance": {
                    "type": "boolean",
                    "description": "Auto-advance every interval_ms.",
                    "default": False,
                },
                "interval_ms": {
                    "type": "number",
                    "description": "Auto-advance interval in milliseconds.",
                    "default": 4000,
                    "minimum": 1000,
                },
            }
        },
    ),
]


TUTORIAL_SLIDES: list[dict[str, str]] = [
    {
        "kicker": "§ 01 — Hello",
        "markdown": """# Welcome to SLAIDES.

You build a deck like a writer — slide by slide, in markdown. Then you drop in **widgets**: small, sandboxed interactives that turn a one-way lecture into a live conversation.

This deck is your tutorial. Walk it once and you'll know everything.

> Time: about five minutes to read, ten if you actually try the prompts.
""",
    },
    {
        "kicker": "§ 02 — Editing",
        "markdown": """# Click anywhere on a slide to edit it.

The toolbar at the top switches between **Rendered** and **Markdown** views. Both edit the same source; pick whichever feels faster.

Supported blocks: headings (`#` `##` `###`), paragraphs, lists (`-` or `1.`), quotes (`>`), tables, horizontal rules (`---`), and widgets.

> Try this: rename this slide's title above. The deck saves automatically.
""",
    },
    {
        "kicker": "§ 03 — Widgets",
        "markdown": """# Widgets are interactives you drop into a slide.

Each widget is sandboxed (it can't touch the rest of the page) and **props-driven** (you customize it without touching code).

{{widget:concept-card}}

Open the right sidebar — the **WIDGETS** pill — to see your library. Pick one, click *Add to slide*, done.
""",
    },
    {
        "kicker": "§ 04 — AI Generate",
        "markdown": """# Don't build widgets by hand. Ask for them.

Open the AI sidebar and type what you want. The model returns a draft you can preview, tweak, and apply.

> Try this prompt:
>
> *"a quick quiz with 3 trivia questions about photosynthesis"*

The first draft is rarely final — that's fine. The next slide shows how to iterate.
""",
    },
    {
        "kicker": "§ 05 — Adjust",
        "markdown": """# Iterate with chat.

Right-click any existing widget and pick **Adjust**. The sidebar enters Adjust mode with the widget as context. Tell it what to change.

{{widget:quick-quiz}}

> Try this: right-click the quiz above → Adjust → *"make the choices longer and add a fourth one about chlorophyll"*.

Each round produces a new draft; click *+ apply* when you like one.
""",
    },
    {
        "kicker": "§ 06a — Quiet",
        "markdown": """# Quiet widgets run privately.

Each viewer interacts with the widget on their own device. Nothing leaves their browser. Great for self-check exercises, formula explorers, flashcards — anything where the answer is for the student, not the room.

{{widget:quick-quiz}}

The quiz above is Quiet: every student's answer stays with them. The next slide shows the other half.
""",
    },
    {
        "kicker": "§ 06b — Loud",
        "markdown": """# Loud widgets aggregate across the audience.

Every vote lands on every screen in real time. Use Loud when the value of the interaction is *seeing the room respond together* — polls, word clouds, brainstorm boards, reactions.

{{widget:live-poll}}

When you generate a widget with AI, pick Quiet or Loud in the composer popover. The model wires the right plumbing.
""",
    },
    {
        "kicker": "§ 07 — Going Live",
        "markdown": """# Click **Start session** to go live.

You get a six-character session code (like `SLD-AB12-CD`) and a join URL. Share either with the room.

The audience opens the URL on their phone, picks a display name, and lands on your current slide. As you advance, they follow.

> Live interactions — polls, open questions, random-audience picks — launch from the blue `+` button on the bottom-right of the presenter view.
""",
    },
    {
        "kicker": "§ 08 — Preview",
        "markdown": """# Test with fake audiences before you ship.

Click **Preview** in the editor toolbar. A new tab opens with a meeting-app layout: a thumbnail of every view (Presenter + N fake students) on the left and the active view on the right.

You can spawn 1–12 fake audiences with the `+` / `−` stepper. Click a thumbnail to jump to that view.

Inspector mode (`inspect ◉` in the header) lets you click any DOM element in the active view to feed it as context into the AI Adjust chat. No more *"the button in the top right"* — the model sees the selector.
""",
    },
    {
        "kicker": "§ 09 — You're ready",
        "markdown": """# Go build something.

Open the workspace and click **+ New deck**. Use the starter widgets on this deck as a reference — copy them across decks via the right sidebar's *Copy from another deck* picker.

Delete this tutorial any time. It won't come back.

> Stuck? Every widget in the library is annotated. Open one in the Code tab to see how it's wired.
""",
    },
]
