# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""The .gitignore anchoring property, and the audit that enforces it.

Three silent exclusions have come from the same mistake: a pattern written for a
project-root directory, left unanchored, matching a directory of the same name
deeper in the tree. Each was followed by a regression test naming the directory
that broke. Those tests are backstops for one filename each; this file asserts
the property, and asserts that the audit still detects the two historical bugs
when they are reintroduced.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from audit_gitignore import (  # noqa: E402
    ignored_source_paths,
    is_anchored,
    patterns,
    unjustified,
)

IN_GIT_WORKTREE = (REPO_ROOT / ".git").exists()
needs_git = pytest.mark.skipif(
    not IN_GIT_WORKTREE,
    reason="requires a git worktree (target containers carry no .git)",
)


# --------------------------------------------------------------------------
# The property
# --------------------------------------------------------------------------


@needs_git
def test_nothing_in_the_source_tree_is_ignored() -> None:
    swallowed = ignored_source_paths()
    assert not swallowed, (
        f"these paths are git-ignored and should not be: {swallowed}. "
        f"Run scripts/audit_gitignore.py for the rule responsible."
    )


def test_every_pattern_is_anchored_or_justified() -> None:
    loose = unjustified()
    assert not loose, (
        f"unanchored patterns with no recorded reason: {loose}. Anchor with a "
        f"leading slash, or record why it must match at any depth."
    )


# --------------------------------------------------------------------------
# The audit itself detects the bugs it exists for
# --------------------------------------------------------------------------


@pytest.mark.parametrize("pattern", ["state/", "reference/", "build/", "manifest/", "consent/"])
def test_the_historical_bug_shape_is_a_finding(pattern: str) -> None:
    """Every one of these is a real directory name under src/ or docs/."""
    assert unjustified([(1, pattern)]) == [(1, pattern)]


@pytest.mark.parametrize("pattern", ["/state/", "/reference/", "/build/"])
def test_anchoring_clears_the_finding(pattern: str) -> None:
    assert unjustified([(1, pattern)]) == []


@pytest.mark.parametrize(
    ("pattern", "anchored"),
    [
        ("/state/", True),
        ("docs/_build/", True),
        ("share/python-wheels/", True),
        ("state/", False),
        ("__pycache__/", False),
        ("*.log", False),
        ("MANIFEST", False),
    ],
)
def test_a_trailing_slash_anchors_nothing(pattern: str, anchored: bool) -> None:
    """The mistake in one line: `state/` reads as anchored and is not."""
    assert is_anchored(pattern) is anchored


def test_negations_are_never_findings() -> None:
    assert unjustified([(1, "!docs/reference/README.md")]) == []


# --------------------------------------------------------------------------
# The audit is wired up
# --------------------------------------------------------------------------


@needs_git
def test_the_audit_script_passes() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/audit_gitignore.py"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_gitignore_has_patterns_to_audit() -> None:
    """Guards the silent-pass mode: an unreadable file auditing to zero findings."""
    assert len(patterns()) > 50
