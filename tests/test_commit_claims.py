# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests for the commit-claims check.  D-031.

Verified the way the `.gitignore` audit was: by reintroducing the historical
bugs and asserting the check now refuses them. A checker that has never been
shown to catch the thing it was written for is itself an unverified claim, which
is the failure this whole decision is about.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from check_commit_claims import check  # noqa: E402


def diff_for(path: str, added: list[str], start: int = 1) -> str:
    body = "\n".join(f"+{line}" for line in added)
    return f"--- a/{path}\n+++ b/{path}\n@@ -{start},0 +{start},{len(added)} @@\n{body}\n"


# ---------------------------------------------------------------------------
# Bug 1: the D-028 amendment that matched nothing
# ---------------------------------------------------------------------------


def test_a_restated_decision_must_touch_that_decision() -> None:
    """The exact phrasing of 717ba26, whose amendment silently no-oped."""
    message = (
        "hardware: Minino captured\n\n"
        "D-028 no longer rests on an esptool constant for that identifier; it "
        "rests on three captures of unrelated hardware.\n"
    )
    problems = check(
        message,
        changed={"src/hammunition/manifest/hardware.py"},
        diff=diff_for("src/hammunition/manifest/hardware.py", ["    See D-028 for why."]),
        tracked={"src/hammunition/manifest/hardware.py"},
    )
    assert problems
    assert "D-028" in problems[0]


def test_mentioning_a_decision_elsewhere_does_not_satisfy_a_restatement() -> None:
    """Why 717ba26 passed the first version of this check.

    That commit added schema docstrings which happen to say "D-028", so a
    check keyed on "does any changed line mention it" was satisfied by prose
    about the decision rather than by the decision.
    """
    message = "docs: D-028 now covers three captures\n"
    diff = diff_for("catalog/hardware/classes/badgelife.yaml", ["# See D-028."])
    assert check(message, {"catalog/hardware/classes/badgelife.yaml"}, diff, set())


def test_citing_a_decision_as_rationale_claims_nothing() -> None:
    """`per D-014` asserts nothing about the diff, and must not be flagged.

    A check that fires on ordinary citation is a check people switch off, which
    would cost more than the bug it prevents.
    """
    message = (
        "backends: measure cargo against its best candidate\n\n"
        "Per D-014, backends are justified by measurement rather than by "
        "convention. Nothing in D-014 changes here.\n"
    )
    assert not check(message, {"scripts/deb-probe.sh"}, diff_for("scripts/deb-probe.sh", ["ok"]), set())


# ---------------------------------------------------------------------------
# Bug 3: the state/ directory that was written and never committed
# ---------------------------------------------------------------------------


def test_a_file_on_disk_that_git_does_not_have_is_refused(tmp_path: Path) -> None:
    """Written, nothing errored, and not in the commit. Silent in every tool."""
    message = "state: add the transaction log\n\nAdds `src/hammunition/state/log.py`.\n"
    problems = check(message, changed=set(), diff="", tracked=set())
    assert problems
    assert any("state/log.py" in p for p in problems)


def test_a_claimed_path_absent_from_the_commit_is_refused() -> None:
    message = "hardware: adds `catalog/hardware/devices/nonexistent-device.yaml`\n"
    problems = check(message, changed={"README.md"}, diff="", tracked={"README.md"})
    assert problems
    assert any("nonexistent-device" in p for p in problems)


def test_a_claimed_path_present_in_the_commit_passes() -> None:
    message = "hardware: adds `catalog/hardware/devices/minino.yaml`\n"
    assert not check(
        message,
        changed={"catalog/hardware/devices/minino.yaml"},
        diff="",
        tracked={"catalog/hardware/devices/minino.yaml"},
    )


def test_a_directory_counts_as_tracked_through_its_files() -> None:
    """`git ls-files` never lists a directory, and the first version tripped on it."""
    message = "contributing: adds `.github/ISSUE_TEMPLATE/` forms\n"
    assert not check(
        message,
        changed={".github/ISSUE_TEMPLATE/hardware-identifier.yml"},
        diff="",
        tracked={".github/ISSUE_TEMPLATE/hardware-identifier.yml"},
    )


# ---------------------------------------------------------------------------
# The check against this repository's own history
# ---------------------------------------------------------------------------


def run_on(rev: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "check_commit_claims.py"), "--rev", rev],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        check=False,
    )


@pytest.mark.skipif(not (REPO_ROOT / ".git").exists(), reason="not a git checkout")
def test_the_commit_that_prompted_this_is_still_caught() -> None:
    """717ba26 is the bug. If a later rewrite ever stops catching it, say so."""
    known = subprocess.run(
        ["git", "cat-file", "-e", "717ba26^{commit}"],
        cwd=REPO_ROOT,
        capture_output=True,
        check=False,
    )
    if known.returncode != 0:
        pytest.skip("717ba26 not present in this checkout")
    assert run_on("717ba26").returncode == 1


@pytest.mark.skipif(not (REPO_ROOT / ".git").exists(), reason="not a git checkout")
def test_the_head_commit_passes_its_own_check() -> None:
    assert run_on("HEAD").returncode == 0, run_on("HEAD").stderr
