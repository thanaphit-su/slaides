# SLAIDES — Design Tokens

Direction: **Editorial Press**. A press for talks worth keeping. White paper, deep ink-blue accent, serif display with italics, quiet sans-serif chrome.

The canonical source is `src/theme.css`. This doc explains the choices and the system around them so you can extend it without breaking the voice.

---

## Colors

### Paper & ink

| Token | Light | Dark | Use |
|---|---|---|---|
| `--paper` | `#ffffff` | `#0d0e10` | Page background, primary card surface |
| `--paper-2` | `#f7f6f2` | `#15171a` | Subtle section background, hover surface |
| `--paper-3` | `#efede7` | `#1d2024` | Quieter surface |
| `--ink` | `#0b0d10` | `#f2efe8` | Primary text, headlines |
| `--ink-soft` | `#4b525b` | `#b1b4bc` | Secondary text, captions |
| `--ink-mute` | `#8a8f96` | `#7d8189` | Tertiary, meta, placeholder |
| `--ink-disabled` | `#b9bdc2` | `#4e5258` | Disabled state |

### Rules (1px borders)

| Token | Value | Use |
|---|---|---|
| `--rule` | `#e3e1dc` | Default 1px border |
| `--rule-soft` | `#ecebe6` | Quieter divider |
| `--rule-strong` | `#cfccc4` | Input borders, hover-elevated borders |

### Brand & accents

