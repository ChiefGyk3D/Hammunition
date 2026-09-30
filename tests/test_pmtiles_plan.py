# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""The tilemaker floor at plan time.  D-071.

tilemaker 3.0 is the first to write PMTiles; Ubuntu 24.04 carries 2.4.0. The
plan reads the version the run will have -- installed, else the archive's
candidate -- from the apt probe it already makes, the way D-037 reads Node's.
Below the floor ``osm-pmtiles`` is deferred from a profile (D-039) and
refused when typed; nothing is built or fetched to meet it.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from hammunition.backends import AptBackend, AptPackageState, RecordingRunner
from hammunition.distro import Target
from hammunition.manifest.schema import PackageManifest, ProfileManifest
from hammunition.plan import PlanError, resolve
from hammunition.station import Station
from test_pmtiles import manifest as tiles_manifest

TARGET = Target(distro="ubuntu", version="24.04", arch="x86_64")
DOC = {
    "what_it_does": "A unit for a test, nothing more.",
    "why_you_want_it": "Because the test suite needs a manifest.",
    "upstream_url": "https://example.org/",
}


def _unit(name: str, install: dict[str, Any]) -> PackageManifest:
    return PackageManifest.model_validate(
        {
            "name": name,
            "version": "1",
            "summary": f"{name} for a test",
            "categories": ["navigation-maps"],
            "install": [{"install": install}],
            "update": {"probe": {"method": "none"}},
            "documentation": DOC,
        }
    )


REGIONS = _unit(
    "osm-regions",
    {
        "method": "osm-regions",
        "licence": "ODbL-1.0",
        "licence_url": "https://www.openstreetmap.org/copyright",
    },
)
KIT = _unit(
    "vector-map-kit",
    {
        "method": "data",
        "artifacts": [
            {"url": "https://x/k.json", "sha256": "a" * 64, "size": 2, "install_as": "k.json"}
        ],
        "licence": "various",
        "licence_url": "https://example.org/",
    },
)
GPSD = _unit("gpsd", {"method": "apt", "packages": ["gpsd"]})
CATALOG = {m.name: m for m in (tiles_manifest(), REGIONS, KIT, GPSD)}
PROFILE = ProfileManifest.model_validate(
    {
        "name": "navigation",
        "summary": "A profile for a test",
        "packages": ["gpsd", "osm-regions", "vector-map-kit", "osm-pmtiles"],
        "documentation": {
            "what_it_installs": "Everything a test needs to see a deferral.",
            "why_together": "Because the test needs a profile around the unit.",
            "deliberately_excludes": "Everything else.",
            "manual_configuration": "Nothing at all here.",
        },
    }
)
STATION = Station(map_regions=("north-america/us/vermont",))


def _apt(tmp_path: Path, tilemaker: AptPackageState | None) -> AptBackend:
    lists = tmp_path / "lists"
    lists.mkdir(exist_ok=True)
    (lists / "example.invalid_dists_noble_main_binary-amd64_Packages").touch()

    class Apt(AptBackend):
        def probe(self, packages: Any) -> Any:
            states = {
                name: AptPackageState(name=name, installed=None, candidate="1.0")
                for name in packages
                if name != "tilemaker"
            }
            if tilemaker is not None and "tilemaker" in packages:
                states["tilemaker"] = tilemaker
            return states

    return Apt(RecordingRunner(), lists_dir=lists)


def _plan(tmp_path: Path, names: list[str], tilemaker: AptPackageState | None) -> Any:
    return resolve(
        names,
        catalog=CATALOG,
        profiles={"navigation": PROFILE},
        target=TARGET,
        apt=_apt(tmp_path, tilemaker),
        user="operator",
        station=STATION,
    )


def _state(candidate: str, installed: str | None = None) -> AptPackageState:
    return AptPackageState("tilemaker", installed=installed, candidate=candidate)


def test_ubuntu_24_04_s_tilemaker_defers_the_unit_from_a_profile_by_name(tmp_path: Path) -> None:
    plan = _plan(tmp_path, ["navigation"], _state("2.4.0-1build3"))
    names = {p.name for p in plan.packages}
    assert "osm-pmtiles" not in names and {"gpsd", "osm-regions", "vector-map-kit"} <= names
    [deferral] = [d for d in plan.deferrals if d.subject == "osm-pmtiles"]
    assert "tilemaker 3.0 or newer" in deferral.why and "writes PMTiles" in deferral.why
    assert "2.4.0-1build3" in deferral.why and "the archive's candidate" in deferral.why


def test_typed_by_name_it_is_refused_with_the_same_reason(tmp_path: Path) -> None:
    with pytest.raises(PlanError) as exc:
        _plan(tmp_path, ["osm-pmtiles"], _state("2.4.0-1build3"))
    text = str(exc.value)
    assert "tilemaker 3.0 or newer" in text and "2.4.0-1build3" in text
    assert "D-071" in text


def test_the_archive_s_3_0_0_passes_and_an_installed_newer_one_counts(tmp_path: Path) -> None:
    plan = _plan(tmp_path, ["osm-pmtiles"], _state("3.0.0-1"))
    assert "osm-pmtiles" in {p.name for p in plan.packages}
    plan = _plan(tmp_path, ["osm-pmtiles"], _state("2.4.0-1", installed="3.2.0-1"))
    assert "osm-pmtiles" in {p.name for p in plan.packages}


def test_an_installed_old_one_counts_over_a_newer_candidate(tmp_path: Path) -> None:
    """As D-037 reads Node: the installed version is the one that counts."""
    with pytest.raises(PlanError, match=r"2\.4\.0-1"):
        _plan(tmp_path, ["osm-pmtiles"], _state("3.0.0-1", installed="2.4.0-1"))


def test_no_tilemaker_at_all_is_one_refusal_the_apt_check_s(tmp_path: Path) -> None:
    """A depends line the archive lacks is the manifest's defect (D-039); the
    floor does not name the same cause a second time."""
    with pytest.raises(PlanError) as exc:
        _plan(tmp_path, ["osm-pmtiles"], None)
    text = str(exc.value)
    assert "no candidate for tilemaker" in text
    assert "tilemaker 3.0 or newer" not in text
