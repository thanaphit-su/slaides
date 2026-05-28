"""Pure aggregator functions for the unified `widget.contribute` protocol.

Each aggregator owns a single shared-state projection per `(session, placement)`.
The audience widget emits a contribution; the server runs the aggregator over
the current state and broadcasts the new state to every connected viewer. The
five aggregators below cover the realistic Loud-widget cases we identified in
[docs/WIDGETS_V2.md](docs/WIDGETS_V2.md):

  - tally:                  { choice_id → count }
  - latest_per_participant: { ref → value }
  - append:                 [{ ref, value, ts }] (capped)
  - set_union:              { value → count }
  - keyed_tally:            [{ id, ref, value, ts, votes }]

Each function is *pure*: it takes the current state dict and the contribution
and returns a new state dict. Callers (the session service today, the
placement_state table in Step 4) are responsible for persistence. Keeping the
core math pure makes it trivial to unit-test and reuse across the legacy
session_slide.results path and the upcoming placement_state path.

Step 3 uses these to back native polls (tally) and open questions (append).
The other three implementations ship now so Step 4's LLM-generated widgets
can route to them without a follow-up backend change.
"""
from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

# Conservative defaults — same numbers as the brief; can be tuned per-widget
# in Step 4 once contribution_schema declarations exist.
APPEND_CAP = 200
SET_UNION_CAP = 500
KEYED_TALLY_CAP = 100
CONTRIBUTION_BYTES_CAP = 2048


class AggregatorError(ValueError):
    """Raised when a contribution payload doesn't fit the aggregator shape."""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ensure_dict(state: Any) -> dict:
    return dict(state) if isinstance(state, Mapping) else {}


def _ensure_list(value: Any) -> list:
    return list(value) if isinstance(value, list) else []


def _validate_size(value: Any) -> None:
    try:
        # Rough but adequate cap on per-contribution payload size.
        import json
        encoded = json.dumps(value, ensure_ascii=False)
    except (TypeError, ValueError) as exc:
        raise AggregatorError(f"contribution is not JSON-serialisable: {exc}") from exc
    if len(encoded.encode("utf-8")) > CONTRIBUTION_BYTES_CAP:
        raise AggregatorError(
            f"contribution exceeds {CONTRIBUTION_BYTES_CAP}-byte cap"
        )


# ---- tally ----

def tally_contribute(state: Mapping[str, Any] | None, contribution: Any, ref: str) -> dict:
    """Single-choice vote. State shape: `{ tally: {choice → int}, voters: int }`.

    A given participant_ref voting twice replaces their old vote (tracked via
    `_votes` index: `{ ref → choice_id }` stored in state). The public payload
    drops `_votes` before broadcasting.
    """
    _validate_size(contribution)
    if not isinstance(contribution, (str, int)):
        raise AggregatorError("tally contribution must be a primitive choice id")
    choice_id = str(contribution)
    s = _ensure_dict(state)
    votes: dict[str, str] = dict(s.get("_votes") or {})
    previous = votes.get(ref)
    votes[ref] = choice_id

    tally: dict[str, int] = dict(s.get("tally") or {})
    if previous is not None and previous != choice_id:
        tally[previous] = max(0, int(tally.get(previous, 0)) - 1)
        if tally[previous] == 0:
            tally.pop(previous, None)
    if previous != choice_id:
        tally[choice_id] = int(tally.get(choice_id, 0)) + 1
    s["tally"] = tally
    s["_votes"] = votes
    s["voters"] = len(votes)
    return s


def tally_public(state: Mapping[str, Any] | None) -> dict:
    """Return the audience-visible projection of a tally state — drops the
    `_votes` index so participants can't see who voted for what."""
    s = _ensure_dict(state)
    s.pop("_votes", None)
    return s


# ---- latest_per_participant ----

def latest_per_participant_contribute(
    state: Mapping[str, Any] | None, contribution: Any, ref: str
) -> dict:
    """Each participant has one current value; new contributions overwrite.

    State shape: `{ values: { ref → value } }`.
    """
    _validate_size(contribution)
    s = _ensure_dict(state)
    values = dict(s.get("values") or {})
    values[ref] = contribution
    s["values"] = values
    return s


# ---- append ----

def append_contribute(
    state: Mapping[str, Any] | None, contribution: Any, ref: str
) -> dict:
    """Append-only event log (capped). State shape: `{ entries: [{ref, value, ts}], total: int }`.

    Once `entries` hits `APPEND_CAP`, oldest entries get dropped. `total` keeps
    growing so the UI can show "47 answers so far" even after rotation.
    """
    _validate_size(contribution)
    s = _ensure_dict(state)
    entries = _ensure_list(s.get("entries"))
    entries.append({"ref": ref, "value": contribution, "ts": _now_iso()})
    if len(entries) > APPEND_CAP:
        entries = entries[-APPEND_CAP:]
    s["entries"] = entries
    s["total"] = int(s.get("total", 0)) + 1
    return s


