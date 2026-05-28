"""Unit tests for widgets.props_validator — the JSON-Schema subset used to
enforce placement props against the widget's declared shape."""
from __future__ import annotations

import pytest

from slaides.widgets.props_validator import (
    PropsValidationError,
    coerce_props,
    validate_props,
)


def test_no_schema_passes_anything_through():
    out = validate_props({"foo": 1, "bar": "x"}, None)
    assert out == {"foo": 1, "bar": "x"}
    out = validate_props({"foo": 1}, {})
    assert out == {"foo": 1}


def test_string_type_enforced():
    schema = {"properties": {"question": {"type": "string"}}}
    validate_props({"question": "hi"}, schema)
    with pytest.raises(PropsValidationError, match="expected string"):
        validate_props({"question": 5}, schema)


def test_integer_type_rejects_bool():
    schema = {"properties": {"count": {"type": "integer"}}}
    validate_props({"count": 3}, schema)
    with pytest.raises(PropsValidationError, match="expected integer"):
        validate_props({"count": True}, schema)


def test_number_type_accepts_int_and_float_rejects_bool():
    schema = {"properties": {"weight": {"type": "number"}}}
    validate_props({"weight": 3}, schema)
    validate_props({"weight": 3.14}, schema)
    with pytest.raises(PropsValidationError, match="expected number"):
        validate_props({"weight": True}, schema)


def test_enum_static():
    schema = {"properties": {"mode": {"type": "string", "enum": ["a", "b"]}}}
    validate_props({"mode": "a"}, schema)
    with pytest.raises(PropsValidationError, match="not one of"):
        validate_props({"mode": "c"}, schema)


def test_min_max_length_string():
    schema = {"properties": {"q": {"type": "string", "minLength": 2, "maxLength": 5}}}
    validate_props({"q": "ok"}, schema)
    with pytest.raises(PropsValidationError, match="minLength"):
        validate_props({"q": "x"}, schema)
    with pytest.raises(PropsValidationError, match="maxLength"):
        validate_props({"q": "way too long"}, schema)


def test_minimum_maximum_number():
    schema = {"properties": {"score": {"type": "number", "minimum": 0, "maximum": 100}}}
    validate_props({"score": 50}, schema)
    with pytest.raises(PropsValidationError, match="below minimum"):
        validate_props({"score": -1}, schema)
    with pytest.raises(PropsValidationError, match="above maximum"):
        validate_props({"score": 101}, schema)


def test_array_items_validated_per_element():
    schema = {
        "properties": {
            "choices": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"},
                        "label": {"type": "string"},
                    },
                },
            }
        }
    }
    validate_props(
        {"choices": [{"id": "a", "label": "A"}, {"id": "b", "label": "B"}]},
        schema,
    )
    with pytest.raises(PropsValidationError, match=r"choices\[1\]\.label.*expected string"):
        validate_props(
            {"choices": [{"id": "a", "label": "A"}, {"id": "b", "label": 9}]},
            schema,
        )


def test_enum_from_resolves_against_sibling_array():
    schema = {
        "properties": {
            "choices": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {"id": {"type": "string"}},
                },
            },
            "correct_answer": {
                "type": "string",
                "enum.from": "choices.id",
            },
        }
    }
    payload = {
        "choices": [{"id": "a"}, {"id": "b"}, {"id": "c"}],
        "correct_answer": "b",
    }
    validate_props(payload, schema)

    bad = {**payload, "correct_answer": "z"}
    with pytest.raises(PropsValidationError, match="not one of"):
        validate_props(bad, schema)


def test_enum_from_with_empty_source_is_non_restrictive():
    # Mid-edit case: user typed `correct_answer` before adding any choices.
    # We don't want to block the save — the form will reconcile.
    schema = {
        "properties": {
            "choices": {"type": "array", "items": {"type": "object", "properties": {"id": {"type": "string"}}}},
            "correct_answer": {"type": "string", "enum.from": "choices.id"},
        }
    }
    validate_props({"choices": [], "correct_answer": "anything"}, schema)


def test_missing_top_level_keys_are_not_enforced():
    # Defaults are filled on read via coerce_props, not on write.
    schema = {"properties": {"a": {"type": "string"}, "b": {"type": "string"}}}
    validate_props({"a": "x"}, schema)


def test_coerce_props_backfills_defaults():
    schema = {
        "properties": {
            "question": {"type": "string", "default": "Pick one"},
            "choices": {"type": "array", "default": []},
            "no_default": {"type": "string"},
        }
    }
    out = coerce_props({}, schema)
    assert out == {"question": "Pick one", "choices": []}

    # Existing values are not overwritten.
    out = coerce_props({"question": "Custom"}, schema)
    assert out == {"question": "Custom", "choices": []}


def test_coerce_props_no_schema_passthrough():
    assert coerce_props({"a": 1}, None) == {"a": 1}
    assert coerce_props(None, None) == {}
    assert coerce_props(None, {}) == {}
