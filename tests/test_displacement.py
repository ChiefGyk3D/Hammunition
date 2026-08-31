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
from typing import Any

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


# ---------------------------------------------------------------------------
# The consumer for conflicts_with_repo_package (2026-08-30): the split is
# decided by method — a vendor .deb collides at the dpkg level and is refused
# at plan time; a source build shadows on PATH and is disclosed.
# ---------------------------------------------------------------------------


def _conflicting_manifest(method_block: dict[str, Any]) -> PackageManifest:

    base: dict[str, Any] = {
        "name": "clasher",
        "version": "1.0",
        "summary": "Fixture that declares a repo conflict",
        "categories": ["digital-modes"],
        "conflicts_with_repo_package": ["distro-owned"],
        "install": [{"install": method_block}],
        "update": {"probe": {"method": "none"}, "strategy": "manual"},
        "documentation": {
            "what_it_does": "Exists so the conflict consumer has a unit.",
            "why_you_want_it": "You do not; the suite does.",
            "upstream_url": "https://example.invalid/",
        },
    }
    return PackageManifest.model_validate(base)


def _plan_with_conflict(tmp_path: Path, method_block: dict[str, Any], installed: bool) -> Any:

    from hammunition.distro import Target
    from hammunition.plan import resolve
    from test_plan import _apt  # reuse the fake-apt helper

    manifest = _conflicting_manifest(method_block)
    known = {"distro-owned": "1.0" if installed else None, "clasher": None, "git": None}
    apt = _apt(tmp_path, known)
    return resolve(
        ["clasher"],
        catalog={"clasher": manifest},
        profiles={},
        target=Target(distro="debian", version="13", arch="x86_64"),
        apt=apt,
        user="op",
    )


DEB_BLOCK: dict[str, Any] = {
    "method": "binary",
    "artifact": {"url": "https://example.org/x.deb", "sha256": "0" * 64},
    "format": "deb",
    "deb_package": "vendor-unit",
}
GIT_BLOCK: dict[str, Any] = {
    "method": "git",
    "repo": "https://example.org/x",
    "ref": "1.0",
    "build_system": "make",
}


def test_a_vendor_deb_conflicting_with_an_installed_package_is_refused(tmp_path: Path) -> None:
    import pytest as _pytest

    from hammunition.plan import PlanError

    with _pytest.raises(PlanError, match="collides with installed distribution"):
        _plan_with_conflict(tmp_path, DEB_BLOCK, installed=True)


def test_a_source_build_shadowing_an_installed_package_is_disclosed_not_refused(
    tmp_path: Path,
) -> None:
    plan = _plan_with_conflict(tmp_path, GIT_BLOCK, installed=True)
    assert plan.packages[0].displaces == ("distro-owned",)


def test_an_uninstalled_conflict_is_silent(tmp_path: Path) -> None:
    plan = _plan_with_conflict(tmp_path, DEB_BLOCK, installed=False)
    assert plan.packages[0].displaces == ()
