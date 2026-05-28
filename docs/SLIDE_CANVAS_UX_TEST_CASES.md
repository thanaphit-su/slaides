# Slide Canvas UX/UI Usability Test Cases

Date: 2026-05-28 (updated from 2026-05-20)
App: SLAIDES
Target area: Slide editor canvas at `http://localhost:5173`

**Note:** Updated to reflect persistent right sidebar widget collection, AI Adjust workflow, and widget revision system (migration 0015).

## Scope

This test plan covers the current slide canvas experience in the editor:

- Rendered slide editing.
- Inline Markdown editing.
- Switching between rendered and Markdown modes.
- Slide insertion around the active slide.
- Selection formatting controls.
- Context menu actions on the canvas.
- Widget insertion, adjustment, and rendering inside a slide.
- Canvas autosave, repaint, and persistence behavior.
- Nearby editor controls that directly affect the canvas, including sidebar slide selection, section state, and slide navigation.

The plan does not cover the full presentation runtime, full export fidelity, billing, account management, or backend-only API behavior except where those flows affect canvas usability.

## Current Feature Inventory

### Canvas Modes

- The active slide has two editing modes:
  - `Rendered`: a contenteditable rendered slide canvas.
  - `Markdown`: an inline textarea editor for the same slide Markdown.
- The old modal-based "Edit as Markdown" flow is no longer expected.
- Switching modes should preserve the same slide content and should not create duplicate content.
- Markdown edits and rendered edits both update the same slide Markdown field.

### Rendered Editing

- The rendered canvas supports direct typing into the slide.
- Empty slides render as an editable empty paragraph.
- Markdown is rendered into editable blocks:
  - H1: `# Heading`
  - H2: `## Heading`
  - H3: `### Heading`
  - Paragraph
  - Blockquote: `> Quote`
  - Horizontal rule: `---` or `___`
  - Widget placeholder: `{{widget:id}}`
- Inline Markdown rendering supports:
  - Bold: `**text**`
  - Italic: `*text*`
  - Inline code: `` `text` ``
  - Links: `[label](https://example.com)`
- Direct typing shortcuts support converting leading heading syntax:
  - `# ` creates an H1 block.
  - `## ` creates an H2 block.
  - `### ` creates an H3 block.

### Selection Toolbar

When text is selected inside the rendered canvas, a floating toolbar can provide:

- Bold.
- Italic.
- Underline.
- H1.
- H2.
- Paragraph.
- Blockquote.
- Inline code.
- Link.
- Interpret with AI.

Known usability risk to validate: underline can be applied visually through the browser editing command, but Markdown serialization may not preserve underline after repaint or reload.

### Context Menu

Right-clicking the canvas opens the custom context menu. Current supported actions include:

- Copy.
- Cut.
- Paste.
- Interpret with AI when text is selected.
- Insert widget from collection when the slide has no widget.
- Generate widget when the slide has no widget.
- Adjust widget when the slide already has a widget.
- Delete slide, disabled when the deck has only one slide.

The context menu should not include "Edit as Markdown" because Markdown is now an inline mode.

### Slide Insertion

- A top hover ribbon appears near the top of the active slide canvas.
- Clicking "Add slide above" inserts a new slide immediately before the active slide.
- If the active slide belongs to a section, the new slide should remain in that same section.

### Widget Canvas Behavior

- A slide can contain exactly one widget (1-widget-per-slide rule enforced).
- Widget collection is a **persistent right sidebar** (not a drawer or modal) with mode-specific panels:
  - Library/create mode: deck-local widgets, cross-deck copy picker, and AI generation chat.
  - Adjust mode: selected-widget chat plus props/code controls when available.
  - Code editing uses HTML/JS/CSS editors with an explicit Save button.
- Widget insertion paths:
  - Drag from sidebar library card to slide canvas
  - "Add to slide" from AI Generate preview card
  - Context menu "Insert from collection" (when no widget present)
  - Context menu "Generate widget…" (when no widget present)
- Widget blocks render as non-editable canvas blocks with hover/focus-only chrome (Adjust/Remove icons, bottom-right)
- Adjust workflow:
  - Opens AI Adjust tab in sidebar with widget as context
  - AI chat produces widget revisions (not overwrites)
  - Apply creates new `widget_revision`; canvas repaints via `widgetRev` bump
  - Manual Code tab edits are local drafts until Save clicked
