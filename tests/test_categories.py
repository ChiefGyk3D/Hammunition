# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""The category vocabulary is controlled, and both directions are enforced.

Categories are D-003's flat tags. Nothing in the engine validates them, which
is how the catalog came to carry `satdump` under `satellite` and `noaa-apt`
under `satellites`: a query for either returned half the satellite software and
reported it as all of it. No test failed, no manifest was malformed, and the
answer was silently wrong -- the shape of defect this repository keeps writing
checks against.

`catalog/categories.yaml` is the vocabulary. This module enforces:

* **No undeclared tag.** A manifest may not invent one, so the drift above
  cannot recur.
* **No unused tag.** The vocabulary may not accumulate names nothing carries,
  which is what keeps the file short enough to actually read before adding a
  tag -- the mechanism that would have caught `satellites` by eye.
* **No singular/plural pair.** The specific collision that happened, made
  unrepresentable rather than merely fixed.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from hammunition.manifest.load import load_catalog  # noqa: E402
from hammunition.manifest.schema import PackageManifest  # noqa: E402

VOCABULARY = REPO_ROOT / "catalog" / "categories.yaml"
CATALOG = REPO_ROOT / "catalog" / "packages"


@pytest.fixture(scope="module")
def declared() -> dict[str, str]:
    data = yaml.safe_load(VOCABULARY.read_text())
    return {c["name"]: c["summary"] for c in data["categories"]}


@pytest.fixture(scope="module")
def catalog() -> dict[str, PackageManifest]:
    return load_catalog(CATALOG)


def test_the_vocabulary_is_not_empty(declared: dict[str, str]) -> None:
    """Guards the guard: a file that failed to parse into an empty mapping
    would make every check below vacuously pass."""
    assert len(declared) >= 15


def test_no_manifest_uses_an_undeclared_category(
    declared: dict[str, str], catalog: dict[str, PackageManifest]
) -> None:
    unknown: dict[str, set[str]] = {}
    for name, manifest in catalog.items():
        extra = set(manifest.categories) - set(declared)
        if extra:
            unknown[name] = extra
    assert not unknown, (
        "undeclared categories: "
        + "; ".join(f"{k} -> {sorted(v)}" for k, v in sorted(unknown.items()))
        + f"\nAdd them to {VOCABULARY.relative_to(REPO_ROOT)} with a summary, or use "
        "an existing tag."
    )


def test_no_declared_category_goes_unused(
    declared: dict[str, str], catalog: dict[str, PackageManifest]
) -> None:
    """A vocabulary nobody has to read is a vocabulary nobody reads."""
    used = {c for m in catalog.values() for c in m.categories}
    dead = sorted(set(declared) - used)
    assert not dead, (
        f"declared but carried by no manifest: {dead}. Remove them, or add the "
        "manifest that needed them in the same commit."
    )


def test_no_category_is_another_ones_plural(declared: dict[str, str]) -> None:
    """The collision that actually happened, made unrepresentable."""
    names = set(declared)
    pairs = sorted((n, n + "s") for n in names if n + "s" in names)
    assert not pairs, f"singular/plural pairs are the same tag twice: {pairs}"


def test_every_category_has_a_real_summary(declared: dict[str, str]) -> None:
    thin = sorted(n for n, s in declared.items() if len(s.split()) < 4)
    assert not thin, f"these say nothing a reader could act on: {thin}"


def test_every_manifest_carries_at_least_one_category(
    catalog: dict[str, PackageManifest],
) -> None:
    """The schema enforces min_length=1; this asserts it against the real
    catalog rather than against a constructed manifest."""
    assert all(m.categories for m in catalog.values())
