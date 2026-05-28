"""JSON-Schema subset validator for widget props_schema.

Widgets declare a `props_schema` that's a strict subset of JSON Schema so the
LLM has a clear contract and the frontend form renderer can render every shape
without a runtime surprise. Supported keywords:

  type:        "string" | "number" | "integer" | "boolean" | "array" | "object"
  enum:        list of allowed primitive values
  default:     fallback value used when the placement's `props` dict omits it
  description: free-form help text (rendered as a hint in the form)
  items:       nested schema, applies when type=="array"
  properties:  {key: schema}, applies when type=="object"
  minLength:   string length lower bound
  maxLength:   string length upper bound
  minimum:     numeric lower bound
  maximum:     numeric upper bound

SLAIDES-specific extension:

  enum.from:   string like "<other_prop>.<key>" — the enum's allowed values are
               sourced from the current sibling array's `.key` field. The
               validator only checks that the value appears in that array;
               cross-field forms in the UI wire the reactive picker.

The validator is permissive about missing top-level props (default backfill
happens lazily on read in `coerce_props`). It rejects type mismatches,
out-of-enum values, and any payload that doesn't match the declared shape.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


class PropsValidationError(ValueError):
    """Raised when placement props don't match the widget's props_schema.

    `path` is the dot-path to the offending value (e.g. "choices[2].label")
    for human-readable error messages.
    """

    def __init__(self, message: str, path: str = "") -> None:
        super().__init__(message)
        self.path = path
        self.message = message

    def __str__(self) -> str:
        if self.path:
            return f"{self.path}: {self.message}"
        return self.message


_PRIMITIVE_TYPES = {"string", "number", "integer", "boolean"}
_ALL_TYPES = _PRIMITIVE_TYPES | {"array", "object"}


def _matches_type(value: Any, declared: str) -> bool:
    if declared == "string":
        return isinstance(value, str)
    if declared == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if declared == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if declared == "boolean":
        return isinstance(value, bool)
    if declared == "array":
        return isinstance(value, list)
    if declared == "object":
        return isinstance(value, dict)
    return False


def _resolve_enum_from(
    spec: str, sibling_props: Mapping[str, Any]
) -> list[Any]:
    """Resolve `enum.from: "<other_prop>.<key>"` against the current props.

    For `choices.id` against `{"choices": [{"id": "a"}, {"id": "b"}]}`,
    returns `["a", "b"]`. Returns an empty list if the path doesn't resolve;
    callers treat that as "no restriction" so a half-filled form doesn't
    block save.
    """
    if "." not in spec:
        return []
    source_key, field = spec.split(".", 1)
    source = sibling_props.get(source_key)
    if not isinstance(source, list):
        return []
    out: list[Any] = []
    for entry in source:
        if isinstance(entry, dict) and field in entry:
            out.append(entry[field])
    return out


def _validate(
    value: Any,
    schema: Mapping[str, Any],
    *,
    path: str,
    sibling_props: Mapping[str, Any],
) -> None:
    declared_type = schema.get("type")
    if declared_type is not None:
        if declared_type not in _ALL_TYPES:
            raise PropsValidationError(
                f"unsupported declared type {declared_type!r}", path=path
            )
        if not _matches_type(value, declared_type):
            raise PropsValidationError(
                f"expected {declared_type}, got {type(value).__name__}",
                path=path,
            )

    if "enum" in schema:
        allowed = schema["enum"]
        if not isinstance(allowed, list):
            raise PropsValidationError("enum must be a list", path=path)
        if value not in allowed:
            raise PropsValidationError(
                f"value {value!r} is not one of {allowed!r}", path=path
            )

    enum_from = schema.get("enum.from")
    if isinstance(enum_from, str) and enum_from:
        allowed_dyn = _resolve_enum_from(enum_from, sibling_props)
        # If the source array hasn't been populated yet, treat enum.from as
        # non-restrictive — the form is in mid-edit. Only reject when the
        # source resolves to a non-empty list and the value isn't in it.
        if allowed_dyn and value not in allowed_dyn:
            raise PropsValidationError(
                f"value {value!r} is not one of {allowed_dyn!r} (from {enum_from})",
                path=path,
            )

    if isinstance(value, str):
        if "minLength" in schema and len(value) < int(schema["minLength"]):
            raise PropsValidationError(
                f"string shorter than minLength={schema['minLength']}", path=path
            )
        if "maxLength" in schema and len(value) > int(schema["maxLength"]):
            raise PropsValidationError(
                f"string longer than maxLength={schema['maxLength']}", path=path
            )

    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            raise PropsValidationError(
                f"value below minimum={schema['minimum']}", path=path
            )
        if "maximum" in schema and value > schema["maximum"]:
            raise PropsValidationError(
                f"value above maximum={schema['maximum']}", path=path
            )

    if isinstance(value, list):
        item_schema = schema.get("items")
        if isinstance(item_schema, Mapping):
            for i, item in enumerate(value):
                _validate(
                    item,
                    item_schema,
                    path=f"{path}[{i}]" if path else f"[{i}]",
                    # Inside an array element the "siblings" are the element's
                    # own object fields, so enum.from sees them.
                    sibling_props=item if isinstance(item, Mapping) else {},
                )

    if isinstance(value, dict):
        properties = schema.get("properties")
        if isinstance(properties, Mapping):
            for key, sub_schema in properties.items():
                if key in value and isinstance(sub_schema, Mapping):
                    _validate(
                        value[key],
                        sub_schema,
                        path=f"{path}.{key}" if path else key,
                        sibling_props=value,
                    )


def validate_props(
    props: Mapping[str, Any] | None,
    props_schema: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Validate `props` against `props_schema`.

    Returns a normalized props dict (a shallow copy with unknown keys preserved
    — callers may want them for forward-compatibility during schema rolls).
    Raises `PropsValidationError` on the first violation.

    Both arguments may be None; an empty schema accepts any props.
    """
    if not props_schema:
        return dict(props or {})
    if not isinstance(props_schema, Mapping):
        raise PropsValidationError("props_schema must be an object")

    declared_props = props_schema if "properties" not in props_schema else props_schema.get("properties")
    if not isinstance(declared_props, Mapping):
        return dict(props or {})

    payload = dict(props or {})
    for key, sub_schema in declared_props.items():
        if key not in payload:
            # Missing key — handled by coerce_props at read time, not enforced here.
            continue
        if not isinstance(sub_schema, Mapping):
            continue
        _validate(payload[key], sub_schema, path=key, sibling_props=payload)
    return payload


def coerce_props(
    props: Mapping[str, Any] | None,
    props_schema: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Return `props` with any missing top-level keys backfilled from their
    `default` in `props_schema`.

    Used on read so the bridge sees a complete object even when older
    placements predate newly-added schema keys.
    """
    out: dict[str, Any] = dict(props or {})
    if not isinstance(props_schema, Mapping):
        return out
    declared = props_schema if "properties" not in props_schema else props_schema.get("properties")
    if not isinstance(declared, Mapping):
        return out
    for key, sub_schema in declared.items():
        if key in out:
            continue
        if isinstance(sub_schema, Mapping) and "default" in sub_schema:
            out[key] = sub_schema["default"]
    return out
