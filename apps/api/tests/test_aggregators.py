"""Unit tests for the pure aggregator primitives used by the Widgets v2
unified `widget.contribute` protocol."""
from __future__ import annotations

import pytest

from slaides.sessions.aggregators import (
    APPEND_CAP,
    KEYED_TALLY_CAP,
    SET_UNION_CAP,
    AggregatorError,
    append_contribute,
    apply_contribution,
    keyed_tally_contribute,
    latest_per_participant_contribute,
    set_union_contribute,
    tally_contribute,
    tally_public,
)


# --- tally ---

def test_tally_counts_unique_voters():
    state: dict = {}
    state = tally_contribute(state, "a", "ref1")
    state = tally_contribute(state, "b", "ref2")
    state = tally_contribute(state, "a", "ref3")
    public = tally_public(state)
    assert public["tally"] == {"a": 2, "b": 1}
    assert public["voters"] == 3
    # `_votes` is the private index — it must not leak into the public state.
    assert "_votes" not in public


def test_tally_revote_replaces_previous_choice():
    state: dict = {}
    state = tally_contribute(state, "a", "ref1")
    state = tally_contribute(state, "b", "ref1")
    public = tally_public(state)
    assert public["tally"] == {"b": 1}
    assert public["voters"] == 1


def test_tally_idempotent_same_vote():
    state: dict = {}
    state = tally_contribute(state, "a", "ref1")
    state = tally_contribute(state, "a", "ref1")
    public = tally_public(state)
    assert public["tally"] == {"a": 1}
    assert public["voters"] == 1


def test_tally_rejects_non_primitive_contribution():
    with pytest.raises(AggregatorError):
        tally_contribute({}, {"choice": "a"}, "ref1")


# --- latest_per_participant ---

def test_latest_per_participant_overwrites():
    state = latest_per_participant_contribute({}, {"x": 1, "y": 2}, "ref1")
    state = latest_per_participant_contribute(state, {"x": 1, "y": 3}, "ref1")
    state = latest_per_participant_contribute(state, {"x": 0, "y": 0}, "ref2")
    assert state["values"]["ref1"] == {"x": 1, "y": 3}
    assert state["values"]["ref2"] == {"x": 0, "y": 0}


# --- append ---

def test_append_grows_and_increments_total():
    state: dict = {}
    state = append_contribute(state, "first", "ref1")
    state = append_contribute(state, "second", "ref2")
    assert [e["value"] for e in state["entries"]] == ["first", "second"]
    assert state["total"] == 2


def test_append_caps_entries_but_grows_total():
    state: dict = {}
    for i in range(APPEND_CAP + 5):
        state = append_contribute(state, f"e{i}", "ref")
    assert len(state["entries"]) == APPEND_CAP
    assert state["total"] == APPEND_CAP + 5
    # Newest entry preserved at the tail; oldest dropped from the head.
    assert state["entries"][-1]["value"] == f"e{APPEND_CAP + 4}"
    assert state["entries"][0]["value"] == "e5"


# --- set_union ---

def test_set_union_counts_distinct_contributors_per_value():
    state: dict = {}
    state = set_union_contribute(state, "hello", "ref1")
    state = set_union_contribute(state, "hello", "ref2")
    state = set_union_contribute(state, "hello", "ref1")  # idempotent
    state = set_union_contribute(state, "world", "ref1")
    assert state["counts"] == {"hello": 2, "world": 1}


def test_set_union_rejects_empty_string():
    with pytest.raises(AggregatorError):
        set_union_contribute({}, "   ", "ref1")


def test_set_union_cap_enforced():
    state: dict = {}
    for i in range(SET_UNION_CAP):
        state = set_union_contribute(state, f"v{i}", "ref")
    assert len(state["counts"]) == SET_UNION_CAP
    with pytest.raises(AggregatorError):
        set_union_contribute(state, "overflow", "ref")
    # An existing value can still receive new contributions even at cap.
    state = set_union_contribute(state, "v0", "another-ref")
    assert state["counts"]["v0"] == 2


# --- keyed_tally ---

def test_keyed_tally_add_and_vote_toggle():
    state = keyed_tally_contribute({}, {"op": "add", "value": "Item A"}, "ref1")
    item_id = state["items"][0]["id"]
    state = keyed_tally_contribute(state, {"op": "vote", "id": item_id}, "ref2")
    state = keyed_tally_contribute(state, {"op": "vote", "id": item_id}, "ref3")
    assert state["items"][0]["votes"] == 2
    # Re-voting from ref2 toggles off.
    state = keyed_tally_contribute(state, {"op": "vote", "id": item_id}, "ref2")
    assert state["items"][0]["votes"] == 1


def test_keyed_tally_cap_enforced():
    state: dict = {}
    for i in range(KEYED_TALLY_CAP):
        state = keyed_tally_contribute(state, {"op": "add", "value": f"item-{i}"}, "ref")
    with pytest.raises(AggregatorError):
        keyed_tally_contribute(state, {"op": "add", "value": "overflow"}, "ref")


def test_keyed_tally_rejects_unknown_op():
    with pytest.raises(AggregatorError):
        keyed_tally_contribute({}, {"op": "delete", "id": "x"}, "ref")


# --- dispatch ---

def test_apply_contribution_dispatches_by_name():
    state = apply_contribution("tally", {}, "a", "ref1")
    assert state["tally"] == {"a": 1}


def test_apply_contribution_rejects_unknown_aggregator():
    with pytest.raises(ValueError, match="unknown aggregator"):
        apply_contribution("nope", {}, "x", "ref")
