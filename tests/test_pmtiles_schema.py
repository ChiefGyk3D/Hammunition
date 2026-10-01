# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""The ``tilemaker-pmtiles`` converter in the schema.  D-071.

It reads two units: the regions (``source``) and the kit holding tilemaker's
OpenMapTiles profile and the Natural Earth layers (``kit``). Both must be in
``depends``, the kit must be a ``data`` unit, and ``kit`` means nothing to
any other converter.
"""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from hammunition.manifest.schema import (
    CONVERTER_SOURCE_METHOD,
    DerivedDataInstall,
    PackageManifest,
    derived_source_method_problem,
)


def _manifest(block: dict[str, Any], depends: list[str] | None = None) -> PackageManifest:
    return PackageManifest.model_validate(
        {
            "name": "osm-pmtiles",
            "version": "station",
            "summary": "Vector tiles for a test",
            "categories": ["navigation-maps"],
            "depends": depends if depends is not None else ["osm-regions", "vector-map-kit"],
            "install": [{"install": block}],
            "update": {"probe": {"method": "none"}},
            "documentation": {
                "what_it_does": "Vector tiles for a test, nothing more.",
                "why_you_want_it": "Because the test suite needs a manifest.",
                "upstream_url": "https://github.com/systemed/tilemaker",
            },
        }
    )


def _block(**extra: Any) -> dict[str, Any]:
    return {
        "method": "derived",
        "converter": "tilemaker-pmtiles",
        "source": "osm-regions",
        "licence": "ODbL-1.0",
        "licence_url": "https://www.openstreetmap.org/copyright",
        **extra,
    }


def test_the_converter_reads_regions_and_a_kit() -> None:
    assert CONVERTER_SOURCE_METHOD["tilemaker-pmtiles"] == "osm-regions"
    m = _manifest(_block(kit="vector-map-kit"))
    block = m.install[0].install
    assert isinstance(block, DerivedDataInstall)
    assert block.inputs() == ("osm-regions", "vector-map-kit")


def test_the_kit_is_required_and_must_be_in_depends() -> None:
    with pytest.raises(ValidationError, match="kit"):
        _manifest(_block())
    with pytest.raises(ValidationError, match="vector-map-kit"):
        _manifest(_block(kit="vector-map-kit"), depends=["osm-regions"])


def test_no_other_converter_takes_a_kit() -> None:
    with pytest.raises(ValidationError, match="kit is read only by the tilemaker-pmtiles"):
        _manifest(_block(converter="mapsforge-map", kit="vector-map-kit"))


def test_brouter_s_inputs_are_still_refused_on_this_converter() -> None:
    with pytest.raises(ValidationError, match="brouter-mapcreator"):
        _manifest(_block(kit="vector-map-kit", program="brouter"), depends=None)


def test_the_kit_must_be_a_data_unit_catalog_wide() -> None:
    m = _manifest(_block(kit="vector-map-kit"))
    regions = PackageManifest.model_validate(
        {
            "name": "osm-regions",
            "version": "station",
            "summary": "Regions for a test",
            "categories": ["navigation-maps"],
            "install": [
                {
                    "install": {
                        "method": "osm-regions",
                        "provider": "geofabrik",
                        "licence": "ODbL-1.0",
                        "licence_url": "https://www.openstreetmap.org/copyright",
                    }
                }
            ],
            "update": {"probe": {"method": "none"}},
            "documentation": {
                "what_it_does": "Regions for a test, nothing more.",
                "why_you_want_it": "Because the test suite needs a manifest.",
                "upstream_url": "https://download.geofabrik.de/",
            },
        }
    )
    not_data = regions.model_copy(update={"name": "vector-map-kit"})
    problem = derived_source_method_problem(m, {"osm-regions": regions, "vector-map-kit": not_data})
    assert problem is not None and "kit 'vector-map-kit' to be a 'data' unit" in problem