- Props customization:
  - Props tab shows form rendered from `widget.props_schema`
  - Placement-specific (same widget, different props per slide)
  - PATCH validated against schema (422 on violation)
- Widget-only slides use fill layout (min-height 560px in editor, 360px in previews)
- Widget placeholders serialize and reload as `{{widget:placement_id}}`
- Canvas watches `widgetRev` counter to repaint after:
  - Widget preload
  - AI Apply
  - Code tab Save
  - Attach/detach
  - Library delete

### Autosave And Persistence

- Rendered canvas edits autosave after input.
- Markdown mode edits use the same save path and flush on blur.
- The canvas should not lose caret position during local typing because external repaint is suppressed for self-emitted Markdown.
- Changing slides, changing sections, widget updates, or external Markdown changes should repaint the active canvas without stale DOM.

## Test Environment

Use these baseline environments unless a case specifies otherwise:

- Browser: Chromium-based browser.
- App URL: `http://localhost:5173`.
- Viewport A: desktop, 1440 x 900 or larger.
- Viewport B: narrow desktop/mobile simulation, 390 x 844.
- Test data: create a fresh deck with one section and one slide.
- User state: authenticated editor user.

For each case, record:

- Pass/fail.
- Browser and viewport.
- Whether the behavior was discoverable without developer knowledge.
- Any visible layout overlap, clipped text, focus loss, or unexpected content mutation.

## Test Cases

