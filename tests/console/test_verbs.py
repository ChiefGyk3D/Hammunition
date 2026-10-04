# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later
import os
import re
from pathlib import Path

import pytest

from hammunition.console import verbs
from hammunition.console.verbs import NotAJsonVerb

ENGINE_ROOT_VAR = "HAMMUNITION_ENGINE_ROOT"


@pytest.mark.parametrize(
    "words,expected",
    [
        (["status"], ("status",)),
        (["station", "show"], ("station", "show")),
        (["maps", "regions", "vermont"], ("maps", "regions")),
        (["reference", "books"], ("reference", "books")),
        (["list", "profiles"], ("list",)),
        (["install", "x", "--dry-run"], ("install",)),
    ],
)
def test_verb_of(words: list[str], expected: tuple[str, ...]) -> None:
    assert verbs.verb_of(words) == expected


@pytest.mark.parametrize(
    "words",
    [
        ["hardware", "list"],
        ["station", "set", "--callsign=X"],
        ["time"],
        ["menus", "apply"],
        ["hardware", "apply"],
        [],
    ],
)
def test_a_verb_with_no_json_form_is_refused(words: list[str]) -> None:
    with pytest.raises(NotAJsonVerb):
        verbs.require_json_verb(words)


@pytest.mark.parametrize("verb", ["install", "uninstall"])
def test_install_and_uninstall_are_only_ever_read_as_a_dry_run(verb: str) -> None:
    with pytest.raises(NotAJsonVerb, match="dry-run"):
        verbs.require_json_verb([verb, "station"])
    verbs.require_json_verb([verb, "station", "--dry-run"])


def test_every_verb_is_one_the_engine_lists_under_commands() -> None:
    """The authority is the engine's own list. Opt-in: set HAMMUNITION_ENGINE_ROOT to an engine checkout."""
    root = os.environ.get(ENGINE_ROOT_VAR)
    if not root:
        pytest.skip(
            f"{ENGINE_ROOT_VAR} is not set (point it at an engine checkout to check the verb list)"
        )
    doc = Path(root) / "docs" / "reference" / "json-interface.md"
    assert doc.is_file(), f"{ENGINE_ROOT_VAR} is set but {doc} does not exist"
    text = doc.read_text()
    listed = {
        tuple(m.group(1).split()) for m in re.finditer(r"^- `hammunition ([a-z ]+?)`", text, re.M)
    }
    for verb in verbs.JSON_VERBS:
        assert verb in listed, (
            f"{verb} is not under Commands in json-interface.md: it has no JSON form"
        )
