/**
 * Widgets v2 Step 4 — defensive parser for the `behavior` field returned
 * by the LLM. Kept in its own module so it can be unit-tested directly
 * (and so the allowed-aggregator set stays in lockstep with the server's
 * canonical list in apps/api/src/slaides/sessions/aggregators.py).
 *
 * Returns a normalised behavior dict, or `null` when the input is
 * unsafe / unrecognised so the caller can decide whether to fall back
 * (rather than silently downgrading a Loud widget to Quiet).
 */

export type BehaviorKind = "quiet" | "loud";
export type LoudAggregator =
  | "tally"
  | "latest_per_participant"
  | "append"
  | "set_union"
  | "keyed_tally";

export const LOUD_AGGREGATORS: ReadonlySet<LoudAggregator> = new Set([
  "tally",
  "latest_per_participant",
  "append",
  "set_union",
  "keyed_tally",
]);

export interface SanitisedBehavior {
  kind: BehaviorKind;
  aggregator?: LoudAggregator;
  contribution_schema?: Record<string, unknown>;
  [extra: string]: unknown;
}

function isPlainObject(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

export function sanitiseBehavior(raw: unknown): SanitisedBehavior | null {
  if (!isPlainObject(raw)) return null;
  const kind = raw.kind;
  if (kind === "quiet") return { kind: "quiet" };
  if (kind !== "loud") return null;

  const result: SanitisedBehavior = { kind: "loud" };

  const aggregator = raw.aggregator;
  if (typeof aggregator === "string" && LOUD_AGGREGATORS.has(aggregator as LoudAggregator)) {
    result.aggregator = aggregator as LoudAggregator;
  } else {
    // Loud without a valid aggregator is unsafe — the runtime silently
    // drops every contribution. Refuse so the caller can fall back.
    return null;
  }

  result.contribution_schema = isPlainObject(raw.contribution_schema)
    ? raw.contribution_schema
    : { type: "string" };

  return result;
}
