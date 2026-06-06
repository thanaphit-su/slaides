import { h, type Component, type VNode } from "vue";
import type { SlideWidgetEmbed, Widget } from "@/api/types";

export interface RenderOptions {
  slim?: boolean;
  showWidgetChrome?: boolean;
  /** Live widget placements for the current slide (from the deck GET). */
  widgets?: SlideWidgetEmbed[];
  /** Render the captured placement revision instead of the mutable current widget.
   * Historical/live surfaces keep this on; authoring surfaces turn it off so
   * AI Adjust applies are visible immediately. */
  usePlacementRevision?: boolean;
  /** Resolve a widget id → full widget record (needs html/js/css). */
  getWidget?: (id: string) => Widget | null;
  /** Component to mount inline for each widget placement. */
  WidgetFrameComp?: Component;
  /** Click handler for the Adjust button on the widget chrome. */
  onAdjust?: (placement: SlideWidgetEmbed) => void;
  /** Click handler for the Remove button on the widget chrome. */
  onRemove?: (placement: SlideWidgetEmbed) => void;
  /** Fired when a mounted widget emits a `slaides.emit()` event via the bridge. */
  onWidgetEvent?: (
    placement: SlideWidgetEmbed,
    event: { type: string; payload: Record<string, unknown> },
  ) => void;
  /** Fired when text is selected inside a mounted widget iframe. */
  onWidgetSelection?: (
    placement: SlideWidgetEmbed,
    event: { x: number; y: number; text: string; contextMenu?: boolean },
  ) => void;
  /** Role passed into the iframe boot (instructor / audience / preview). */
  widgetRole?: "instructor" | "audience" | "preview";
  /** Audience identity (display_name + anon flag) baked into the iframe
   * `window.slaides.participant`. Omitted for presenter / preview. `ref` is the
   * stable per-participant id used only to scope per-viewer scratch state; it is
   * not baked into the iframe boot. */
  widgetParticipant?: { display_name?: string | null; anon?: boolean; ref?: string | null };
}

export interface Block {
  type: "h1" | "h2" | "h3" | "p" | "quote" | "rule" | "widget" | "list" | "table";
  text?: string;
  id?: string;
  ordered?: boolean;
  items?: string[];
  headers?: string[];
  rows?: string[][];
}

export const INLINE_RE = /(\*\*[^*]+\*\*|\*[^*]+\*|`[^`]+`|\[[^\]]+\]\([^)]+\))/;

const ALLOWED_LINK_SCHEMES = new Set(["http", "https", "mailto"]);

/**
 * Returns a safe `href` value or `null` if the URL must be dropped.
 *
 * Strips inline control characters and whitespace before scheme detection so
 * tricks like `java\tscript:` / `java\nscript:` are normalized and caught.
 * Schemeless values (relative paths, hash anchors, root-relative) pass through;
 * anything with a scheme outside the allowlist is rejected.
 */
export function sanitizeHref(href: string | null | undefined): string | null {
  if (!href) return null;
  let cleaned = "";
  for (let k = 0; k < href.length; k++) {
    const code = href.charCodeAt(k);
    if (code <= 0x20 || code === 0x7f) continue;
    cleaned += href[k];
  }
  if (!cleaned) return null;
  const schemeMatch = cleaned.match(/^([a-z][a-z0-9+.\-]*):/i);
  if (!schemeMatch) return href.trim();
  return ALLOWED_LINK_SCHEMES.has(schemeMatch[1].toLowerCase()) ? href.trim() : null;
}

export function renderInline(text: string): (string | VNode)[] {
  const out: (string | VNode)[] = [];
  let rest = text;
  let key = 0;
  while (rest.length) {
    const m = rest.match(INLINE_RE);
    if (!m) {
      out.push(rest);
      break;
    }
    if (m.index! > 0) out.push(rest.slice(0, m.index));
    const tok = m[0];
    if (tok.startsWith("**")) {
      out.push(h("strong", { key: key++ }, tok.slice(2, -2)));
    } else if (tok.startsWith("*")) {
      out.push(h("em", { key: key++ }, tok.slice(1, -1)));
    } else if (tok.startsWith("`")) {
      out.push(
        h(
          "code",
          {
            key: key++,
            style: {
              fontFamily: "var(--mono)",
              fontSize: ".92em",
              background: "var(--paper-2)",
              padding: "1px 6px",
              borderRadius: "4px",
            },
          },
          tok.slice(1, -1),
        ),
      );
    } else if (tok.startsWith("[")) {
      const lm = tok.match(/\[([^\]]+)\]\(([^)]+)\)/);
      if (lm) {
        const safeHref = sanitizeHref(lm[2]);
        if (safeHref === null) {
          out.push(lm[1]);
          rest = rest.slice(m.index! + tok.length);
          continue;
        }
        out.push(
          h(
            "a",
            {
              key: key++,
              href: safeHref,
              style: {
                color: "var(--accent)",
                textDecoration: "underline",
                textDecorationThickness: "1px",
                textUnderlineOffset: "3px",
              },
            },
            lm[1],
          ),
        );
      }
    }
    rest = rest.slice(m.index! + tok.length);
  }
  return out;
}

