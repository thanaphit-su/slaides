# Widget Revisions And AI Workflow Contract

## Goal

Widgets are durable authored artifacts. A widget identity has metadata and points
to a current immutable revision. Each revision stores the executable source,
behavior contract, props schema, example props, and AI-readable spec.

## Data Ownership

- `widget` owns stable identity: deck, name, kind, description, tags, current revision.
- `widget_revision` owns versioned source and contract: html, js, css, props_schema,
  example_props, behavior, ai_spec.
- `slide_widget` owns placement: placement_id, widget_id, revision_id, props.
- `widget_ai_thread` owns durable conversation summary for a widget.
- `widget_ai_message` owns structured chat events: user, question, plan, step,
  reflection, draft, apply.

## Compatibility Rule

Until all render paths read revisions directly, API responses keep flattening the
current revision onto `WidgetOut` as `html`, `js`, `css`, `props_schema`, and
`behavior`.

## Behavior Rule

Quiet behavior is exactly `{ "kind": "quiet" }`.
Loud behavior requires `{ "kind": "loud", "aggregator": "tally",
"contribution_schema": {"type": "string"} }` or the equivalent shape for
another supported aggregator.
Invalid Loud behavior returns 422 and is never persisted.

## AI Workflow Rule

The widget AI returns a structured JSON envelope:

- `question`: AI needs user input and includes option chips.
- `draft`: AI is confident and includes `widget`, `ai_spec`, and `example_props`.
- `plan`, `step`, and `reflection`: optional progress records stored in the thread.

Plain prose is invalid for widget generation/adjustment.

## Session History Rule

Any live/session historical view renders the revision captured at placement or
session materialization time. Editing the widget later cannot alter past sessions.
