# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""Rules for software that displaces a distribution's choice.  D-022.

The first instance is an editor and feels minor. The pattern is not: it recurs
for dump1090-mutability against readsb, for vendor SDR drivers against the
distribution's, and for anything where upstream ships newer than the archive.
These assert the rule rather than the instance.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from hammunition.manifest.load import load_catalog
from hammunition.manifest.schema import PackageManifest

CATALOG = Path(__file__).resolve().parent.parent / "catalog" / "packages"
FINGERPRINT = re.compile(r"^[0-9A-F]{40}$")


@pytest.fixture(scope="module")
def catalog() -> dict[str, PackageManifest]:
    return load_catalog(CATALOG)


def _with_repos(catalog: dict[str, PackageManifest]) -> list[PackageManifest]:
    return [m for m in catalog.values() if m.apt_repos]


def test_third_party_repos_pin_a_full_fingerprint(catalog: dict[str, PackageManifest]) -> None:
    """A short key id is forgeable. Pin all forty hex digits."""
    for manifest in _with_repos(catalog):
        for repo in manifest.apt_repos:
            assert FINGERPRINT.match(repo.key_fingerprint), (
                f"{manifest.name}: repo {repo.name!r} fingerprint "
                f"{repo.key_fingerprint!r} is not 40 uppercase hex digits"
            )


def test_third_party_repos_explain_the_scope_of_what_is_granted(
    catalog: dict[str, PackageManifest],
) -> None:
    """D-022: adding a vendor repo is larger than installing one package.

    The rationale is shown to the operator before the repo is added, so it has
    to say what is actually being granted, not just name a URL.
    """
    for manifest in _with_repos(catalog):
        for repo in manifest.apt_repos:
            assert len(repo.rationale) >= 100, (
                f"{manifest.name}: repo {repo.name!r} rationale is too short to "
                f"have disclosed anything"
            )
            assert "update" in repo.rationale.lower(), (
                f"{manifest.name}: repo {repo.name!r} rationale must say the "
                f"vendor gains the ability to ship updates"
            )


def test_packages_adding_a_repo_are_never_a_default(
    catalog: dict[str, PackageManifest],
) -> None:
    """D-022 rule 5: opt-in, and not in any getting-started profile."""
    for manifest in _with_repos(catalog):
        assert manifest.recommended_default is False, (
            f"{manifest.name} adds a third-party repository and must not be a recommended default"
        )


def test_adding_a_repo_is_a_declared_reversible_modification(
    catalog: dict[str, PackageManifest],
) -> None:
    """Rule 2: never silently, and reversible with a stated command."""
    for manifest in _with_repos(catalog):
        mods = [m for m in manifest.system_modifications if m.kind == "apt_pin"]
        assert mods, f"{manifest.name} adds a repo but declares no system_modification"
        for mod in mods:
            assert mod.reversible, f"{manifest.name}: adding a repo must be reversible"
            assert mod.reverse_hint and "rm " in mod.reverse_hint, (
                f"{manifest.name}: reverse_hint must give the actual command"
            )


def test_displacement_never_purges(catalog: dict[str, PackageManifest]) -> None:
    """Rule 1: coexistence is the default.

    AHRL removes the distribution's librtlsdr with no record. Nothing in this
    catalog purges a distribution package as a side effect of installing
    something else.
    """
    for manifest in catalog.values():
        purges = [m for m in manifest.system_modifications if m.kind == "package_purge"]
        assert not purges, (
            f"{manifest.name} purges a package as part of installing. D-022: "
            f"removal is a separate act the operator asks for."
        )


def test_the_vscode_instance_documents_both_sides(catalog: dict[str, PackageManifest]) -> None:
    """Rule 4: state the distribution's reasoning as a reason, not an obstacle."""
    manifest = catalog["code"]
    problems = (manifest.documentation.known_problems or "").lower()
    for phrase in ("proprietary", "telemetry", "vscodium"):
        assert phrase in problems, f"the trade-off must name {phrase!r}"
    why = manifest.documentation.why_you_want_it.lower()
    assert "marketplace" in why, "the functional counter-argument must be stated"


def test_the_vscode_instance_does_not_remove_vscodium(
    catalog: dict[str, PackageManifest],
) -> None:
    manifest = catalog["code"]
    assert "codium" not in manifest.conflicts_with_repo_package
    assert "codium" not in " ".join(m.detail for m in manifest.system_modifications).lower()
