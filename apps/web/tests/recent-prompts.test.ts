import { afterEach, beforeEach, describe, expect, it } from "vitest";
import {
  RECENT_PROMPTS_KEY,
  RECENT_PROMPTS_MAX,
  loadRecentPrompts,
  pushRecentPrompt,
} from "../src/widgets/recent-prompts";

describe("recent-prompts", () => {
  beforeEach(() => {
    localStorage.clear();
  });
  afterEach(() => {
    localStorage.clear();
  });

  it("returns empty when nothing is stored", () => {
    expect(loadRecentPrompts()).toEqual([]);
  });

  it("returns empty when stored value is not an array", () => {
    localStorage.setItem(RECENT_PROMPTS_KEY, JSON.stringify({ not: "array" }));
    expect(loadRecentPrompts()).toEqual([]);
  });

  it("returns empty when stored value is malformed JSON", () => {
    localStorage.setItem(RECENT_PROMPTS_KEY, "{not json");
    expect(loadRecentPrompts()).toEqual([]);
  });

  it("pushes a prompt and reads it back", () => {
    pushRecentPrompt("a 4-option poll");
    expect(loadRecentPrompts()).toEqual(["a 4-option poll"]);
  });

  it("ignores blank input", () => {
    pushRecentPrompt("   ");
    pushRecentPrompt("");
    expect(loadRecentPrompts()).toEqual([]);
  });

  it("trims and dedupes — moves existing to the front", () => {
    pushRecentPrompt("one");
    pushRecentPrompt("two");
    pushRecentPrompt("one");
    expect(loadRecentPrompts()).toEqual(["one", "two"]);
  });

  it("caps at MAX entries, most recent first", () => {
    pushRecentPrompt("a");
    pushRecentPrompt("b");
    pushRecentPrompt("c");
    pushRecentPrompt("d");
    pushRecentPrompt("e");
    pushRecentPrompt("f");
    const result = loadRecentPrompts();
    expect(result).toHaveLength(RECENT_PROMPTS_MAX);
    expect(result[0]).toBe("f");
    expect(result).not.toContain("a");
  });

  it("filters out non-string entries from stored array", () => {
    localStorage.setItem(
      RECENT_PROMPTS_KEY,
      JSON.stringify(["valid", 42, null, "also valid", { obj: true }]),
    );
    expect(loadRecentPrompts()).toEqual(["valid", "also valid"]);
  });

  it("trims whitespace from input before storing", () => {
    pushRecentPrompt("  hello  ");
    expect(loadRecentPrompts()).toEqual(["hello"]);
  });
});
