# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""The phone units and their profile, as the catalog carries them.  D-067."""

from __future__ import annotations

from pathlib import Path

from hammunition.manifest.load import load_catalog, load_profiles
from hammunition.manifest.schema import DerivedDataInstall

CATALOG = Path(__file__).resolve().parent.parent / "catalog"
POI_SHA = "85dd23488511f51a710139dffc8c622d184ea93e817c4ec27dde1c222b7432a7"


def test_both_units_are_derived_from_the_regions_with_the_archive_s_osmosis() -> None:
    catalog = load_catalog(CATALOG / "packages")
    for name in ("mapsforge-map", "mapsforge-poi"):
        m = catalog[name]
        block = m.install[0].install
        assert isinstance(block, DerivedDataInstall)
        assert block.converter == name and block.source == "osm-regions"
        assert set(m.depends) == {"osm-regions", "osmosis", "libmapsforge-java"}


def test_the_poi_writer_is_pinned_to_the_measured_digest() -> None:
    block = load_catalog(CATALOG / "packages")["mapsforge-poi"].install[0].install
    assert isinstance(block, DerivedDataInstall) and block.tool is not None
    assert block.tool.artifact.sha256 == POI_SHA
    assert block.tool.size == 18827962
    assert block.tool.artifact.url.startswith("https://repo1.maven.org/maven2/org/mapsforge/")
    assert block.tool.artifact.signature_url == block.tool.artifact.url + ".asc"


def test_phone_maps_is_its_own_post_1_0_profile_and_navigation_is_unchanged() -> None:
    profiles = load_profiles(CATALOG / "profiles")
    phone = profiles["phone-maps"]
    assert phone.stage == "post-1.0"
    assert list(phone.packages) == ["osm-regions", "mapsforge-map", "mapsforge-poi"]
    assert not {"mapsforge-map", "mapsforge-poi"} & set(profiles["navigation"].packages)
