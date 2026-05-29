// Bridge between the markdown source of truth and TipTap's ProseMirror JSON.
//
// The chain is:  markdown  ⇄  Block[]  ⇄  TipTap JSON doc
//
// We deliberately reuse the existing, tested `parseBlocks` / `blocksToMarkdown`
// (markdown ⇄ Block[]) rather than pull in a second markdown parser like
// markdown-it via tiptap-markdown. That keeps the on-the-wire markdown — and
// the `{{widget:id}}` placeholder the API reconciles against — byte-identical
// to what `markdown.test.ts` already verifies. The only new surface is the
// small Block[] ⇄ JSON step below.

import {
  INLINE_RE,
  blocksToMarkdown,
  parseBlocks,
  sanitizeHref,
  type Block,
} from "./render";

export interface JSONMark {
  type: "bold" | "italic" | "code" | "link";
  attrs?: Record<string, unknown>;
}

export interface JSONNode {
  type: string;
  attrs?: Record<string, unknown>;
  content?: JSONNode[];
  text?: string;
  marks?: JSONMark[];
}

/* ----------------------------- inline ⇄ marks ---------------------------- */

/** Parse one block's inline markdown into TipTap text nodes with marks.
 * Mirrors `renderInline` but emits ProseMirror JSON instead of VNodes. */
export function inlineToNodes(text: string): JSONNode[] {
  const out: JSONNode[] = [];
  let rest = text;
  const push = (t: string, marks?: JSONMark[]) => {
    if (!t) return;
    out.push(marks && marks.length ? { type: "text", text: t, marks } : { type: "text", text: t });
  };
  while (rest.length) {
    const m = rest.match(INLINE_RE);
    if (!m) {
      push(rest);
      break;
    }
    if (m.index! > 0) push(rest.slice(0, m.index));
    const tok = m[0];
    if (tok.startsWith("**")) {
      push(tok.slice(2, -2), [{ type: "bold" }]);
    } else if (tok.startsWith("*")) {
      push(tok.slice(1, -1), [{ type: "italic" }]);
    } else if (tok.startsWith("`")) {
      push(tok.slice(1, -1), [{ type: "code" }]);
    } else if (tok.startsWith("[")) {
      const lm = tok.match(/\[([^\]]+)\]\(([^)]+)\)/);
      if (lm) {
        const safe = sanitizeHref(lm[2]);
        if (safe === null) push(lm[1]);
        else push(lm[1], [{ type: "link", attrs: { href: safe } }]);
      }
    }
    rest = rest.slice(m.index! + tok.length);
  }
  return out;
}

/** Serialise TipTap inline text nodes back to inline markdown. Inverse of
 * `inlineToNodes`; the resulting string is what `Block.text` holds. */
export function nodesToInline(content: JSONNode[] | undefined): string {
  if (!content) return "";
  let out = "";
  for (const node of content) {
    if (node.type === "hardBreak") {
      out += "\n";
      continue;
    }
    if (node.type !== "text" || node.text == null) continue;
    let text = node.text;
    const marks = node.marks || [];
    const has = (t: string) => marks.some((mk) => mk.type === t);
    if (has("code")) text = `\`${text}\``;
    if (has("bold")) text = `**${text}**`;
    if (has("italic")) text = `*${text}*`;
    const link = marks.find((mk) => mk.type === "link");
    if (link) {
      const href = sanitizeHref((link.attrs?.href as string) ?? null);
      if (href !== null) text = `[${text}](${href})`;
    }
    out += text;
  }
  return out;
}

/* ------------------------------ Block ⇄ JSON ----------------------------- */

function paragraph(text: string): JSONNode {
  const content = inlineToNodes(text);
  return content.length ? { type: "paragraph", content } : { type: "paragraph" };
}

function blockToNode(b: Block): JSONNode {
  switch (b.type) {
    case "h1":
    case "h2":
    case "h3": {
      const level = b.type === "h1" ? 1 : b.type === "h2" ? 2 : 3;
      const content = inlineToNodes(b.text || "");
      return content.length
        ? { type: "heading", attrs: { level }, content }
        : { type: "heading", attrs: { level } };
    }
    case "quote":
      return { type: "blockquote", content: [paragraph(b.text || "")] };
    case "rule":
      return { type: "horizontalRule" };
    case "widget":
      return { type: "widget", attrs: { placementId: b.id || "" } };
    case "list": {
      const listType = b.ordered ? "orderedList" : "bulletList";
      const items = (b.items || []).map((item) => ({
        type: "listItem",
        content: [paragraph(item)],
      }));
      return { type: listType, content: items.length ? items : [{ type: "listItem", content: [paragraph("")] }] };
    }
    case "table": {
      const headers = b.headers || [];
      const rows = b.rows || [];
      const headerRow: JSONNode = {
        type: "tableRow",
        content: headers.map((h) => ({ type: "tableHeader", content: [paragraph(h)] })),
      };
      const bodyRows: JSONNode[] = rows.map((row) => ({
        type: "tableRow",
        content: headers.map((_, c) => ({ type: "tableCell", content: [paragraph(row[c] || "")] })),
      }));
      return { type: "table", content: [headerRow, ...bodyRows] };
    }
    case "p":
    default:
      return paragraph(b.text || "");
  }
}

function nodeToBlock(node: JSONNode): Block | null {
  switch (node.type) {
    case "heading": {
      const level = Number(node.attrs?.level) || 1;
      const type = level === 1 ? "h1" : level === 2 ? "h2" : "h3";
      return { type, text: nodesToInline(node.content) };
    }
    case "blockquote": {
      // Flatten the inner paragraph(s) into a single quote line.
      const text = (node.content || [])
        .map((p) => nodesToInline(p.content))
        .filter(Boolean)
        .join(" ");
      return { type: "quote", text };
    }
    case "horizontalRule":
      return { type: "rule" };
    case "widget":
      return { type: "widget", id: String(node.attrs?.placementId || "") };
    case "bulletList":
    case "orderedList": {
      const items = (node.content || []).map((li) =>
        (li.content || [])
          .map((p) => nodesToInline(p.content))
          .filter(Boolean)
          .join(" "),
      );
      return { type: "list", ordered: node.type === "orderedList", items };
    }
    case "table": {
      const rows = node.content || [];
      const headerRow = rows[0];
      const headers = (headerRow?.content || []).map((c) => nodesToInline(c.content?.[0]?.content));
      const bodyRows = rows.slice(1).map((r) =>
        (r.content || []).map((c) => nodesToInline(c.content?.[0]?.content)),
      );
      return { type: "table", headers, rows: bodyRows };
    }
    case "paragraph":
      return { type: "p", text: nodesToInline(node.content) };
    default:
      return null;
  }
}

/* ------------------------------- top level ------------------------------- */

/** markdown → TipTap doc JSON (via the Block model). */
export function markdownToDoc(md: string): JSONNode {
  const blocks = parseBlocks(md);
  const content = (blocks.length ? blocks : [{ type: "p", text: "" } as Block]).map(blockToNode);
  return { type: "doc", content };
}

/** TipTap doc JSON → Block model. */
export function docToBlocks(doc: JSONNode): Block[] {
  const blocks: Block[] = [];
  for (const node of doc.content || []) {
    const b = nodeToBlock(node);
    if (b) blocks.push(b);
  }
  return blocks;
}

/** TipTap doc JSON → markdown (round-trips through the Block model so the
 * `{{widget:id}}` placeholder and all block syntax stay identical to the
 * existing markdown contract). */
export function docToMarkdown(doc: JSONNode): string {
  return blocksToMarkdown(docToBlocks(doc));
}
