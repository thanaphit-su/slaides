import { describe, expect, it } from "vitest";
import { validateDraftJs } from "../src/widgets/draft-js";

describe("validateDraftJs", () => {
  it("returns null for empty / undefined / null input (legitimate Quiet widget)", () => {
    expect(validateDraftJs("")).toBeNull();
    expect(validateDraftJs("   ")).toBeNull();
    expect(validateDraftJs(undefined)).toBeNull();
    expect(validateDraftJs(null)).toBeNull();
  });

  it("returns null for a valid IIFE body", () => {
    const js = `(function () {
      var x = 1;
      window.slaides && window.slaides.on('state', function () {});
    })();`;
    expect(validateDraftJs(js)).toBeNull();
  });

  it("flags the user's actual failure — literal newline inside a single-quoted string", () => {
    // Verbatim shape from the broken Kahoot draft: `panel.innerHTML = '\n…\n  ';`.
    // String.raw keeps the literal newline + lone quote characters so the
    // file itself stores the broken pattern.
    const js = String.raw`(function () {
      var panel = document.createElement('div');
      panel.innerHTML = '
        <div class="q-detail">
          <h3>q</h3>
        </div>
      ';
    })();`;
    const err = validateDraftJs(js);
    expect(err).not.toBeNull();
    expect(err).toMatch(/^AI JS has a syntax error/);
  });

  it("flags an unmatched brace", () => {
    const err = validateDraftJs("({");
    expect(err).not.toBeNull();
    expect(err).toMatch(/^AI JS has a syntax error/);
  });

  it("flags an unterminated string", () => {
    const err = validateDraftJs("var x = 'unterminated;");
    expect(err).not.toBeNull();
    expect(err).toMatch(/^AI JS has a syntax error/);
  });

  it("does not gate on style — `var let = 1;` is parseable in non-strict scripts", () => {
    // `let` as an identifier is legal in non-strict code; only style-bad.
    // We refuse to parse-error on it because it's not a SyntaxError under
    // `new Function`, which is what the iframe also uses.
    expect(validateDraftJs("var let = 1;")).toBeNull();
  });

  it("allows top-level `return` because new Function() builds a function context", () => {
    // Top-level return is a SyntaxError in a module but legal inside a
    // Function constructor. The iframe's <script> block is closer to the
    // latter — it's a fresh script, not a module — so allow it.
    expect(validateDraftJs("return 1;")).toBeNull();
  });
});
