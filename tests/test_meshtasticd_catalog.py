# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""`meshtasticd` from the Meshtastic project's repositories.  D-040, issue #308.

No distribution carries it. Five repository declarations, one per kind of
target, each pinning a key whose fingerprint was computed from the published
key with `src/hammunition/openpgp.py` on 2026-10-05. These tests hold the shape
those measurements gave: which target gets which repository (exactly one, or
none), that the OBS repositories are the flat shape (`Suites: ./`) and the PPA
ones are not, that the pinned fingerprints are the measured ones, and that the
package's udev rule and boot service are disclosed in the plan, which the
engine does not perform and dpkg does.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from hammunition.backends import AptRepoBackend
from hammunition.backends.apt_repo import render_sources
from hammunition.distro import Target
from hammunition.manifest.load import load_catalog
from hammunition.manifest.schema import PackageManifest
from hammunition.plan import resolve

from test_plan import _apt  # isort: skip

ROOT = Path(__file__).resolve().parent.parent
CATALOG = load_catalog(ROOT / "catalog" / "packages")
UNIT: PackageManifest = CATALOG["meshtasticd"]

#: Read from the published keys on 2026-10-05 (docs/reference/mesh-inventory.md).
OBS_FPR = "426AA6B0285C2096B70D9FC2528423A469A77D9A"
PPA_FPR = "5E0A0F83F3DDE7AC55915B14F40C93FFA2CD17E3"

#: (distro, version) -> the one repository that applies, per the measured table.
EXPECTED = {
    ("debian", "13"): "meshtastic-obs-debian13",
    ("parrot", "7.3"): "meshtastic-obs-parrot",
    ("parrot", "7.4"): "meshtastic-obs-parrot",
    ("kali", "2026.3"): "meshtastic-obs-kali",
    ("ubuntu", "24.04"): "meshtastic-ppa-noble",
    ("linuxmint", "22.3"): "meshtastic-ppa-noble",
    ("ubuntu", "26.04"): "meshtastic-ppa-resolute",
}


@pytest.mark.parametrize(("target", "name"), sorted(EXPECTED.items()))
def test_every_supported_target_gets_exactly_one_repository(
    target: tuple[str, str], name: str
) -> None:
    applicable = UNIT.apt_repos_for(target[0], target[1], "x86_64")
    assert [r.name for r in applicable] == [name]


@pytest.mark.parametrize(
    "target", [("debian", "12"), ("ubuntu", "22.04"), ("fedora", "42"), ("linuxmint", "21.3")]
)
def test_an_unsupported_target_gets_no_repository(target: tuple[str, str]) -> None:
    """Debian 12 has an OBS build and Ubuntu 22.04 a PPA series, but D-084 does
    not support either release, so none is declared (D-039 defers the unit)."""
    assert UNIT.apt_repos_for(target[0], target[1], "x86_64") == []


def test_the_pinned_fingerprints_are_the_measured_ones() -> None:
    by_name = {r.name: r.key_fingerprint for r in UNIT.apt_repos}
    assert {n: f for n, f in by_name.items() if "obs" in n} == dict.fromkeys(
        ("meshtastic-obs-debian13", "meshtastic-obs-parrot", "meshtastic-obs-kali"), OBS_FPR
    )
    assert {n: f for n, f in by_name.items() if "ppa" in n} == dict.fromkeys(
        ("meshtastic-ppa-noble", "meshtastic-ppa-resolute"), PPA_FPR
    )


def test_obs_repositories_are_flat_and_ppa_repositories_are_not() -> None:
    for repo in UNIT.apt_repos:
        if "obs" in repo.name:
            assert repo.suites == ["./"] and repo.components == [], repo.name
            assert repo.uri.endswith("/"), repo.name
            assert repo.uri.startswith("https://download.opensuse.org/repositories/"), repo.name
            rendered = render_sources(repo, Path("/etc/apt/keyrings/x.gpg"), unit="meshtasticd")
            assert "Suites: ./\n" in rendered and "Components" not in rendered
        else:
            assert repo.components == ["main"], repo.name
            assert repo.uri == "https://ppa.launchpadcontent.net/meshtastic/beta/ubuntu"


def test_the_keys_are_fetched_over_https_from_the_publisher() -> None:
    for repo in UNIT.apt_repos:
        assert repo.key_url.startswith("https://"), repo.name
        host = repo.key_url.split("/")[2]
        assert host in {"download.opensuse.org", "keyserver.ubuntu.com"}, repo.name


def test_the_obs_rationale_says_the_key_is_the_whole_projects_and_expires() -> None:
    rationale = next(r for r in UNIT.apt_repos if r.name == "meshtastic-obs-debian13").rationale
    assert "2027-08-26" in rationale
    assert "network OBS Project" in rationale
    assert "flat" in rationale


def test_the_package_effects_are_disclosed_as_modifications() -> None:
    kinds = {m.kind for m in UNIT.system_modifications}
    assert {"apt_pin", "package_service", "package_udev_rule", "package_account"} <= kinds
    udev = next(m for m in UNIT.system_modifications if m.kind == "package_udev_rule")
    assert "1a86:5512" in udev.description and "0666" in udev.description
    service = next(m for m in UNIT.system_modifications if m.kind == "package_service")
    assert "meshtasticd.service" in service.description and "boot" in service.description


def test_the_plan_prints_the_udev_rule_and_the_service_before_the_confirmation(
    tmp_path: Path,
) -> None:
    """`package_*` modifications are performed by dpkg, not the engine; the plan
    still has to say them (a world-writable udev line is the kind of thing a
    dry run that omitted it would make approximate)."""
    target = Target(distro="debian", version="13", arch="x86_64")
    repos = AptRepoBackend(
        cache_dir=tmp_path / "cache",
        staging_dir=tmp_path / "staging",
        sources_dir=tmp_path / "sources.list.d",
        keyrings_dir=tmp_path / "keyrings",
    )
    plan = resolve(
        ["meshtasticd"],
        catalog=CATALOG,
        profiles={},
        target=target,
        apt=_apt(tmp_path, {}),
        user="operator",
        repos=repos,
    )
    text = "\n".join(plan.notes)
    assert "60-meshtasticd.rules" in text and "0666" in text
    assert "meshtasticd.service" in text
    assert "system user and group `meshtasticd`" in text
    assert [a.repo.name for a in plan.apt_repos] == ["meshtastic-obs-debian13"]


def test_the_unit_is_in_the_mesh_profile_only_and_no_default() -> None:
    from hammunition.manifest.load import load_profiles

    profiles = load_profiles(ROOT / "catalog" / "profiles", CATALOG)
    holders = [n for n, p in profiles.items() if "meshtasticd" in p.packages]
    assert holders == ["mesh"]
    assert UNIT.recommended_default is False