export function parseBlocks(md: string): Block[] {
  const lines = md.split(/\n/);
  const blocks: Block[] = [];
  let para: string[] = [];
  let listItems: string[] = [];
  let listOrdered = false;

  const flushPara = () => {
    if (para.length) {
      blocks.push({ type: "p", text: para.join(" ") });
      para = [];
    }
  };
  const flushList = () => {
    if (listItems.length) {
      blocks.push({ type: "list", ordered: listOrdered, items: [...listItems] });
      listItems = [];
    }
  };
  const flushBlocks = () => {
    flushPara();
    flushList();
  };

  for (let lineIndex = 0; lineIndex < lines.length; lineIndex++) {
    const line = lines[lineIndex];
    if (!line.trim()) {
      flushBlocks();
      continue;
    }
    if (line.startsWith("# ")) {
      flushBlocks();
      blocks.push({ type: "h1", text: line.slice(2) });
      continue;
    }
    if (line.startsWith("## ")) {
      flushBlocks();
      blocks.push({ type: "h2", text: line.slice(3) });
      continue;
    }
    if (line.startsWith("### ")) {
      flushBlocks();
      blocks.push({ type: "h3", text: line.slice(4) });
      continue;
    }
    if (line.startsWith("> ")) {
      flushBlocks();
      blocks.push({ type: "quote", text: line.slice(2) });
      continue;
    }
    if (/^[-_]{3,}\s*$/.test(line)) {
      flushBlocks();
      blocks.push({ type: "rule" });
      continue;
    }
    const widget = line.match(/^\{\{widget:([^}]+)\}\}\s*$/);
    if (widget) {
      flushBlocks();
      blocks.push({ type: "widget", id: widget[1] });
      continue;
    }
    const maybeHeader = parseTableRow(line);
    const maybeSeparator = parseTableRow(lines[lineIndex + 1] || "");
    if (maybeHeader && maybeSeparator && isTableSeparator(maybeSeparator)) {
      flushBlocks();
      const rows: string[][] = [];
      lineIndex += 2;
      while (lineIndex < lines.length) {
        const cells = parseTableRow(lines[lineIndex]);
        if (!cells || isTableSeparator(cells)) {
          lineIndex -= 1;
          break;
        }
        rows.push(cells);
        lineIndex += 1;
      }
      blocks.push({ type: "table", headers: maybeHeader, rows });
      continue;
    }
    const ulMatch = line.match(/^[-*] (.+)/);
    if (ulMatch) {
      flushPara();
      if (listItems.length && listOrdered) flushList();
      listOrdered = false;
      listItems.push(ulMatch[1]);
      continue;
    }
    const olMatch = line.match(/^\d+\. (.+)/);
    if (olMatch) {
      flushPara();
      if (listItems.length && !listOrdered) flushList();
      listOrdered = true;
      listItems.push(olMatch[1]);
      continue;
    }
    flushList();
    para.push(line);
  }
  flushBlocks();
  return blocks;
}

function parseTableRow(line: string): string[] | null {
  const trimmed = line.trim();
  if (!trimmed.includes("|")) return null;
  const content = trimmed.replace(/^\|/, "").replace(/\|$/, "");
  const cells = content.split("|").map((cell) => cell.trim());
  return cells.length >= 2 ? cells : null;
}

function isTableSeparator(cells: string[]): boolean {
  return cells.every((cell) => /^:?-{3,}:?$/.test(cell.trim()));
}

export function renderMarkdown(md: string, opts: RenderOptions = {}): VNode[] {
  const { slim = false } = opts;
  const blocks = parseBlocks(md);
  const visibleBlocks: Block[] = blocks.length ? blocks : [{ type: "p", text: "" }];
  const widgetOnly = blocks.length === 1 && blocks[0].type === "widget";
  return visibleBlocks.map((b, i) => renderBlock(b, i, slim, opts, widgetOnly));
}