| Token | Value | Use |
|---|---|---|
| `--accent` | `#1f3a8a` | Deep ink-blue. Inline links, focus, primary accent (NOT the primary CTA color — that's `--ink`) |
| `--accent-2` | `#2845a6` | Hover variant |
| `--accent-soft` | `rgba(31,58,138,.08)` | Accent fill (badges, hover) |
| `--accent-tint` | `rgba(31,58,138,.13)` | Selection highlight, focus ring |
| `--amber` | `#c2410c` | Warm secondary — chart line, occasional second accent |
| `--meadow` | `#117a45` | Success / confirm |
| `--rose` | `#be1d4a` | Live, error, destructive |

### Semantic

| Token | Value | Use |
|---|---|---|
| `--ok` | `#117a45` | Confirmation |
| `--warn` | `#c2410c` | Mid-priority alert |
| `--err` | `#be1d4a` | Validation error |
| `--live` | `#be1d4a` | LIVE state on sessions (pulse animation on dots) |

### Dark mode

Dark mode redefines the variables on `.dark`. Notable shifts:

- Paper darkens to `#0d0e10` (true near-black).
- Ink softens to a warm bone (`#f2efe8`) to avoid harsh white on dark.
- Accent shifts to a lighter blue (`#8bb0ff`) for AA contrast on the dark paper.

The dark mode is invoked via `.dark` class on the page root or a section root. Current Settings UI labels per-user persistence as later-release work.

---

## Type

### Families

| Token | Font | Fallback chain |
|---|---|---|
| `--serif` | **Newsreader** | `'Newsreader', 'Fraunces', Georgia, serif` |
| `--sans` | **Inter** | `'Inter', system-ui, sans-serif` |
| `--mono` | **IBM Plex Mono** | `'IBM Plex Mono', ui-monospace, monospace` |

Newsreader gives us a humane, magazine-warm display with real italics. Inter is the workhorse for UI chrome (buttons, labels). Plex Mono handles every numeric/metadata moment — version numbers, share codes, time-ago labels.

### Scale (named classes in `src/theme.css`)

| Class | Size | Weight | Line height | Letter spacing | Use |
|---|---|---|---|---|---|
| `.t-display` | 80px | 400 | 1.04 | -0.025em | Hero / signin headline |
| `.t-h1` | 56px | 400 | 1.06 | -0.025em | Workspace hero |
| `.t-h2` | 36px | 400 | 1.15 | -0.02em | Section openers |
| `.t-h3` | 28px | 400 | 1.25 | -0.015em | Card titles |
| `.t-h4` | 22px | 500 | 1.3 | 0 | Sub-headlines |
| `.t-lede` | 20px | 300 | 1.55 | 0 | Pull quotes, descriptions (serif, light) |
| `.t-body` | 18px | 400 | 1.7 | 0 | Slide body text (serif) |
| `.t-body-sans` | 14px | 400 | 1.55 | 0 | UI body (Inter) |
| `.t-kicker` | 11px | 600 | 1.6 | 0.18em | Uppercase pre-headline (accent color) |
| `.t-meta` | 12px | 400 | — | 0 | Metadata (Inter, soft ink) |
| `.t-mono` | 11px | 400 | — | 0.04em | Codes, IDs, timestamps |
| `.t-mono-up` | 11px | 400 | — | 0.1em | Uppercase mono — section labels |
| `.t-btn` | 13px | 600 | 1.3 | 0 | Button labels (Inter) |

### Principles

1. **Italics carry the voice.** Display headlines emphasize *one word* in italic to set tone. Don't use bold for emphasis in headlines — italics only.
2. **Serif for content, sans for chrome.** Slide body, lede, card titles → Newsreader. Buttons, labels, badges → Inter.
3. **Generous leading on body (1.7).** Reading is the job. Don't compress.
4. **Tight leading on display (1.04).** Display sets the visual mass.
5. **Letter-spacing tightens with size.** -0.025em on display, settles to 0 by 22px.

---

## Spacing

A 4px base, named tokens. Use these, not raw pixels.

| Token | Value | Common use |
|---|---|---|
| `--s-1` | 4px | Hairline gap |
| `--s-2` | 8px | Inline gap |
| `--s-3` | 12px | Tight padding |
| `--s-4` | 16px | Default padding |
| `--s-5` | 24px | Card padding, comfortable row |
| `--s-6` | 32px | Section padding |
| `--s-7` | 48px | Major spacing |
| `--s-8` | 64px | Hero padding |
| `--s-9` | 96px | Page-level rhythm |

---

## Radii

| Token | Value | Use |
|---|---|---|
| `--r-xs` | 4px | Tag chips, tiny accents |
| `--r-sm` | 6px | Small badges, kbd |
| `--r-md` | 8px | **Buttons**, inputs, search-pill |
| `--r-lg` | 12px | **Cards**, drawers, panels |
| `--r-xl` | 16px | Large feature panels |
| `--r-2xl` | 20px | Showcase cards |
| `--r-pill` | 9999px | Pill badges, dots, audience-count chip |

Note: **buttons are rectangles, not pills.** Pill radius is reserved for badges and status chips.

---

## Elevation

| Token | Value | Use |
|---|---|---|
| `--shadow-1` | `0 1px 2px rgba(15,15,15,.04)` | Hover-elevated tiles |
| `--shadow-2` | `0 4px 14px rgba(15,15,15,.08)` | Cards, popovers |
| `--shadow-3` | `0 24px 48px -8px rgba(15,15,15,.18)` | Hero mockup, modal |
| `--shadow-4` | `0 16px 48px -8px rgba(15,15,15,.20)` | Drawers, dropdowns |

Editorial Press is restrained with shadows. The hero mockup and live drawers earn elevation; everything else relies on a 1px rule.

---

## Motion

Four utility classes, four uses:

| Class | Keyframes | Duration | Easing | Use |
|---|---|---|---|---|
| `.fade-in` | opacity 0 → 1 | 250ms | ease | Anything appearing softly |
| `.slide-up` | translateY 8 → 0 + fade | 300ms | cubic-bezier(.2,.7,.2,1) | Modal & sheet appear |
| `.slide-in-right` | translateX 20 → 0 + fade | 300ms | cubic-bezier(.2,.7,.2,1) | Drawer, right rail |
| `.scale-in` | scale .96 → 1 + fade | 200ms | cubic-bezier(.2,.7,.2,1) | Menus, popovers |

Plus `.pulse` (1.6s infinite) for the LIVE dot.

Principles:

1. **One easing curve.** Almost everything that moves uses the same cubic-bezier — variation should be on duration and distance, not curve.
2. **Quick and small.** Nothing animates longer than 300ms. If you need longer, you're animating the wrong thing.
3. **Respect `prefers-reduced-motion`.** The motion utility classes degrade to instant transitions when the OS asks.

---

## Components (reference)

### Buttons

- `.btn` — default, light surface, 1px border, 8px radius, 13px Inter 500.
- `.btn-primary` — black surface, white text. The dominant action on a screen.
- `.btn-accent` — ink-blue surface. Used for emphasis live actions (e.g. "Open interaction" on the presenter).
- `.btn-ghost` — no border, no fill, soft ink color. For toolbar dismisses and tertiary actions.
- `.btn-sm` and `.btn-lg` are vertical size adjustments.

### Inputs

- `.input` — 10px/12px padding, 8px radius, 1px strong rule border. Focus shifts the border to `--accent` with a 3px accent-soft halo.
- `.field-label` — uppercase 12px Inter 600 in soft ink. Pairs above an input.

### Cards

- `.card` — 1px rule, 12px radius, 24px padding. Default content container.
- `.card-flat` — same but tighter (8px radius), for nested lists.

### Badges

- `.badge` — pill, 11px Inter 600, soft fill + 1px rule.
- Variants: `.badge-accent` (ink-blue tint), `.badge-live` (rose fill, white text), `.badge-amber`.

### Live dot

`LiveDot` component: a 6–10px circle with a pulsing halo. Use only for LIVE indicators — overuse blunts the signal.

---

## Wordmark

`SLAIDES` set in `var(--serif)`, weight 500, letter-spacing 0.22em. Paired with a small framed icon (a deck mark — a stylized rectangle with a baseline divider and a single ink dot). Available as a single component `<Wordmark size={...}>`.

The wordmark is the only place where we use serif uppercase with wide letter-spacing. Don't extend this treatment to other titles — they should use mixed case + italics instead.

---

## Iconography

Hand-tuned single-stroke icons on a 20×20 grid. 1.4px stroke weight, rounded caps and joins. No filled-shape icons except play / pause and a couple of dots — keep the visual language *drawn*, not iconic.

If you need an icon that isn't in the prototype set, draw a new one to the same constraints: single 20×20 viewBox, ≤2 strokes, ≤1 stroke weight (1.4), rounded caps.

---

## Don'ts

- Don't use the ink-blue accent as a background on big surfaces. It's an *accent*.
- Don't introduce a third UI font. Newsreader + Inter + Plex Mono is the system.
- Don't add gradients. Editorial Press is paper-flat.
- Don't pill-shape buttons. Buttons are rectangles.
- Don't use the rose / live red for anything other than LIVE state or destructive actions.
- Don't bold for emphasis in display type. Italic.