| ID | Feature | Steps | Expected Result | Usability Focus |
| --- | --- | --- | --- | --- |
| SC-001 | Initial canvas load | Create a fresh deck and open the editor. | One slide is visible in rendered mode. The section kicker, slide title area, sidebar slide item, and bottom slide stepper are visible and aligned. | First impression, orientation, visual hierarchy. |
| SC-002 | Rendered to Markdown switch | Type `Plain title` in rendered mode, wait for autosave, then click `Markdown`. | Inline textarea appears in place of the rendered canvas. It contains the current slide content, not an empty value. No modal opens. | Mode discoverability, data continuity. |
| SC-003 | Markdown to rendered switch | In Markdown mode, replace content with `# Markdown Title`, then click `Rendered`. | The slide renders a styled H1 `Markdown Title`. The old text is not duplicated. | Consistency between modes. |
| SC-004 | Markdown save on blur | In Markdown mode, type `# Blur Save Test`, click outside the textarea, then reload the page. | The reloaded slide still contains `# Blur Save Test` and renders it correctly in rendered mode. | Save feedback, persistence. |
| SC-005 | Empty slide editability | Create or clear a slide so its Markdown is empty, then switch to rendered mode and click the canvas. | The empty slide shows an editable insertion point or empty text area. Typing starts in the expected location. | Empty state usability. |
| SC-006 | Rendered typing persistence | In rendered mode, type `Rendered edit persistence`, wait for autosave, reload the page. | The text remains after reload and no duplicate paragraph appears. | Basic editing trust. |
| SC-007 | H1 shortcut | In rendered mode on an empty block, type `# My Title`. | The block becomes a styled H1 with text `My Title`; the `# ` prefix is removed. | Direct manipulation, Markdown consistency. |
| SC-008 | H2 shortcut | In rendered mode on an empty block, type `## Section Title`. | The block becomes a styled H2 with text `Section Title`; the `## ` prefix is removed. | Shortcut consistency. |
| SC-009 | H3 shortcut | In rendered mode on an empty block, type `### Detail Title`. | The block becomes a styled H3 with text `Detail Title`; the `### ` prefix is removed. | Shortcut consistency and hidden capability validation. |
| SC-010 | Selection toolbar visibility | Type a sentence, select part of it, then click outside the selected text. | Toolbar appears only while a non-collapsed canvas selection exists and disappears when selection is cleared or focus leaves the canvas. | Contextual controls, visual noise. |
| SC-011 | Bold formatting | Select text in rendered mode, click Bold, switch to Markdown mode. | Markdown contains `**selected text**` or equivalent bold serialization. Rendered mode displays bold text. | Formatting reliability. |
| SC-012 | Italic formatting | Select text in rendered mode, click Italic, switch to Markdown mode. | Markdown contains `*selected text*` or equivalent italic serialization. Rendered mode displays italic text. | Formatting reliability. |
| SC-013 | Inline code formatting | Select text in rendered mode, click inline code, switch to Markdown mode. | Markdown contains backticks around the selected text. Rendered mode displays inline code styling. | Formatting reliability. |
| SC-014 | Link formatting | Select text, click Link, enter `https://example.com`, then switch to Markdown. | Markdown contains `[selected text](https://example.com)`. Rendered mode displays a link. | Error prevention, prompt clarity. |
| SC-015 | Link cancel | Select text, click Link, cancel the URL prompt. | The selected text is unchanged and no broken Markdown is inserted. | Recoverability. |
| SC-016 | Underline persistence | Select text, click Underline, switch modes or reload. | Record actual behavior. If underline disappears after serialization, log as a usability defect or unsupported formatting gap. | Consistency, data loss risk. |
| SC-017 | Toolbar block H1 | Select or place cursor in a paragraph, click H1. | The block becomes H1 visually and serializes as `# ...` in Markdown mode. | Formatting predictability. |
| SC-018 | Toolbar block H2 | Select or place cursor in a paragraph, click H2. | The block becomes H2 visually and serializes as `## ...` in Markdown mode. | Formatting predictability. |
| SC-019 | Toolbar paragraph | Convert a heading to paragraph with the paragraph control. | The block returns to paragraph styling and Markdown no longer has a heading prefix. | Reversibility. |
| SC-020 | Toolbar blockquote | Select or place cursor in a paragraph, click blockquote. | The block becomes a blockquote and serializes with `> `. | Formatting predictability. |
| SC-021 | Markdown horizontal rule | In Markdown mode enter `# Title\n\n---\n\nAfter`, then switch to rendered. | A horizontal rule appears between `Title` and `After`; no editable layout break occurs. | Markdown rendering completeness. |
| SC-022 | Context menu replacement | Right-click inside the rendered canvas. | Context menu appears with canvas actions. It does not contain "Edit as Markdown". | New workflow clarity. |
| SC-023 | Context menu copy | Select text, right-click, choose Copy, paste into another text field. | The selected text is copied accurately. | Platform expectation. |
| SC-024 | Context menu cut | Select text, right-click, choose Cut. | Selected text is removed from the canvas and can be pasted elsewhere. Autosave preserves the cut state. | Data mutation clarity. |
| SC-025 | Context menu paste | Copy plain text externally, right-click the canvas, choose Paste. | Text is inserted at the caret without corrupting surrounding Markdown. | Editing ergonomics. |
| SC-026 | Context menu AI visibility | Select text and right-click, then right-click again with no selection. | "Interpret with AI" is available only when selection exists. | Action relevance. |
| SC-027 | Interpret with AI insertion | Select text, use Interpret with AI, complete the popover flow. | Generated or returned interpretation is inserted into the slide without removing unrelated content. | AI flow discoverability and insertion safety. |
| SC-028 | Delete last slide disabled | On a one-slide deck, right-click the canvas. | Delete slide is disabled or unavailable in a way that clearly prevents deleting the last slide. | Destructive action safety. |
| SC-029 | Delete slide confirmation | Add a second slide, right-click a slide, choose Delete slide, cancel, then repeat and confirm. | Cancel keeps the slide. Confirm removes only the selected slide and updates sidebar and stepper. | Recoverability, confirmation clarity. |
| SC-030 | Add slide above same section | In the first slide of a named section, hover near the top of the canvas and click Add slide above. | New slide appears before the original slide and remains inside the same section in the sidebar. It is not labeled unsectioned. | Section hierarchy integrity. |
| SC-031 | Add slide hover behavior | Move the pointer near and away from the top of the active slide. | The add-slide ribbon appears predictably near the top and disappears without shifting slide content. | Discoverability, layout stability. |
| SC-032 | Sidebar slide switching | Create three slides with unique content. Click each sidebar slide item. | Canvas updates to the selected slide with no stale content from the previous slide. | Navigation reliability. |
| SC-033 | Bottom stepper navigation | With multiple slides, use Prev and Next. | Active slide, sidebar selection, stepper count, and canvas content remain synchronized. | Multi-control consistency. |
| SC-034 | Section rename reflected in canvas | Rename the active slide's section in the sidebar. | The canvas section kicker updates to the new section name. | Immediate feedback. |
| SC-035 | Slide reorder within section | Drag a slide in the sidebar to a new position in the same section. | Sidebar order, bottom stepper position, and canvas active slide position update consistently. | Spatial model consistency. |
| SC-036 | Slide move across sections | Move a slide from one section to another in the sidebar. | The slide appears in the target section and the canvas kicker reflects the target section. | Section ownership clarity. |
| SC-037 | Add-widget ribbon empty slide | On an empty or title-only slide in rendered mode, blur the canvas and observe the lower canvas area. | Add-widget ribbon is visible with From collection and Generate with AI. | Widget discovery. |
| SC-038 | Add-widget ribbon hidden while editing | Focus the canvas text editor. | Add-widget ribbon hides so it does not compete with typing or selection. | Editing focus. |
| SC-039 | Add-widget ribbon hidden in Markdown mode | Switch to Markdown mode. | Add-widget ribbon is hidden. Widget actions should remain reachable through the appropriate editor controls if supported. | Mode-specific affordances. |
| SC-040 | Insert widget from collection | Use From collection from the add-widget ribbon or context menu and select a widget. | A single widget appears in the slide, non-editable as text, and the slide Markdown contains one widget placeholder. | Insertion confidence. |
| SC-041 | Generate widget entry | Use Generate with AI from the add-widget ribbon or context menu. | The generator UI opens and is associated with the active slide. Canceling returns to the canvas without content loss. | Workflow entry clarity. |
| SC-042 | One-widget limit | After a slide has a widget, right-click the canvas and inspect widget actions. | Insert/generate actions are replaced by Adjust widget or a clear max-reached state. A second widget cannot be inserted into the same slide. | Constraint communication. |
| SC-043 | Widget adjust from canvas | Click the widget Adjust button or right edge Adjust widget tab. | Widget adjustment panel opens for the active widget. | Direct manipulation. |
| SC-044 | Widget non-editable boundary | Try to place the text caret inside a rendered widget and type. | Text is not inserted into the widget frame. Canvas text before or after the widget remains editable if available. | Interaction boundary clarity. |
| SC-045 | Widget placeholder round trip | Insert a widget, switch to Markdown, verify `{{widget:id}}`, add text before and after it, switch back to rendered. | Widget remains in the correct position and surrounding text renders correctly. | Serialization integrity. |
| SC-046 | Widget-only fill layout | Create a slide with only one widget and no other text. | Widget uses the larger fill presentation without overlapping sidebar, footer, or right edge controls. | Layout quality. |
| SC-047 | Widget repaint after adjustment | Adjust widget settings, apply changes, and return to the canvas. | Widget preview updates without requiring a full page reload. | Feedback latency. |
| SC-048 | Autosave rapid typing | Type continuously for 10 seconds in rendered mode, then immediately switch slides and return. | Latest text is preserved, no partial duplicate blocks appear, and save state eventually settles. | Data loss prevention. |
| SC-049 | Autosave rapid mode switching | Edit text in Markdown mode, switch quickly to rendered, edit again, then reload. | Final visible content persists and is not duplicated or reverted. | Race condition resilience. |
| SC-050 | Export after pending edit | Make a small canvas edit and immediately use Export. | Exported content includes the latest edit or the UI blocks export until pending save is flushed. | Trust in output. |
| SC-051 | Preview after pending edit | Make a small canvas edit and immediately use Preview. | Preview reflects the latest edit or clearly indicates if preview uses last saved content. | Cross-flow consistency. |
| SC-052 | Responsive desktop layout | At 1440 x 900, test rendered mode, Markdown mode, context menu, toolbar, add-slide ribbon, add-widget ribbon, and right tab. | Controls do not overlap each other or hide active content. Text fits inside buttons. | Visual polish. |
| SC-053 | Responsive narrow layout | At 390 x 844, repeat key canvas interactions. | Canvas remains usable, text does not clip, controls remain reachable, and no fixed element blocks editing. | Small viewport usability. |
| SC-054 | Keyboard focus order | Use Tab and Shift+Tab through editor controls around the canvas. | Mode toggle, canvas editor, toolbar buttons when visible, sidebar controls, and footer navigation have logical focus order and visible focus states. | Accessibility. |
| SC-055 | Keyboard text editing | In rendered mode, use standard keyboard shortcuts such as select all, copy, paste, undo, and redo. | Browser-standard editing shortcuts work without breaking Markdown serialization. | Power-user workflow. |
| SC-056 | Escape behavior | Open context menu, widget panel, or AI popover and press Escape. | The topmost transient UI closes without modifying slide content. | Predictable dismissal. |
| SC-057 | Unsupported Markdown visibility | Enter Markdown syntax that is not supported, such as a list or table. | The UI handles it predictably, either as plain text or a supported fallback, without broken layout or data loss. | Graceful degradation. |
| SC-058 | Rich paste normalization | Paste formatted text from an external rich-text source into rendered mode. | The canvas normalizes content to supported blocks and inline marks. Unsupported styling does not create broken DOM or unsavable Markdown. | Paste robustness. |
| SC-059 | Browser reload during editing | Type in rendered mode, wait less than the debounce interval, then reload immediately. | Record whether latest input survives. If it does not, check whether the UI warned about unsaved changes. | Unsaved-change risk. |
| SC-060 | Multiple slide identity safety | Edit slide A, switch to slide B before autosave completes, edit slide B, reload. | Slide A and slide B retain their own edits. No content crosses between slides. | Data isolation. |

