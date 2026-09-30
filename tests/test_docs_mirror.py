# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""D-070 is written down where people look.  CLAUDE.md: a feature is not
done until it is documented."""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
TITLE = (
    "## D-070 — A data artifact may be taken from a LAN mirror the operator names, "
    "verified the same either way, and the engine can list what it would fetch "
    "without a station"
)


def _flat(path: str) -> str:
    return " ".join((REPO_ROOT / path).read_text().split())


def test_d070_is_recorded_after_what_preceded_it_under_its_assigned_title() -> None:
    """Appended, never inserted: D-070 follows every entry that existed when it
    was written. It is no longer the last one -- D-069 was appended after it,
    by the same rule (entries are added at the end and never renumbered)."""
    text = (REPO_ROOT / "docs" / "DECISIONS.md").read_text()
    assert TITLE in text
    at = text.index(TITLE)
    for earlier in ("## D-063 ", "## D-064 ", "## D-066 ", "## D-067 "):
        assert text.index(earlier) < at, f"{earlier.strip()} comes before D-070"


def test_the_guide_points_at_the_bunker_and_says_lan_only() -> None:
    guide = _flat("docs/guides/lan-mirror.md")
    assert "https://github.com/ChiefGyk3D/hammunition-bunker" in guide
    assert "never reachable from the internet" in guide
    assert "station set --mirror" in guide and "--no-mirror" in guide


def test_the_cli_reference_documents_every_new_flag() -> None:
    cli = _flat("docs/reference/cli.md")
    for flag in ("--mirror URL", "--clear-mirror", "--no-mirror", "`artifacts` document"):
        assert flag in cli, flag


def test_the_log_reference_documents_the_fetch_facts() -> None:
    log = _flat("docs/reference/transaction-log.md")
    assert "fetched_from" in log and "mirror_failure" in log


def test_claude_md_and_the_changelog_carry_it() -> None:
    assert "**D-070**" in _flat("CLAUDE.md")
    changelog = (REPO_ROOT / "CHANGELOG.md").read_text()
    unreleased = changelog[changelog.index("## Unreleased") : changelog.index("\n## v")]
    assert "D-070" in unreleased


def test_the_guide_says_the_plan_still_needs_the_internet() -> None:
    guide = _flat("docs/guides/lan-mirror.md")
    assert "does not make an install work offline" in guide
