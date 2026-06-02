import { describe, expect, it } from "vitest";
import { LOUD_AGGREGATORS, sanitiseBehavior } from "../src/widgets/behavior";

describe("sanitiseBehavior", () => {
  it("returns null for non-object inputs", () => {
    expect(sanitiseBehavior(null)).toBeNull();
    expect(sanitiseBehavior(undefined)).toBeNull();
    expect(sanitiseBehavior("loud")).toBeNull();
    expect(sanitiseBehavior(42)).toBeNull();
    expect(sanitiseBehavior(["loud"])).toBeNull();
  });

  it("returns null for unknown kind", () => {
    expect(sanitiseBehavior({ kind: "weird" })).toBeNull();
    expect(sanitiseBehavior({ kind: "" })).toBeNull();
    expect(sanitiseBehavior({})).toBeNull();
  });

  it("preserves quiet behavior", () => {
    expect(sanitiseBehavior({ kind: "quiet" })).toEqual({ kind: "quiet" });
  });

  it("strips extraneous fields from quiet behavior", () => {
    // Quiet doesn't carry an aggregator; drop noise.
    expect(sanitiseBehavior({ kind: "quiet", aggregator: "tally" })).toEqual({ kind: "quiet" });
  });

  it("accepts collect behavior and defaults its contribution_schema", () => {
    // collect carries no aggregator — the server fixes it to "collect".
    expect(sanitiseBehavior({ kind: "collect" })).toEqual({
      kind: "collect",
      contribution_schema: { type: "string" },
    });
  });

  it("preserves a collect contribution_schema when it is an object", () => {
    expect(
      sanitiseBehavior({ kind: "collect", contribution_schema: { type: "object" } }),
    ).toEqual({
      kind: "collect",
      contribution_schema: { type: "object" },
    });
  });

  it("adds a default contribution_schema for loud behavior when missing", () => {
    expect(sanitiseBehavior({ kind: "loud", aggregator: "tally" })).toEqual({
      kind: "loud",
      aggregator: "tally",
      contribution_schema: { type: "string" },
    });
  });

  it("preserves contribution_schema when it is an object", () => {
    const result = sanitiseBehavior({
      kind: "loud",
      aggregator: "tally",
      contribution_schema: { type: "string" },
    });
    expect(result).toEqual({
      kind: "loud",
      aggregator: "tally",
      contribution_schema: { type: "string" },
    });
  });

  it("replaces non-object contribution_schema with the default schema", () => {
    const result = sanitiseBehavior({
      kind: "loud",
      aggregator: "tally",
      contribution_schema: "string-not-object",
    });
    expect(result).toEqual({
      kind: "loud",
      aggregator: "tally",
      contribution_schema: { type: "string" },
    });
  });

  it("returns null for loud with missing aggregator (would silently drop votes)", () => {
    expect(sanitiseBehavior({ kind: "loud" })).toBeNull();
  });

  it("returns null for loud with unknown aggregator", () => {
    expect(sanitiseBehavior({ kind: "loud", aggregator: "made-up" })).toBeNull();
  });

  it("accepts every server-side aggregator", () => {
    for (const aggregator of LOUD_AGGREGATORS) {
      expect(sanitiseBehavior({ kind: "loud", aggregator })).toEqual({
        kind: "loud",
        aggregator,
        contribution_schema: { type: "string" },
      });
    }
  });

  it("keeps the published LOUD_AGGREGATORS set in lockstep with the server", () => {
    // If you add an aggregator to apps/api/src/slaides/sessions/aggregators.py
    // remember to extend behavior.ts too — this assertion is a tripwire.
    expect([...LOUD_AGGREGATORS].sort()).toEqual([
      "append",
      "keyed_tally",
      "latest_per_participant",
      "set_union",
      "tally",
    ]);
  });
});
