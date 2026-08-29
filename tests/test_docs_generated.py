# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""Generated documentation is generated, and regenerating it is a no-op.

CLAUDE.md: "Generated docs are generated... Never hand-edit a generated file."
That rule needs a check behind it or it is a comment. The failure it prevents
is quiet: a reference page edited by hand reads correctly, passes the link
checker, and is silently reverted the next time anyone runs the generator --
so the correction is lost and nobody learns it was.

The check is the cheap one that actually works: render into memory, compare
against what is on disk. It also catches the commoner case, which is not a
hand edit at all but a manifest changed without regenerating.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from hammunition.manifest.load import load_catalog  # noqa: E402

PACKAGES = REPO_ROOT / "docs" / "packages"
GENERATOR = REPO_ROOT / "scripts" / "gen_package_reference.py"


def _generator() -> object:
    spec = importlib.util.spec_from_file_location("gen_package_reference", GENERATOR)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def rendered() -> dict[str, str]:
    gen = _generator()
    catalog = load_catalog(REPO_ROOT / "catalog" / "packages")
    vocabulary = {
        c["name"]: c["summary"]
        for c in yaml.safe_load((REPO_ROOT / "catalog" / "categories.yaml").read_text())[
            "categories"
        ]
    }
    rendered: dict[str, str] = gen.render(catalog, vocabulary)  # type: ignore[attr-defined]
    return rendered


def test_there_is_something_to_compare(rendered: dict[str, str]) -> None:
    """Guards the guard: an empty render would make every check below pass."""
    assert len(rendered) > 100
    assert "index.md" in rendered


def test_every_manifest_has_a_generated_page(rendered: dict[str, str]) -> None:
    catalog = load_catalog(REPO_ROOT / "catalog" / "packages")
    missing = sorted(name for name in catalog if f"{name}.md" not in rendered)
    assert not missing, f"no generated page for: {missing}"


def test_regenerating_is_a_no_op(rendered: dict[str, str]) -> None:
    on_disk = {p.name: p.read_text() for p in PACKAGES.glob("*.md")}
    stale = sorted(set(on_disk) - set(rendered))
    absent = sorted(set(rendered) - set(on_disk))
    changed = sorted(n for n in set(rendered) & set(on_disk) if rendered[n] != on_disk[n])
    assert not (stale or absent or changed), (
        "docs/packages/ is out of date — run scripts/gen_package_reference.py.\n"
        f"  pages for packages that no longer exist: {stale[:6]}\n"
        f"  packages with no page: {absent[:6]}\n"
        f"  pages whose manifest changed: {changed[:6]}"
    )


def test_generated_pages_say_they_are_generated() -> None:
    """So that someone opening one to fix a typo is told where to fix it."""
    unmarked = [
        p.name
        for p in PACKAGES.glob("*.md")
        if "gen_package_reference.py" not in p.read_text().split("\n")[0]
    ]
    assert not unmarked, f"generated pages with no generated-by line: {unmarked[:6]}"


# ---------------------------------------------------------------------------
# The capability matrix
#
# Its generator reads a measured apt sweep from the gitignored reference/probes
# tree, so a full regeneration check cannot run in CI. Two checks instead: the
# part that needs no probe runs everywhere, and the full no-op runs where the
# sweep exists. This is the same shape the programmer-class generator already
# uses, for the same reason.
# ---------------------------------------------------------------------------

MATRIX = REPO_ROOT / "docs" / "reference" / "capability-matrix.md"
PROBES = REPO_ROOT / "reference" / "probes"


def test_the_matrix_lists_every_manifest() -> None:
    """Runs everywhere, needs no probe, and catches the common staleness:
    a manifest added and the matrix not regenerated."""
    text = MATRIX.read_text()
    catalog = load_catalog(REPO_ROOT / "catalog" / "packages")
    missing = sorted(name for name in catalog if f"| `{name}` |" not in text)
    assert not missing, (
        f"{len(missing)} manifest(s) absent from the capability matrix — "
        f"run scripts/gen_capability_matrix.py: {missing[:8]}"
    )


def test_the_matrix_lists_no_package_that_left_the_catalog() -> None:
    import re

    catalog = load_catalog(REPO_ROOT / "catalog" / "packages")
    # Only the full table at the end. The legend above it uses the same row
    # shape to explain what `apt` means, and matching that reported `apt` as a
    # package the catalog had lost -- a check failing on its own documentation.
    _, _, table = MATRIX.read_text().partition("## Every manifest")
    listed = set(re.findall(r"^\| `([a-z0-9][a-z0-9.+-]*)` \|", table, re.M))
    assert listed, "found no package rows; the section heading must have changed"
    stale = sorted(listed - set(catalog))
    assert not stale, f"matrix names packages the catalog no longer has: {stale}"


@pytest.mark.skipif(
    not list(PROBES.glob("policy-cat-*.tsv")),
    reason="needs the apt sweep in reference/probes/ — see the generator's docstring",
)
def test_regenerating_the_matrix_is_a_no_op() -> None:
    import subprocess

    before = MATRIX.read_text()
    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "gen_capability_matrix.py")],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        check=False,
    )
    after = MATRIX.read_text()
    if before != after:
        MATRIX.write_text(before)
    assert result.returncode == 0, result.stderr

    def without_date(text: str) -> list[str]:
        return [ln for ln in text.splitlines() if not ln.startswith("**Generated:**")]

    assert without_date(before) == without_date(after), (
        "docs/reference/capability-matrix.md is stale — regenerate it. If the "
        "sweep has moved, that is the point: the matrix is a measurement."
    )
