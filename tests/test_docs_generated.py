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
    return gen.render(catalog, vocabulary)  # type: ignore[attr-defined]


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
