# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""The shipped vector-tile units and their place in ``navigation``.  D-071.

The pins are the digests measured on 2026-09-30 by downloading each file once;
each is asserted here so a changed manifest is a visible change. Nothing is
downloaded by the suite.
"""

from __future__ import annotations

from pathlib import Path

from hammunition.backends.pmtiles import CONFIG, LANDCOVER, OCEAN, PROCESS, SHAPE_PARTS
from hammunition.manifest.load import load_catalog, load_profiles
from hammunition.manifest.schema import DataInstall, DerivedDataInstall

CATALOG = Path(__file__).resolve().parent.parent / "catalog"


def _kit() -> DataInstall:
    block = load_catalog(CATALOG / "packages")["vector-map-kit"].install[0].install
    assert isinstance(block, DataInstall)
    return block


def test_osm_pmtiles_is_derived_from_the_regions_with_the_kit_and_the_archive_s_tools() -> None:
    m = load_catalog(CATALOG / "packages")["osm-pmtiles"]
    block = m.install[0].install
    assert isinstance(block, DerivedDataInstall)
    assert (block.converter, block.source, block.kit) == (
        "tilemaker-pmtiles",
        "osm-regions",
        "vector-map-kit",
    )
    assert m.depends == ["osm-regions", "vector-map-kit", "tilemaker", "gdal-bin"]
    assert block.licence == "ODbL-1.0"


def test_the_kit_s_pins_are_the_measured_digests() -> None:
    by_url = {a.url.rsplit("/", 1)[-1]: a for a in _kit().artifacts}
    assert by_url["tilemaker_3.0.0.orig.tar.gz"].sha256.startswith("eff9ba9e0a3f")
    assert by_url["tilemaker_3.0.0.orig.tar.gz"].size == 43679032
    assert by_url["dist.zip"].sha256 == (
        "45d010b7cc590b471982395390a51eb6d57d0813de37090ea6e744fccf28f4de"
    )
    assert "v6.11.2" in by_url["dist.zip"].url
    assert by_url["pmtiles-4.5.0.tgz"].sha256.startswith("23ae7c575578")
    assert by_url["ne_10m_ocean.shp"].sha256.startswith("bb5ae1e0922b")
    assert "f1890d9f152c896d250a77557a5751a93d494776" in by_url["ne_10m_ocean.shp"].url


def test_the_kit_carries_every_file_the_converter_reads() -> None:
    kit = _kit()
    files = {a.install_as for a in kit.artifacts if a.install_as}
    assert {f"{layer}.{part}" for layer in (OCEAN, *LANDCOVER) for part in SHAPE_PARTS} <= files
    tilemaker = next(a for a in kit.artifacts if a.into == "tilemaker")
    members = {m.removeprefix("tilemaker-3.0.0/") for m in tilemaker.members or ()}
    assert {str(CONFIG).removeprefix("tilemaker/"), str(PROCESS).removeprefix("tilemaker/")} <= (
        members
    )


def test_no_water_polygons_from_osmdata_are_pinned() -> None:
    """They are rebuilt daily with no checksum (D-071): a pin would die in a day."""
    assert not [a for a in _kit().artifacts if "osmdata.openstreetmap.de" in a.url]


def test_the_kit_states_the_credit_the_licence_requires() -> None:
    assert "© OpenMapTiles © OpenStreetMap contributors" in _kit().licence
    for licence in ("FTWPL", "CC-BY-4.0", "BSD-3-Clause", "OFL-1.1", "public domain"):
        assert licence in _kit().licence


def test_navigation_carries_the_kit_and_the_tiles() -> None:
    profile = load_profiles(CATALOG / "profiles")["navigation"]
    assert {"vector-map-kit", "osm-pmtiles", "gdal-bin", "osm-regions"} <= set(profile.packages)