function renderTextChildren(text: string): (string | VNode)[] {
  return text ? renderInline(text) : [h("br")];
}

function renderBlock(b: Block, key: number, slim: boolean, opts: RenderOptions, widgetOnly = false): VNode {
  switch (b.type) {
    case "h1":
      return h(
        "h1",
        {
          key,
          class: slim ? "t-h2" : "t-display",
          style: { margin: slim ? "0 0 12px" : "0 0 18px" },
          "data-block": "h1",
        },
        renderTextChildren(b.text || ""),
      );
    case "h2":
      return h(
        "h2",
        {
          key,
          class: "t-h2",
          style: { margin: "24px 0 12px" },
          "data-block": "h2",
        },
        renderTextChildren(b.text || ""),
      );
    case "h3":
      return h(
        "h3",
        {
          key,
          class: "t-h3",
          style: { margin: "24px 0 10px" },
          "data-block": "h3",
        },
        renderTextChildren(b.text || ""),
      );
    case "rule":
      return h("hr", {
        key,
        style: {
          border: "none",
          borderTop: "1px solid var(--ink)",
          width: "48px",
          margin: "24px 0",
        },
        "data-block": "rule",
      });
    case "quote":
      return h(
        "blockquote",
        {
          key,
          style: {
            margin: "18px 0",
            paddingLeft: "18px",
            borderLeft: "2px solid var(--accent)",
            fontFamily: "var(--serif)",
            fontStyle: "italic",
            fontSize: slim ? "18px" : "22px",
            color: "var(--ink-soft)",
            lineHeight: "1.55",
          },
          "data-block": "quote",
        },
        renderTextChildren(b.text || ""),
      );
    case "widget":
      return renderWidgetBlock(b, key, opts, widgetOnly);
    case "list":
      return h(
        b.ordered ? "ol" : "ul",
        {
          key,
          class: slim ? "t-body-sans" : "t-body",
          style: {
            margin: "0 0 18px",
            paddingLeft: "28px",
            color: "var(--ink)",
          },
          "data-block": "list",
          "data-ordered": b.ordered ? "true" : "false",
        },
        (b.items || []).map((item, i) => h("li", { key: i }, renderTextChildren(item))),
      );
    case "table":
      return renderTableBlock(b, key, slim);
    case "p":
    default:
      return h(
        "p",
        {
          key,
          class: slim ? "t-body-sans" : "t-body",
          style: { margin: "0 0 18px", color: "var(--ink)" },
          "data-block": "p",
        },
        renderTextChildren(b.text || ""),
      );
  }
}

function renderTableBlock(b: Block, key: number, slim: boolean): VNode {
  const headers = b.headers || [];
  const rows = b.rows || [];
  const cellBase = {
    border: "1px solid var(--rule)",
    padding: slim ? "7px 9px" : "9px 12px",
    verticalAlign: "top",
    textAlign: "left",
  };
  return h(
    "table",
    {
      key,
      class: slim ? "t-body-sans" : "t-body",
      style: {
        width: "100%",
        borderCollapse: "collapse",
        margin: "0 0 22px",
        color: "var(--ink)",
        fontSize: slim ? "13px" : undefined,
      },
      "data-block": "table",
    },
    [
      h("thead", [
        h(
          "tr",
          headers.map((header, i) =>
            h(
              "th",
              {
                key: i,
                style: {
                  ...cellBase,
                  background: "var(--paper-2)",
                  fontFamily: "var(--sans)",
                  fontSize: slim ? "12px" : "13px",
                  fontWeight: 700,
                },
              },
              renderTextChildren(header),
            ),
          ),
        ),
      ]),
      h(
        "tbody",
        rows.map((row, rowIndex) =>
          h(
            "tr",
            { key: rowIndex },
            headers.map((_, cellIndex) =>
              h(
                "td",
                { key: cellIndex, style: cellBase },
                renderTextChildren(row[cellIndex] || ""),
              ),
            ),
          ),
        ),
      ),
    ],
  );
}

