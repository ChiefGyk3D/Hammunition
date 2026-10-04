# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later
from typing import Any

import pytest

from .schema_check import ENVELOPE, validate

SCHEMA: dict[str, Any] = {
    "$defs": {
        "Row": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "n": {"type": "integer"},
                "s": {"anyOf": [{"type": "string"}, {"type": "null"}]},
            },
            "required": ["n", "s"],
        }
    },
    "type": "object",
    "additionalProperties": False,
    "properties": {"rows": {"type": "array", "items": {"$ref": "#/$defs/Row"}}},
    "required": ["rows"],
}


def test_valid_document_passes() -> None:
    assert validate({"rows": [{"n": 1, "s": None}, {"n": 2, "s": "x"}]}, SCHEMA) == []


def test_extra_field_is_rejected() -> None:
    assert validate({"rows": [{"n": 1, "s": None, "extra": 1}]}, SCHEMA)


def test_missing_required_field_is_rejected() -> None:
    assert validate({"rows": [{"n": 1}]}, SCHEMA)


def test_wrong_type_is_rejected_and_bool_is_not_an_integer() -> None:
    assert validate({"rows": [{"n": "1", "s": None}]}, SCHEMA)
    assert validate({"rows": [{"n": True, "s": None}]}, SCHEMA)


def test_the_envelope_names() -> None:
    assert {"schema", "kind", "engine"} == ENVELOPE


@pytest.mark.parametrize(
    "sub",
    [
        {"enum": ["a"]},
        {"const": 1},
        {"oneOf": [{"type": "string"}]},
        {"pattern": "x"},
        {"type": ["string", "null"]},
        {"type": "float"},
        {"type": "object", "additionalProperties": {"type": "string"}},
    ],
)
def test_an_unsupported_keyword_or_shape_fails_loudly(sub: dict[str, Any]) -> None:
    with pytest.raises(NotImplementedError, match=r"\$"):
        validate({"a": "x"}, sub)


def test_annotations_are_ignored() -> None:
    assert validate("x", {"title": "T", "description": "d", "type": "string"}) == []