## Widget AI Workflow Test Cases (NEW - 2026-05-28)

| ID | Feature | Steps | Expected Result | Usability Focus |
| --- | --- | --- | --- | --- |
| SC-061 | AI Generate streaming feedback | Open Generate with AI, submit prompt "Create a live poll widget", watch streaming. | Typing dots appear with "Waiting for the model to start…", character counter updates live, faded mono tail shows last ~280 chars of stream. | Forward progress visibility during 30-70s wait. |
| SC-062 | AI Generate image attachment | With image-capable model configured, verify `+` button appears in composer. | Image attachment button visible; can attach data URL image; included in LLM request. | Capability discoverability. |
| SC-063 | AI Generate preview card | After generation completes, inspect preview card. | Compact "DRAFT · KIND" kicker, "</> code" link, "+ insert" button visible. Warnings (if any) shown as amber notice above Apply. | Draft presentation clarity. |
| SC-064 | AI Adjust behavior swap (Quiet→Loud) | Start with Quiet widget, open AI Adjust, ask "Make this a loud widget with tally aggregation", apply. | Behavior becomes Loud, new revision created, live contribution path works. | Behavior change transparency. |
| SC-065 | AI Adjust behavior swap (Loud→Quiet) | Start with Loud widget, open AI Adjust, ask "Make this private, remove shared state", apply. | Behavior becomes Quiet, shared contribution code unused, new revision created. | Bidirectional behavior change. |
| SC-066 | AI Adjust thread history | Open AI Adjust, send change request, apply or leave draft visible, close sidebar, reopen AI Adjust for same widget. | Previous user messages, AI plan/reflection/draft/apply history still visible. | Conversation continuity. |
| SC-067 | AI Adjust workflow progress | Ask for complex adjustment "Refactor to support configurable labels, explain plan first". | `plan`, `step`, or `reflection` responses render as workflow progress; no "AI response was not a valid widget workflow" error. | Agent transparency. |
| SC-068 | Widget revision creation | Apply AI Adjust draft, then check widget in library. | New `widget_revision` created; current_revision_id updated; previous revision preserved. | Revision tracking visibility. |
| SC-068A | AI Adjust apply UI recovery | Apply an AI Adjust draft that changes widget props/source, then immediately click Props and the editor back button. | Apply button returns from `applying`, Props panel renders without refresh, Back changes both URL and DOM to Workspace, and console has no `DataCloneError` or Vue unmount/update errors. | Scheduler/repaint regression coverage. |
| SC-069 | Manual Code tab Save | Open Code tab, edit HTML/JS/CSS, click Save (bottom-right). | Changes persist via PATCH; canvas repaints via `widgetRev` bump; no autosave occurs. | Explicit save clarity. |
| SC-070 | Props tab form rendering | Open Props tab for widget with `props_schema` containing strings, enums, arrays, `enum.from`. | Form renders primitives, array editor with reorder, nested objects, dynamic enum picker against sibling array. | Schema-driven form quality. |
| SC-071 | Props PATCH validation | Edit props to invalid value (type mismatch, out-of-enum, length violation), save. | Server returns 422 with dot-path-prefixed message; UI shows validation error. | Validation feedback clarity. |
| SC-072 | Placement revision stability | Attach widget showing "Version A", adjust widget to "Version B", inspect existing placement. | Placement can still render captured original revision where revision snapshots apply; later edits don't rewrite history. | Historical revision integrity. |
| SC-073 | Cross-deck widget copy | Drag widget from "Other decks" section to slide, drop. | Widget copied into current deck with `derived_from_id` lineage; independent from source; adjusting copy doesn't mutate original. | Cross-deck copy safety. |
| SC-074 | Widget thumbnail preview | Inspect widget card in sidebar library. | Sandboxed iframe preview with host theme tokens injected; matches canvas rendering; "OTHER DECK" pill for cross-deck widgets. | Preview fidelity. |
| SC-075 | Widget drag-to-insert | Drag widget card from sidebar, drop on slide canvas. | Widget inserted at drop position; `widgetRev` bumps; canvas repaints with cached widget body. | Drag-to-insert ergonomics. |
| SC-076 | AI clarification questions | Generate widget without specifying Quiet/Loud, ask "Create an audience mood widget". | If AI uncertain, clarification question rendered as option chips above chat input; choosing one continues workflow. | Human-in-the-loop behavior choice. |
| SC-077 | Recent prompts empty state | Open Generate with AI with no recent prompts, then with 5+ prior prompts. | Empty state shows "What should we *build*?" headline; with history, up to 5 recent prompts shown (deduped, capped); click to prefill. | Prompt history utility. |
| SC-078 | Widget library delete cascade | Delete widget with placements (no force), then with `force=true`. | Without force: 409 with `usage_count`; with force: strips placeholders, deletes placements, nulls historical `session_slide.widget_id` / `interaction_log.widget_id`. | Cascade delete clarity. |
| SC-079 | Canvas `widgetRev` repaint | Trigger widget preload, AI Apply, Code Save, attach, detach, or library delete. | Canvas `widgetRev` counter bumps; `SlideCanvas` repaints with cached widget body; no stale placeholder. | Repaint trigger reliability. |
| SC-080 | Example props preview | Generate props-driven widget "Create a quiz with question text and three choices as props". | Preview/thumbnail/new placement uses realistic sample values from `example_props`; Props tab starts from useful defaults. | Example-driven preview. |

