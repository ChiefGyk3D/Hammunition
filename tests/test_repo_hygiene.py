# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""Repository hygiene tests.

These guard two invariants that are easy to break silently:

1. ``docs/reference/`` is a required documentation section (CLAUDE.md) and must
   stay tracked. An unanchored ``reference/`` rule in .gitignore also matches it
   and silently excluded the AHRL inventory once already.
2. Third-party reference material (AHRL tarballs, extracted upstream trees) must
   never be committed. Provenance stays clean — see D-011.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent

# These tests assert properties of the *repository* — .gitignore behaviour,
# what is tracked, that third-party material never lands in git. A target
# container deliberately contains only src/, catalog/, tests/ and scripts/,
# with no .git and no docs/ tree, so there is nothing here to assert about.
# Skipping is correct: running them there would test the copy, not the repo.
IN_GIT_WORKTREE = (REPO_ROOT / ".git").exists()

pytestmark = pytest.mark.skipif(
    not IN_GIT_WORKTREE,
    reason="repository hygiene tests require a git worktree (not present in target containers)",
)


def _git(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def _is_ignored(path: str) -> bool:
    """True if git would ignore *path*."""
    return _git("check-ignore", "-q", "--no-index", path).returncode == 0


def _tracked_files() -> set[str]:
    result = _git("ls-files")
    assert result.returncode == 0, result.stderr
    return set(result.stdout.split())


# --------------------------------------------------------------------------
# docs/reference/ must stay tracked
# --------------------------------------------------------------------------


def test_docs_reference_dir_is_not_ignored() -> None:
    """The unanchored 'reference/' rule regression. See CLAUDE.md Conventions."""
    assert not _is_ignored("docs/reference/"), (
        "docs/reference/ is git-ignored. The .gitignore rule for third-party "
        "reference material must be anchored to the repo root (/reference/), "
        "or it also swallows the docs section of the same name."
    )


def test_docs_reference_files_are_not_ignored() -> None:
    for name in ("ahrl-inventory.md", "schema.md", "cli.md"):
        path = f"docs/reference/{name}"
        assert not _is_ignored(path), f"{path} would be ignored"


def test_ahrl_inventory_is_tracked() -> None:
    assert "docs/reference/ahrl-inventory.md" in _tracked_files(), (
        "docs/reference/ahrl-inventory.md is not tracked by git"
    )


def test_docs_reference_has_tracked_content() -> None:
    tracked = _tracked_files()
    under_docs_reference = {f for f in tracked if f.startswith("docs/reference/")}
    assert under_docs_reference, "no files tracked under docs/reference/"


# --------------------------------------------------------------------------
# Third-party material must stay out
# --------------------------------------------------------------------------


def test_root_reference_dir_is_ignored() -> None:
    """The AHRL extracted tree lives here and must never be committed."""
    assert _is_ignored("reference/"), "/reference/ must be git-ignored (D-011)"


@pytest.mark.parametrize(
    "path",
    [
        "reference/bin/install_ahrl",
        "reference/tarballs/fldigi-4.2.11.tar.gz",
        # Source trees and probe output added by the round-3 inventories. Each
        # is upstream material or a machine-generated measurement, never ours.
        "reference/skywave/SDR-Scripts/sdr-installer.sh",
        "reference/skywave/skywavelinux-index.html",
        "reference/dragonos/README.txt",
        "reference/probes/blend-debian-13.tsv",
        "reference/blend-tasks/sdr",
        "vendor/anything.txt",
        "andy_v27.tar.gz",
        "some/nested/upstream.tar.gz",
        "GridTracker2-amd64.deb",
    ],
)
def test_third_party_material_is_ignored(path: str) -> None:
    assert _is_ignored(path), f"{path} should be git-ignored but is not"


def test_no_third_party_archives_are_tracked() -> None:
    suffixes = (
        ".tar",
        ".tar.gz",
        ".tgz",
        ".tar.bz2",
        ".tar.xz",
        ".zip",
        ".deb",
        ".rpm",
        ".whl",
        ".AppImage",
        ".iso",
        ".img",
    )
    offenders = [f for f in _tracked_files() if f.endswith(suffixes)]
    assert not offenders, f"third-party archives are tracked: {offenders}"


def test_no_files_tracked_from_root_reference_tree() -> None:
    offenders = [
        f for f in _tracked_files() if f.startswith("reference/") or f.startswith("vendor/")
    ]
    assert not offenders, f"third-party tree committed: {offenders}"


# --------------------------------------------------------------------------
# dispositions.md must stay internally consistent
#
# PARITY-POLICY.md requires that no unit is left unclassified, and the summary
# table claims to be derived from the index rather than hand-maintained. This
# asserts both, so the two cannot drift.
# --------------------------------------------------------------------------

DISPOSITIONS = REPO_ROOT / "docs" / "reference" / "dispositions.md"

_CODES = {
    "C": "CARRY",
    "S": "SUPERSEDE",
    "R": "REVIVE",
    "X": "RETIRE",
    "A": "ADD",
    "?": "NEEDS-DECISION",
    "M": "Reserved to maintainer",
}


# The index carries one bold sub-header per source, each naming its own count.
# The summary table has one column per source in the same order. Both are held
# to the index below, so a fifth source (or a sixth) needs only a row here.
_SOURCES = (
    ("AHRL", "**AHRL (105):**", 105),
    ("73Linux delta", "**73Linux delta (28):**", 28),
    ("Skywave delta", "**Skywave delta (9):**", 9),
    ("DragonOS Tier-1 — new units", "**DragonOS Tier-1 — new units (8):**", 8),
)


def _parse_index() -> dict[str, list[tuple[str, str]]]:
    """Each source's index sub-list, as {source: [(unit, code), ...]}.

    A sub-list is the single paragraph after its bold header — up to the next
    blank line, which stops it before the following header or an explanatory
    note. The note under the DragonOS list backticks names *without* a code, so
    bounding on the blank line keeps it out rather than tripping the parser.
    """
    import re

    text = DISPOSITIONS.read_text()
    parsed: dict[str, list[tuple[str, str]]] = {}
    for source, marker, _count in _SOURCES:
        assert marker in text, f"index is missing the {source!r} sub-header {marker!r}"
        # The header is followed by a blank line before the token paragraph;
        # strip that so the paragraph itself is what the blank-line split bounds.
        block = text.split(marker, 1)[1].lstrip("\n").split("\n\n", 1)[0]
        entries: list[tuple[str, str]] = []
        for part in block.split("·"):
            item = part.strip()
            if not item:
                continue
            m = re.search(r"`([A-Za-z0-9_.+\- ]+)`\s*([SRXCAM?])\s*$", item)
            assert m, f"unparseable {source} index entry: {item!r}"
            entries.append((m.group(1).strip(), m.group(2)))
        parsed[source] = entries
    return parsed


def _summary_counts() -> dict[str, tuple[int, ...]]:
    """Parse the per-source columns of the summary table into {disposition: (...)}.

    The row is ``| name | AHRL | 73Linux | Skywave | DragonOS | Total |`` — six
    cells. The per-source columns are all but the first (name) and last (total).
    """
    counts: dict[str, tuple[int, ...]] = {}
    expected_cells = 2 + len(_SOURCES)  # name + per-source columns + total
    for line in DISPOSITIONS.read_text().splitlines():
        if not line.startswith("| ") or line.startswith("| **Total"):
            continue
        cells = [c.strip().strip("*") for c in line.strip("|").split("|")]
        if len(cells) != expected_cells or cells[0] in {"Disposition", "---"}:
            continue
        if cells[0] not in _CODES.values():
            continue
        per_source = tuple(0 if c == "—" else int(c) for c in cells[1:-1])
        counts[cells[0]] = per_source
    return counts


def test_dispositions_index_totals() -> None:
    parsed = _parse_index()
    for source, _marker, count in _SOURCES:
        assert len(parsed[source]) == count, (
            f"expected {count} {source} units, found {len(parsed[source])}"
        )


def test_dispositions_no_duplicate_units() -> None:
    from collections import Counter

    for source, entries in _parse_index().items():
        dupes = [n for n, c in Counter(n for n, _ in entries).items() if c > 1]
        assert not dupes, f"{source} index has duplicates: {dupes}"


def test_dispositions_summary_matches_index() -> None:
    """The summary table claims to be derived from the index. Hold it to that,
    every source column against its own sub-list."""
    from collections import Counter

    parsed = _parse_index()
    per_source_counts = [Counter(code for _, code in parsed[s]) for s, _m, _c in _SOURCES]
    summary = _summary_counts()

    for code, name in _CODES.items():
        claimed = summary.get(name)
        assert claimed is not None, f"summary table missing row: {name}"
        actual = tuple(counter[code] for counter in per_source_counts)
        assert claimed == actual, f"{name}: summary says {claimed}, index has {actual}"


# ---------------------------------------------------------------------------
# The doc-link checker must actually scan docs/reference/
#
# The same unanchored-'reference' bug that hid docs/reference/ from git also hid
# it from scripts/check_doc_links.py, whose SKIP_DIRS was matched against every
# path component. Seven inventory documents were reported as "no broken internal
# references" because none of them was ever opened.
# ---------------------------------------------------------------------------


def test_link_checker_scans_docs_reference() -> None:
    """Regression: the checker's skip list must be root-anchored, like .gitignore."""
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "check_doc_links", REPO_ROOT / "scripts" / "check_doc_links.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    # The checker's own filter, not a copy of it.
    scanned = [str(p) for p in module.scanned_docs()]

    assert [p for p in scanned if p.startswith("docs/reference/")], (
        "scripts/check_doc_links.py skips the whole docs/reference/ tree. Its "
        "skip list must be anchored to the repo root, not matched against every "
        "path component — see CLAUDE.md Conventions."
    )
    assert not [p for p in scanned if p.startswith("reference/")], (
        "the gitignored root reference/ tree must stay out of the doc checker"
    )


# ---------------------------------------------------------------------------
# Every source package must be tracked
#
# `state/` in .gitignore was unanchored and therefore also matched
# src/hammunition/state/, which kept a whole source package out of git through
# an entire commit without any error. `reference/` did the same thing to
# docs/reference/ earlier. Rather than add a third named special case, this
# asserts the general property: if it is a Python package under src/ or tests/,
# git must be able to see it.
# ---------------------------------------------------------------------------


def _source_packages() -> list[str]:
    roots = [REPO_ROOT / "src", REPO_ROOT / "tests"]
    out: list[str] = []
    for root in roots:
        if not root.exists():
            continue
        for path in sorted(root.rglob("*.py")):
            if "__pycache__" in path.parts:
                continue
            out.append(str(path.relative_to(REPO_ROOT)))
    return out


def test_no_source_file_is_git_ignored() -> None:
    ignored = [p for p in _source_packages() if _is_ignored(p)]
    assert not ignored, (
        "these source files are git-ignored and would silently never be "
        f"committed: {ignored}. A .gitignore rule for build output or runtime "
        "state must be anchored to the repo root."
    )


def test_every_source_file_is_tracked() -> None:
    """Ignored or not, an untracked source file is a commit somebody forgot."""
    tracked = _tracked_files()
    missing = [p for p in _source_packages() if p not in tracked]
    assert not missing, f"source files exist but are not tracked by git: {missing}"


@pytest.mark.parametrize(
    "path",
    [
        "src/hammunition/state/log.py",
        "src/hammunition/consent/gate.py",
        "src/hammunition/manifest/schema.py",
    ],
)
def test_named_source_packages_are_not_ignored(path: str) -> None:
    """Spot checks with names, so a failure says which rule went wrong."""
    assert not _is_ignored(path), f"{path} is git-ignored"


@pytest.mark.parametrize("path", ["state/transactions.jsonl", "logs/run.log", "build/lib/x.py"])
def test_root_output_dirs_are_still_ignored(path: str) -> None:
    """Anchoring must not have stopped the rules doing their actual job."""
    assert _is_ignored(path), f"{path} should be git-ignored but is not"