# ---- set_union ----

def set_union_contribute(
    state: Mapping[str, Any] | None, contribution: Any, ref: str
) -> dict:
    """String set with per-value counts. Each participant_ref can contribute
    multiple distinct values; same value from the same participant only counts
    once. State shape: `{ counts: { value → int }, contributors: { value → [ref] } }`.

    Cap is the number of distinct values, not the total contribution count.
    """
    _validate_size(contribution)
    if not isinstance(contribution, str):
        raise AggregatorError("set_union contribution must be a string")
    value = contribution.strip()
    if not value:
        raise AggregatorError("set_union contribution must be a non-empty string")
    s = _ensure_dict(state)
    counts: dict[str, int] = dict(s.get("counts") or {})
    contributors: dict[str, list[str]] = {
        k: list(v) for k, v in (s.get("contributors") or {}).items()
    }
    existing_refs = contributors.get(value, [])
    if ref in existing_refs:
        # Idempotent — same participant, same word, no change.
        s["counts"] = counts
        s["contributors"] = contributors
        return s
    if value not in counts and len(counts) >= SET_UNION_CAP:
        raise AggregatorError(
            f"set_union exceeds {SET_UNION_CAP}-value cap"
        )
    counts[value] = counts.get(value, 0) + 1
    contributors[value] = [*existing_refs, ref]
    s["counts"] = counts
    s["contributors"] = contributors
    return s


# ---- keyed_tally ----

def keyed_tally_contribute(
    state: Mapping[str, Any] | None, contribution: Any, ref: str
) -> dict:
    """Two-layer: items appended by participants AND votes tallied per item.

    Contribution shapes:
      - `{ "op": "add", "value": "<idea>" }` — appends an item; returns its id
      - `{ "op": "vote", "id": "<item_id>" }` — toggles a vote by this ref on
        the item (re-voting unsets it)

    State shape: `{ items: [{id, ref, value, ts, votes: int, voters: [ref]}] }`.
    """
    _validate_size(contribution)
    if not isinstance(contribution, Mapping):
        raise AggregatorError("keyed_tally contribution must be an object")
    op = contribution.get("op")
    s = _ensure_dict(state)
    items: list[dict] = [dict(item) for item in _ensure_list(s.get("items"))]
    if op == "add":
        value = contribution.get("value")
        if not isinstance(value, str) or not value.strip():
            raise AggregatorError("keyed_tally add requires a non-empty string value")
        if len(items) >= KEYED_TALLY_CAP:
            raise AggregatorError(
                f"keyed_tally exceeds {KEYED_TALLY_CAP}-item cap"
            )
        new_id = f"kt-{len(items) + 1}-{int(datetime.now(timezone.utc).timestamp() * 1000)}"
        items.append(
            {
                "id": new_id,
                "ref": ref,
                "value": value.strip(),
                "ts": _now_iso(),
                "votes": 0,
                "voters": [],
            }
        )
    elif op == "vote":
        target_id = str(contribution.get("id") or "")
        if not target_id:
            raise AggregatorError("keyed_tally vote requires an item id")
        target = next((item for item in items if item.get("id") == target_id), None)
        if target is None:
            raise AggregatorError(f"keyed_tally vote target {target_id!r} not found")
        voters = list(target.get("voters") or [])
        if ref in voters:
            voters.remove(ref)
        else:
            voters.append(ref)
        target["voters"] = voters
        target["votes"] = len(voters)
    else:
        raise AggregatorError(f"keyed_tally op must be 'add' or 'vote', got {op!r}")
    s["items"] = items
    return s


AGGREGATORS = {
    "tally": tally_contribute,
    "latest_per_participant": latest_per_participant_contribute,
    "append": append_contribute,
    "set_union": set_union_contribute,
    "keyed_tally": keyed_tally_contribute,
}


def apply_contribution(
    aggregator: str,
    state: Mapping[str, Any] | None,
    contribution: Any,
    ref: str,
) -> dict:
    """Dispatch to the named aggregator. Raises `AggregatorError` on shape
    mismatch or cap-exceeded; raises `ValueError` on unknown aggregator name."""
    fn = AGGREGATORS.get(aggregator)
    if fn is None:
        raise ValueError(f"unknown aggregator: {aggregator!r}")
    return fn(state, contribution, ref)
