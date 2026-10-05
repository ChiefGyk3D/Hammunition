# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later
"""#323: every CLI verb has a console path or a named issue, and the table stays honest."""

from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path
from types import ModuleType

import pytest

from hammunition.console import coverage
from hammunition.console.coverage import COVERED, EXEMPT, MAX_UNCOVERED, UNCOVERED, Verb

from .helpers import PACKAGE_DIR

REPO = Path(__file__).resolve().parents[2]


def _generator() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "gen_console_coverage", REPO / "scripts" / "gen_console_coverage.py"
    )
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


GEN = _generator()


def _names(words: Verb, source: str) -> bool:
    """The module's source writes the verb's words as consecutive string literals."""
    pattern = r"\s*,\s*".join(rf"[\"']{re.escape(w)}[\"']" for w in words)
    return re.search(pattern, source) is not None


def test_every_cli_verb_is_classified_exactly_once() -> None:
    verbs = GEN.cli_verbs()
    assert len(verbs) > 40, "the argparse walk found too few verbs to mean anything"
    assert GEN.unclassified(verbs) == []
    tables = [set(COVERED), set(UNCOVERED), set(EXEMPT)]
    for i, a in enumerate(tables):
        for b in tables[i + 1 :]:
            assert not (a & b), f"classified twice: {sorted(a & b)}"
    assert (set().union(*tables)) <= set(verbs), "a classified verb is not in the CLI"


def test_a_new_cli_verb_turns_the_check_red_and_names_it() -> None:
    verbs = [*GEN.cli_verbs(), ("frobnicate",)]
    assert GEN.unclassified(verbs) == [("frobnicate",)]


@pytest.mark.parametrize("verb", sorted(COVERED), ids=lambda v: " ".join(v))
def test_a_covered_verb_is_named_by_its_screen(verb: Verb) -> None:
    screen, module = COVERED[verb]
    path = PACKAGE_DIR / module
    assert path.exists(), f"{module} does not exist"
    assert _names(verb, path.read_text()), (
        f"{module} never writes `{' '.join(verb)}` as literal words, so {screen} does not "
        "offer it: move the verb to UNCOVERED in console/coverage.py, or fix the module"
    )


def test_the_uncovered_list_names_an_issue_and_does_not_grow() -> None:
    for verb, (issue, screen) in UNCOVERED.items():
        assert re.fullmatch(r"#\d+", issue), f"{' '.join(verb)}: no issue named"
        assert screen
    assert len(UNCOVERED) <= MAX_UNCOVERED, (
        f"{len(UNCOVERED)} verbs have no console path, up from {MAX_UNCOVERED}: cover the new "
        "verb, or raise MAX_UNCOVERED in a change that names the issue"
    )


def test_the_ceiling_is_tight_so_a_covered_verb_lowers_it() -> None:
    assert len(UNCOVERED) == MAX_UNCOVERED, (
        "lower MAX_UNCOVERED to the new count so the list cannot silently regrow"
    )


def test_the_exempt_verbs_have_a_reason() -> None:
    assert all(reason.strip() for reason in coverage.EXEMPT.values())


def test_the_generated_page_is_current() -> None:
    assert GEN.OUT.read_text() == GEN.render()