function renderWidgetBlock(b: Block, key: number, opts: RenderOptions, fill = false): VNode {
  const id = b.id || "";
  const placement = (opts.widgets || []).find((w) => w.placement_id === id);
  const widget = placement && opts.getWidget ? opts.getWidget(placement.widget_id) : null;
  const iconStyle = {
    width: "28px",
    height: "28px",
    padding: 0,
    display: "inline-flex",
    alignItems: "center",
    justifyContent: "center",
    background: "var(--paper)",
    pointerEvents: "auto",
    lineHeight: 0,
  };

  const iconSvg = (path: string, color = "currentColor") =>
    h(
      "svg",
      {
        width: 14,
        height: 14,
        viewBox: "0 0 20 20",
        fill: "none",
        stroke: color,
        "stroke-width": 1.5,
        "stroke-linecap": "round",
        "stroke-linejoin": "round",
        "aria-hidden": "true",
      },
      [h("path", { d: path })],
    );

  // Editor-only metadata strip. Audience and preview tiles must NEVER see
  // the internal `WIDGET · KIND · #PLACEMENT_ID` debug text — it's
  // instructor chrome for placing/adjusting widgets in the canvas. Render
  // it only in the "instructor" role.
  const labelChrome =
    opts.widgetRole === "instructor" || opts.widgetRole === undefined
      ? h(
          "div",
          {
            style: {
              position: "absolute",
              top: "-20px",
              left: "0",
              right: "0",
              display: "flex",
              justifyContent: "flex-start",
              alignItems: "center",
              pointerEvents: "none",
              zIndex: 1,
            },
          },
          [
            h(
              "span",
              {
                class: "t-mono-up",
                style: {
                  background: "transparent",
                  padding: "0",
                  border: "0",
                  borderRadius: "0",
                  pointerEvents: "auto",
                  fontSize: "11px",
                  letterSpacing: ".1em",
                  textTransform: "uppercase",
                  color: "var(--ink-soft)",
                },
              },
              placement ? `WIDGET · ${placement.kind} · #${id}` : `WIDGET · #${id}`,
            ),
          ],
        )
      : null;

  const actionChrome =
    placement && (opts.onAdjust || opts.onRemove)
      ? h(
          "div",
          {
            style: {
              position: "absolute",
              right: "0",
              bottom: "0",
              display: "inline-flex",
              alignItems: "center",
              gap: "6px",
              pointerEvents: "auto",
              zIndex: 2,
              opacity: 0,
              transition: "opacity .12s ease",
            },
            class: "widget-action-chrome",
          },
          [
            opts.onAdjust
              ? h(
                  "button",
                  {
                    class: "btn btn-sm",
                    type: "button",
                    title: "Adjust widget",
                    "aria-label": "Adjust widget",
                    style: iconStyle,
                    onClick: (e: Event) => {
                      e.preventDefault();
                      e.stopPropagation();
                      opts.onAdjust!(placement);
                    },
                    onMousedown: (e: Event) => e.preventDefault(),
                  },
                  [iconSvg("M4 16l1-3 8-8 3 3-8 8-3 1z")],
                )
              : null,
            opts.onRemove
              ? h(
                  "button",
                  {
                    class: "btn btn-sm",
                    type: "button",
                    title: "Remove widget",
                    "aria-label": "Remove widget",
                    style: {
                      ...iconStyle,
                      borderColor: "var(--err)",
                      color: "var(--err)",
                    },
                    onClick: (e: Event) => {
                      e.preventDefault();
                      e.stopPropagation();
                      opts.onRemove!(placement);
                    },
                    onMousedown: (e: Event) => e.preventDefault(),
                  },
                  [iconSvg("M5 6h10M8 6V4h4v2M6.5 6l.7 10.2c0 .5.4.8.8.8h4c.4 0 .8-.3.8-.8L13.5 6")],
                )
              : null,
          ],
        )
      : null;

  const chrome = h("div", [labelChrome, actionChrome]);

  let body: VNode;
  const revisionWidget: Widget | null = placement?.revision
    ? {
        id: placement.widget_id,
        deck_id: "",
        derived_from_id: null,
        name: placement.name,
        kind: placement.kind,
        description: null,
        html: placement.revision.html || "",
        js: placement.revision.js,
        css: placement.revision.css,
        props_schema: placement.revision.props_schema || {},
        tags: [],
        version: String(placement.revision.version_number || 1),
        behavior: placement.revision.behavior || { kind: "quiet" },
        current_revision_id: placement.revision.id,
        example_props: placement.revision.example_props || {},
        ai_spec: placement.revision.ai_spec || {},
      }
    : null;
  const renderedWidget = opts.usePlacementRevision !== false && placement?.revision
    ? {
        ...(widget || revisionWidget!),
        html: placement.revision.html || "",
        js: placement.revision.js,
        css: placement.revision.css,
        props_schema: placement.revision.props_schema || {},
        behavior: placement.revision.behavior || { kind: "quiet" },
        current_revision_id: placement.revision.id,
        example_props: placement.revision.example_props || {},
        ai_spec: placement.revision.ai_spec || {},
      }
    : widget;
  if (renderedWidget && placement && opts.WidgetFrameComp) {
    body = h(opts.WidgetFrameComp, {
      widget: renderedWidget,
      placementId: id,
      bootProps: placement.props || {},
      role: opts.widgetRole || "instructor",
      fill,
      minHeight: fill ? 560 : 80,
      participant: opts.widgetParticipant,
      onInteraction: opts.onWidgetEvent
        ? (event: { type: string; payload: Record<string, unknown> }) =>
            opts.onWidgetEvent!(placement, event)
        : undefined,
      onSelection: opts.onWidgetSelection
        ? (event: { x: number; y: number; text: string; contextMenu?: boolean }) =>
            opts.onWidgetSelection!(placement, event)
        : undefined,
    });
  } else {
    body = h(
      "div",
      {
        style: {
          padding: "28px 24px",
          border: "1px dashed var(--rule-strong)",
          borderRadius: "var(--r-lg)",
          background: "var(--paper-2)",
          fontFamily: "var(--mono)",
          fontSize: "12px",
          color: "var(--ink-soft)",
          letterSpacing: "0.04em",
          textAlign: "center",
        },
      },
      placement ? "Loading widget…" : `WIDGET · #${id}`,
    );
  }

  return h(
    "div",
    {
      // Key by widget identity (placement_id + widget_id) so Vue mounts a
      // fresh WidgetFrame whenever the slide swaps in a different widget.
      // Previously this used the block-position-index, which stayed stable
      // across slides and caused Vue to reuse the iframe with new props —
      // the iframe DOM persisted and showed the *previous* slide's widget
      // (often in mid-interaction state) until reset. See bug report
      // 2026-05-25: "Widget content bleeds across slides after interaction".
      key: renderedWidget ? `widget-${id}-${renderedWidget.id}` : `widget-${id}-loading`,
      contenteditable: "false",
      "data-block": "widget",
      "data-widget-id": id,
      style: {
        margin: "32px 0",
        position: "relative",
        userSelect: "none",
      },
    },
    [chrome, body],
  );
}

