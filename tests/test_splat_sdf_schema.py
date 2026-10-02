# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""The ``splat-sdf`` converter in the schema.  D-061, amended 2026-10-02.

SPLAT's terrain from the elevation tiles: a ``dem-tiles`` source, and the
same optional ``alternative`` ``gdal-dem`` reads (the 3DEP unit drawn from
when the station chose it).
"""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from hammunition.manifest.schema import (
    CONVERTER_SOURCE_METHOD,
    PackageManifest,
    derived_source_method_problem,
)

LICENCE = {"licence": "Copernicus DEM licence", "licence_url": "https://spacedata.copernicus.eu/"}


def _manifest(name: str, block: dict[str, Any], depends: list[str]) -> PackageManifest:
    return PackageManifest.model_validate(
        {
            "name": name,
            "version": "station",
            "summary": "A unit for a test",
            "categories": ["propagation"],
            "depends": depends,
            "install": [{"install": block}],
            "update": {"probe": {"method": "none"}},
            "documentation": {
                "what_it_does": "A unit for a test, nothing more.",
                "why_you_want_it": "Because the test suite needs a manifest.",
                "upstream_url": "https://gdal.org/",
            },
        }
    )


def _splat(**extra: Any) -> dict[str, Any]:
    return {
        "method": "derived",
        "converter": "splat-sdf",
        "source": "dem-copernicus",
        **LICENCE,
        **extra,
    }


def _tiles(name: str, provider: str) -> PackageManifest:
    return _manifest(
        name, {"method": "dem-tiles", "provider": provider, **LICENCE}, ["osm-regions"]
    )


def test_splat_sdf_reads_a_dem_tiles_source() -> None:
    assert CONVERTER_SOURCE_METHOD["splat-sdf"] == "dem-tiles"
    m = _manifest("splat-sdf", _splat(), ["dem-copernicus"])
    assert m.install[0].install.converter == "splat-sdf"  # type: ignore[union-attr]


def test_splat_sdf_takes_the_same_optional_alternative_as_gdal_dem() -> None:
    m = _manifest("splat-sdf", _splat(alternative="dem-3dep"), ["dem-copernicus", "dem-3dep"])
    assert m.install[0].install.alternative == "dem-3dep"  # type: ignore[union-attr]
    with pytest.raises(ValidationError, match="depends"):
        _manifest("splat-sdf", _splat(alternative="dem-3dep"), ["dem-copernicus"])


def test_the_alternative_is_still_refused_on_a_converter_that_does_not_read_it() -> None:
    block = {
        "method": "derived",
        "converter": "mkgmap",
        "source": "osm-regions",
        "alternative": "dem-3dep",
        **LICENCE,
    }
    with pytest.raises(ValidationError, match="alternative"):
        _manifest("x", block, ["osm-regions", "dem-3dep"])


def test_the_splat_alternative_must_be_the_3dep_provider_catalog_wide() -> None:
    m = _manifest("splat-sdf", _splat(alternative="dem-3dep"), ["dem-copernicus", "dem-3dep"])
    good = {"dem-copernicus": _tiles("dem-copernicus", "copernicus-glo30")}
    good["dem-3dep"] = _tiles("dem-3dep", "usgs-3dep")
    assert derived_source_method_problem(m, good) is None
    bad = dict(good, **{"dem-3dep": _tiles("dem-3dep", "copernicus-glo30")})
    problem = derived_source_method_problem(m, bad)
    assert problem is not None and "usgs-3dep" in problem


def test_a_splat_sdf_source_that_is_not_dem_tiles_is_refused_catalog_wide() -> None:
    m = _manifest("splat-sdf", _splat(), ["dem-copernicus"])
    # A derived unit in the source's place: not a dem-tiles one.
    not_tiles = _manifest("dem-copernicus", _splat(), ["dem-copernicus"])
    problem = derived_source_method_problem(m, {"dem-copernicus": not_tiles})
    assert problem is not None and "'dem-tiles'" in problem
