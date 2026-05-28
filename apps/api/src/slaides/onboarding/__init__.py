"""Tutorial deck + starter widget pack provisioned to every approved instructor.

The package keeps three concerns separate:

- `content` — pure data: slide markdown + widget metadata loaded from sibling
  HTML/JS/CSS files.
- `service` — the idempotent `create_tutorial_for(session, user)` that builds
  the deck rows, attaches the widgets, and stamps `manifest.is_tutorial=True`.
- `widgets/` — one `.html` + `.js` + `.css` triple per starter widget,
  authored against the same theme/layout/behavior contracts the LLM is
  held to.
"""