/* ===================== Serialise back to markdown =====================
   The block model (`Block[]`, parsed by `parseBlocks`) is the source of truth
   for the editor. `blocksToMarkdown` maps it back to markdown deterministically
   — block *structure* comes from the model, never from reading the DOM. Only
   inline content round-trips through the DOM, via `serialiseInline` below
   (bounded: strong/em/code/a/br), so an editing surface can read a single
   focused block's marks back without ever serialising whole-document structure.
*/

/** Map a single block of the parsed model back to its markdown source. */
export function blockToMarkdown(b: Block): string {
  switch (b.type) {
    case "h1":
      return `# ${b.text || ""}`;
    case "h2":
      return `## ${b.text || ""}`;
    case "h3":
      return `### ${b.text || ""}`;
    case "quote":
      return `> ${b.text || ""}`;
    case "rule":
      return "---";
    case "widget":
      return `{{widget:${b.id || ""}}}`;
    case "list": {
      const ordered = !!b.ordered;
      return (b.items || [])
        .map((item, i) => `${ordered ? `${i + 1}.` : "-"} ${item}`)
        .join("\n");
    }
    case "table": {
      const headers = b.headers || [];
      const rows = b.rows || [];
      const header = `| ${headers.join(" | ")} |`;
      const separator = `| ${headers.map(() => "---").join(" | ")} |`;
      const body = rows.map((row) => `| ${row.join(" | ")} |`);
      return [header, separator, ...body].join("\n");
    }
    case "p":
    default:
      return b.text || "";
  }
}

/** Serialise the whole block model back to a markdown document. */
export function blocksToMarkdown(blocks: Block[]): string {
  return blocks
    .map(blockToMarkdown)
    .join("\n\n")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

export function serialiseInline(node: Node): string {
  if (node.nodeType === Node.TEXT_NODE) return node.textContent || "";
  if (!(node instanceof HTMLElement)) return "";
  const tag = node.tagName.toLowerCase();
  const inner = Array.from(node.childNodes).map(serialiseInline).join("");
  switch (tag) {
    case "strong":
    case "b":
      return `**${inner}**`;
    case "em":
    case "i":
      return `*${inner}*`;
    case "code":
      return `\`${inner}\``;
    case "a": {
      const safe = sanitizeHref(node.getAttribute("href"));
      if (safe === null) return inner;
      return `[${inner}](${safe})`;
    }
    case "br":
      return "\n";
    default:
      return inner;
  }
}
