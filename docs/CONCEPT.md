# SLAIDES — Product Concept

## What it is

A web-based **interactive slide platform** for instructors who want their audience to *do something*, not just sit there. The unit of authoring is a markdown document; the unit of presenting is a session. Every session records a transcript-ready interaction log: not just what was on the screen, but what the audience clicked, voted, typed, asked, and re-asked.

## Why it exists

Presentations today are one-directional. Live polling tools exist, but they bolt onto slides as a clunky second app and never let the instructor *teach with* the data the audience produces. SLAIDES collapses authoring, presenting, and the feedback loop into one tool with three first-class outputs:

1. **The deck** — markdown source, exportable, importable, version-able.
2. **The session** — a realtime conversation, with interaction logs that can power transcript and analytics work.
3. **The widget library** — every interactive component the instructor builds is reusable across decks.

## Users & roles

### Instructor (registered)
- Authors decks, builds widgets, configures the LLM, starts sessions.
- Sees the full audience: names, anonymous-but-hashed counterparts, questions, and live interaction state.
- Privileged actions: open polls/questions and mark questions answered.

### Audience — registered
- Joins by code or link; identifies with their workspace account.
- Their interactions are linked to their account in the session log.

### Audience — guest
- Joins by code or link, provides an **email + display name** OR an email and toggles **Anonymous mode**.
- Email is used to derive a per-session participant reference; in anonymous mode the email is salted+hashed and never displayed.
- Cannot author or build.

## The seven primary jobs-to-be-done

1. **Author a deck** in a focused, single-column, markdown-first editor. The page should feel like writing a journal entry, not laying out PowerPoint.
2. **Make a slide interactive** by inserting a widget — either picked from a library or generated on demand from a prompt.
3. **Generate or rewrite content with AI**, inline in the editor, without leaving the page.
4. **Run a live session** — share a code/link, watch audience join, walk the deck.
5. **Open a poll or question on the fly** during presentation, without having authored it ahead of time. Results stream to both presenter and audience in realtime.
6. **Field audience questions** — see the live queue, mark answered, optionally jump to the relevant slide.
7. **Look back** — use the captured votes, questions, and interpretation requests to improve the deck. The transcript UI/export is planned for M5; the current product persists the underlying interaction data.

## The eight design principles

1. **Editorial, not corporate.** The deck reads like a magazine essay. Serif display, generous leading, marginalia. The UI chrome around it is quiet sans-serif so the content stays the loudest voice.
2. **Markdown is the source of truth.** Every slide is `.md`. No drag-to-position. No invisible layout objects. If you can read the source, you can read the slide.
3. **Markdown stays readable.** The current implementation stores each slide as its own markdown document. It does not auto-split typed content on H1; new slides are created explicitly.
4. **Widgets are real software, not props.** They run in a sandbox, can be hand-edited, exported, and shared.
5. **The audience is part of the deck.** Their interactions are first-class content — visible to the presenter without leaving the slide.
6. **Anonymous means anonymous to humans, traceable to the system.** Hash the identifier; keep the content. Never store cleartext PII on an anonymous interaction.
7. **The LLM is a tool, not a feature.** It lives behind contextual menus and inline prompts, never as a hovering pop-up. The instructor's voice stays louder than the model's.
8. **Right-click is a real menu.** Authors and audience can right-click any text to act on it (copy, interpret, translate). This is the muscle memory people already have.

## What v0.1 is and isn't

**v0.1 is** the smallest end-to-end product that proves the loop: author a markdown deck with one AI-generated widget, present it live to an audience that includes one guest and one anonymous attendee, and persist the interaction data needed for later transcript work.

**v0.1 is not** team collaboration, paid plans, mobile-native apps, widget marketplaces, advanced analytics dashboards, slide animations, exports to PowerPoint, video calls, or any form of "presenter notes" beyond what the instructor types in markdown.

## Why now, why this team

The arrival of competent, cheap LLMs makes both "interpret this term" and "generate a widget from a prompt" feasible for a single instructor without an engineering team. That capability deserves a presentation tool built around it, not stapled to one.

## What success looks like (v0.1)

- An instructor can author and run an hour-long session without leaving the app.
- An audience member can join from a phone in under 15 seconds — no app install.
- A live poll opens and resolves in under 5 seconds end-to-end.
- 80% of guest joins choose to provide an email (anonymous or not), validating the privacy bargain.
- One widget generated by a single instructor gets reused in three other decks (proves the library is useful).
