# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""FSTopo and 3DEP in the schema.  D-068, amended 2026-10-01.

Two provider members on existing methods, and two optional converter inputs:
``alternative`` on ``gdal-dem`` (the ``dem-tiles`` unit drawn from when the
station's ``dem_source`` is ``3dep``) and ``fstopo`` on ``ustopo-mosaic``
(the Forest Service sheets mosaicked beside US Topo).
"""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from hammunition.manifest.schema import (
    DemTilesInstall,
    PackageManifest,
    TopoQuadsInstall,
    derived_source_method_problem,
)

PD = {"licence": "Public domain (USGS)", "licence_url": "https://www.usgs.gov/"}


def _manifest(name: str, block: dict[str, Any], depends: list[str]) -> PackageManifest:
    return PackageManifest.model_validate(
        {
            "name": name,
            "version": "station",
            "summary": "A unit for a test",
            "categories": ["navigation-maps"],
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


def test_the_new_providers_validate() -> None:
    dem = DemTilesInstall.model_validate({"method": "dem-tiles", "provider": "usgs-3dep", **PD})
    topo = TopoQuadsInstall.model_validate(
        {"method": "topo-quads", "provider": "usfs-fstopo", **PD}
    )
    assert (dem.provider, topo.provider) == ("usgs-3dep", "usfs-fstopo")


def test_an_unknown_provider_is_refused() -> None:
    with pytest.raises(ValidationError):
        DemTilesInstall.model_validate({"method": "dem-tiles", "provider": "srtm", **PD})


def _gdal(**extra: Any) -> dict[str, Any]:
    return {"method": "derived", "converter": "gdal-dem", "source": "dem-copernicus", **PD, **extra}


def _mosaic(**extra: Any) -> dict[str, Any]:
    return {
        "method": "derived",
        "converter": "ustopo-mosaic",
        "source": "usgs-ustopo",
        **PD,
        **extra,
    }


def test_gdal_dem_takes_an_optional_alternative_in_depends() -> None:
    m = _manifest("dem-qmapshack", _gdal(alternative="dem-3dep"), ["dem-copernicus", "dem-3dep"])
    assert m.install[0].install.alternative == "dem-3dep"  # type: ignore[union-attr]
    assert _manifest("dem-qmapshack", _gdal(), ["dem-copernicus"])
    with pytest.raises(ValidationError, match="depends"):
        _manifest("dem-qmapshack", _gdal(alternative="dem-3dep"), ["dem-copernicus"])


def test_ustopo_mosaic_takes_an_optional_fstopo_in_depends() -> None:
    m = _manifest("ustopo-qmapshack", _mosaic(fstopo="usfs-fstopo"), ["usgs-ustopo", "usfs-fstopo"])
    assert m.install[0].install.fstopo == "usfs-fstopo"  # type: ignore[union-attr]
    assert _manifest("ustopo-qmapshack", _mosaic(), ["usgs-ustopo"])


def test_the_inputs_mean_nothing_to_another_converter() -> None:
    with pytest.raises(ValidationError, match="alternative"):
        _manifest("x", _mosaic(alternative="dem-3dep"), ["usgs-ustopo", "dem-3dep"])
    with pytest.raises(ValidationError, match="fstopo"):
        _manifest("x", _gdal(fstopo="usfs-fstopo"), ["dem-copernicus", "usfs-fstopo"])


def _tiles(name: str, provider: str) -> PackageManifest:
    return _manifest(name, {"method": "dem-tiles", "provider": provider, **PD}, ["osm-regions"])


def _sheets(name: str, provider: str) -> PackageManifest:
    return _manifest(name, {"method": "topo-quads", "provider": provider, **PD}, ["osm-regions"])


def test_the_alternative_must_be_the_3dep_provider_catalog_wide() -> None:
    m = _manifest("dem-qmapshack", _gdal(alternative="dem-3dep"), ["dem-copernicus", "dem-3dep"])
    good = {"dem-copernicus": _tiles("dem-copernicus", "copernicus-glo30")}
    assert (
        derived_source_method_problem(m, {**good, "dem-3dep": _tiles("dem-3dep", "usgs-3dep")})
        is None
    )
    problem = derived_source_method_problem(
        m, {**good, "dem-3dep": _tiles("dem-3dep", "copernicus-glo30")}
    )
    assert problem is not None and "usgs-3dep" in problem


def test_the_fstopo_input_must_be_the_forest_service_provider_catalog_wide() -> None:
    m = _manifest("ustopo-qmapshack", _mosaic(fstopo="usfs-fstopo"), ["usgs-ustopo", "usfs-fstopo"])
    good = {"usgs-ustopo": _sheets("usgs-ustopo", "usgs-ustopo")}
    assert (
        derived_source_method_problem(
            m, {**good, "usfs-fstopo": _sheets("usfs-fstopo", "usfs-fstopo")}
        )
        is None
    )
    problem = derived_source_method_problem(
        m, {**good, "usfs-fstopo": _sheets("usfs-fstopo", "usgs-ustopo")}
    )
    assert problem is not None and "usfs-fstopo" in problem
