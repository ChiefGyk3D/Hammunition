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
        ".tar", ".tar.gz", ".tgz", ".tar.bz2", ".tar.xz", ".zip",
        ".deb", ".rpm", ".whl", ".AppImage", ".iso", ".img",
    )
    offenders = [f for f in _tracked_files() if f.endswith(suffixes)]
    assert not offenders, f"third-party archives are tracked: {offenders}"


def test_no_files_tracked_from_root_reference_tree() -> None:
    offenders = [
        f for f in _tracked_files()
        if f.startswith("reference/") or f.startswith("vendor/")
    ]
    assert not offenders, f"third-party tree committed: {offenders}"
