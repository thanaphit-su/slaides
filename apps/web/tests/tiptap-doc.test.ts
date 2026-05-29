import { describe, expect, it } from "vitest";
import { docToMarkdown, markdownToDoc, inlineToNodes, nodesToInline } from "../src/markdown/tiptap-doc";

// The bridge must preserve the markdown contract: markdown → doc → markdown is
// the identity for everything the editor supports (the API reconciles widgets
// against the `{{widget:id}}` placeholder, so that especially must survive).
function roundTrip(md: string): string {
  return docToMarkdown(markdownToDoc(md));
}

describe("tiptap-doc bridge — markdown round-trip", () => {
  it("preserves headings", () => {
    expect(roundTrip("# One")).toBe("# One");
    expect(roundTrip("## Two")).toBe("## Two");
    expect(roundTrip("### Three")).toBe("### Three");
  });

  it("preserves paragraphs and inline marks", () => {
    expect(roundTrip("Plain text")).toBe("Plain text");
    expect(roundTrip("**Bold** and *italic* and `code`.")).toBe("**Bold** and *italic* and `code`.");
  });

  it("preserves safe links and drops the mark structure cleanly", () => {
    expect(roundTrip("See [docs](https://x).")).toBe("See [docs](https://x).");
  });

  it("preserves blockquote", () => {
    expect(roundTrip("> A wise word")).toBe("> A wise word");
  });

  it("preserves horizontal rule", () => {
    expect(roundTrip("---")).toBe("---");
  });

  it("preserves unordered and ordered lists", () => {
    expect(roundTrip("- one\n- two")).toBe("- one\n- two");
    expect(roundTrip("1. one\n2. two")).toBe("1. one\n2. two");
  });

  it("preserves pipe tables", () => {
    const md = ["| Year | Milestone |", "| --- | --- |", "| 1950 | Turing |", "| 2022 | GPT |"].join("\n");
    expect(roundTrip(md)).toBe(md);
  });

  it("preserves the widget placeholder verbatim", () => {
    expect(roundTrip("Intro.\n\n{{widget:fn-plotter}}")).toContain("{{widget:fn-plotter}}");
    // And as a standalone block.
    expect(roundTrip("{{widget:my-pid}}")).toBe("{{widget:my-pid}}");
  });

  it("preserves a mixed document", () => {
    const md = ["# Title", "", "Lead paragraph with **bold**.", "", "- a", "- b", "", "{{widget:pid}}"].join("\n");
    expect(roundTrip(md)).toBe(md);
  });

  it("produces a doc node with a widget node carrying placementId", () => {
    const doc = markdownToDoc("{{widget:abc}}");
    const widget = (doc.content || []).find((n) => n.type === "widget");
    expect(widget?.attrs?.placementId).toBe("abc");
  });
});

describe("tiptap-doc bridge — inline conversion", () => {
  it("round-trips inline marks", () => {
    expect(nodesToInline(inlineToNodes("a **b** c"))).toBe("a **b** c");
    expect(nodesToInline(inlineToNodes("`x` and [y](https://z)"))).toBe("`x` and [y](https://z)");
  });

  it("drops an unsafe link to plain text", () => {
    const nodes = inlineToNodes("[click](javascript:alert1)");
    // Unsafe href → no link mark, just the text.
    expect(nodes.every((n) => !(n.marks || []).some((m) => m.type === "link"))).toBe(true);
    expect(nodesToInline(nodes)).toBe("click");
  });

  it("converts a hard break to a newline", () => {
    expect(nodesToInline([{ type: "text", text: "a" }, { type: "hardBreak" }, { type: "text", text: "b" }])).toBe("a\nb");
  });
});
