# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""Shared checks for the ``--json`` interface tests.  D-059.

Golden files live in ``tests/fixtures/json/``. A change to a document is a
deliberate diff: run the failing test once with ``HAMMUNITION_UPDATE_GOLDEN=1``,
read the diff to the golden file, and commit it with the change that caused it.
"""

from __future__ import annotations

import inspect
import json
import os
import re
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from pydantic import TypeAdapter

from hammunition.interface.envelope import SCHEMA, kinds

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent
GOLDEN = HERE / "fixtures" / "json"
FIXTURE_CATALOG = GOLDEN / "catalog"
UPDATE_ENV = "HAMMUNITION_UPDATE_GOLDEN"

#: A value as the text shows it: two or more word characters, dots, slashes,
#: pluses, tildes or hyphens. A single character (a one-digit count) is too
#: common to attribute and is not checked. `@` separates: the text joins
#: `NAME@ADDRESS` where the JSON carries two fields, and each half is checked.
TOKEN = re.compile(r"[\w./+~-]{2,}")


def parse_one(stdout: str) -> dict[str, Any]:
    """The whole of stdout as exactly one JSON object, envelope checked."""
    doc = json.loads(stdout)
    assert isinstance(doc, dict), f"stdout is a {type(doc).__name__}, not one document"
    assert doc.get("schema") == SCHEMA, doc.get("schema")
    assert isinstance(doc.get("kind"), str) and isinstance(doc.get("engine"), str)
    return doc


def validate(doc: Mapping[str, Any]) -> None:
    """*doc* validates against the published schema of its kind."""
    body = {k: v for k, v in doc.items() if k not in ("schema", "kind", "engine")}
    cls = kinds()[str(doc["kind"])]
    TypeAdapter(cls).validate_python(body)


def _normalise(doc: Mapping[str, Any], replacements: Mapping[str, str]) -> Any:
    text = json.dumps(doc, ensure_ascii=False)
    for real, placeholder in replacements.items():
        text = text.replace(json.dumps(real, ensure_ascii=False)[1:-1], placeholder)
    loaded = json.loads(text)
    loaded["engine"] = "<engine>"
    return loaded


def assert_golden(
    name: str, doc: Mapping[str, Any], replacements: Mapping[str, str] | None = None
) -> None:
    """*doc* equals ``tests/fixtures/json/<name>.json``, engine version and
    machine paths replaced by placeholders so the file is the same everywhere."""
    rendered = json.dumps(_normalise(doc, replacements or {}), ensure_ascii=False, indent=2) + "\n"
    _compare(GOLDEN / f"{name}.json", rendered)


def assert_golden_text(name: str, text: str) -> None:
    """*text* equals ``tests/fixtures/json/<name>.txt`` byte for byte."""
    _compare(GOLDEN / f"{name}.txt", text)


def _compare(path: Path, rendered: str) -> None:
    if os.environ.get(UPDATE_ENV) == "1":
        path.write_text(rendered)
        return
    assert path.exists(), (
        f"no golden file {path.relative_to(REPO_ROOT)}: run this test once with "
        f"{UPDATE_ENV}=1, review the file, and commit it"
    )
    expected = path.read_text()
    assert rendered == expected, (
        f"{path.relative_to(REPO_ROOT)} differs from what the engine now prints. If the "
        f"change is intended, re-run with {UPDATE_ENV}=1 and commit the diff."
    )


def assert_text_values_in_json(
    text: str, doc: Mapping[str, Any], *renderers: Callable[..., object]
) -> None:
    """Every value the text shows is carried by the JSON.

    A token of *text* is chrome when it occurs in the source of one of the
    *renderers* (a label, a fixed sentence) and a value otherwise; every value
    must occur somewhere in the serialised document.
    """
    chrome = "\n".join(inspect.getsource(r) for r in renderers)
    flat = json.dumps(doc, ensure_ascii=False)
    missing = sorted({t for t in TOKEN.findall(text) if t not in chrome and t not in flat})
    assert not missing, (
        f"the text shows {len(missing)} value(s) the JSON does not carry: {missing[:12]}"
    )