---

## Usability Review Checklist

Use this checklist while executing the cases:

- **Discoverability:** Can a new user find rendered/Markdown switching, widget insertion, and add-slide controls without hidden right-click knowledge? Can they discover AI Generate and Adjust through sidebar tabs?
- **Consistency:** Does the same Markdown content behave the same whether entered in rendered mode or Markdown mode? Do widget previews match canvas rendering?
- **Feedback:** Does the editor show when changes are saved, pending, or failed? Does AI streaming show forward progress during long waits?
- **Reversibility:** Are destructive actions confirmed and cancelable? Can widget revisions be rolled back?
- **Focus management:** Does focus stay where the user expects after formatting, switching modes, inserting widgets, or closing menus?
- **Layout stability:** Do ribbons, toolbars, side panels, and tabs avoid shifting or covering content? Does collapsed sidebar pill not intercept canvas clicks?
- **Accessibility:** Are controls reachable by keyboard, named clearly, and visibly focused? Are AI workflow states announced?
- **Error prevention:** Does the UI prevent accidental content replacement, duplicate content, and orphaned slides outside sections? Does it prevent invalid props values?
- **Revision safety:** Do widget adjustments create new revisions instead of overwriting? Do placements render historical revisions correctly?
- **AI transparency:** Are AI workflow states (question/plan/step/reflection/draft) clearly rendered? Is behavior choice (Quiet/Loud) made explicit through clarification?

## Known Risks To Track During Testing

- Underline formatting may not serialize to Markdown and may disappear after repaint or reload.
- H3 is supported through Markdown and direct typing, but the toolbar exposes only H1 and H2.
- Horizontal rules are supported through Markdown, but there is no visible toolbar action for them.
- Link creation uses a browser prompt, which may be less discoverable and less polished than inline editor controls.
- Copy, cut, and paste rely on browser editing commands, which can vary by browser permissions and focus state.
- Rapid reload before autosave debounce completes may expose unsaved-change risk if there is no unload guard.
