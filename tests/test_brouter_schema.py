# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""The ``brouter-mapcreator`` converter's block and its three inputs.  D-063."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from hammunition.manifest.schema import (
    DerivedDataInstall,
    PackageManifest,
    derived_source_method_problem,
)

SHA = "a" * 64
DOCS = {
    "what_it_does": "Does an example thing for the purposes of testing.",
    "why_you_want_it": "Because the test suite requires a valid manifest.",
    "upstream_url": "https://example.invalid/",
}
OSM = {"licence": "ODbL-1.0", "licence_url": "https://www.openstreetmap.org/copyright"}


def _manifest(
    name: str, install: dict[str, Any], depends: list[str] | None = None
) -> dict[str, Any]:
    return {
        "name": name,
        "version": "1.0",
        "summary": "An example package",
        "categories": ["navigation-maps"],
        "depends": depends or [],
        "install": [{"install": install}],
        "update": {"probe": {"method": "none"}},
        "documentation": DOCS,
    }


def _block(**extra: Any) -> dict[str, Any]:
    return {
        "method": "derived",
        "converter": "brouter-mapcreator",
        "source": "osm-regions",
        "program": "brouter",
        "profiles": "brouter-mapcreator-profiles",
        "elevation": "dem-copernicus",
        **OSM,
        **extra,
    }


DEPENDS = ["osm-regions", "brouter", "brouter-mapcreator-profiles", "dem-copernicus"]


def _segments(
    block: dict[str, Any] | None = None, depends: list[str] | None = None
) -> PackageManifest:
    return PackageManifest.model_validate(
        _manifest("brouter-segments", block or _block(), DEPENDS if depends is None else depends)
    )


def test_a_brouter_mapcreator_block_with_its_three_inputs_validates() -> None:
    block = _segments().install[0].install
    assert isinstance(block, DerivedDataInstall)
    assert (block.program, block.profiles, block.elevation) == (
        "brouter",
        "brouter-mapcreator-profiles",
        "dem-copernicus",
    )


def test_elevation_is_optional() -> None:
    block = _block()
    del block["elevation"]
    parsed = _segments(block, DEPENDS[:3]).install[0].install
    assert isinstance(parsed, DerivedDataInstall) and parsed.elevation is None


@pytest.mark.parametrize("field", ["program", "profiles"])
def test_program_and_profiles_are_required_on_this_converter(field: str) -> None:
    block = _block()
    del block[field]
    with pytest.raises(ValidationError, match=field):
        _segments(block)


@pytest.mark.parametrize("field", ["program", "profiles", "elevation"])
def test_the_three_inputs_are_refused_on_any_other_converter(field: str) -> None:
    block = {
        "method": "derived",
        "converter": "routino-planetsplitter",
        "source": "osm-regions",
        field: "something",
        **OSM,
    }
    with pytest.raises(ValidationError, match=field):
        PackageManifest.model_validate(_manifest("x", block, ["osm-regions", "something"]))


@pytest.mark.parametrize("missing", DEPENDS)
def test_every_input_must_be_in_depends(missing: str) -> None:
    with pytest.raises(ValidationError, match=missing):
        _segments(depends=[d for d in DEPENDS if d != missing])


def _catalog() -> dict[str, PackageManifest]:
    units = {
        "osm-regions": _manifest("osm-regions", {"method": "osm-regions", **OSM}),
        "brouter": _manifest(
            "brouter",
            {
                "method": "binary",
                "artifact": {"url": "https://example.invalid/brouter.zip", "sha256": SHA},
                "format": "zip",
                "install_tree": True,
                "tree_marker": "brouter.jar",
            },
        ),
        "brouter-mapcreator-profiles": _manifest(
            "brouter-mapcreator-profiles",
            {
                "method": "data",
                "artifacts": [
                    {
                        "url": "https://example.invalid/all.brf",
                        "sha256": SHA,
                        "size": 1,
                        "install_as": "all.brf",
                    }
                ],
                "licence": "MIT",
                "licence_url": "https://example.invalid/LICENSE",
            },
        ),
        "dem-copernicus": _manifest(
            "dem-copernicus",
            {
                "method": "dem-tiles",
                "provider": "copernicus-glo30",
                "licence": "Copernicus DEM licence",
                "licence_url": "https://example.invalid/readme.html",
            },
        ),
    }
    return {name: PackageManifest.model_validate(data) for name, data in units.items()}


def test_the_catalog_wide_check_accepts_the_right_methods() -> None:
    assert derived_source_method_problem(_segments(), _catalog()) is None


@pytest.mark.parametrize(
    ("field", "wrong_unit", "needed"),
    [
        ("program", "osm-regions", "binary"),
        ("profiles", "brouter", "data"),
        ("elevation", "brouter-mapcreator-profiles", "dem-tiles"),
    ],
)
def test_the_catalog_wide_check_refuses_a_wrong_method_by_name(
    field: str, wrong_unit: str, needed: str
) -> None:
    block = _block(**{field: wrong_unit})
    depends = sorted({*DEPENDS, wrong_unit})
    problem = derived_source_method_problem(_segments(block, depends), _catalog())
    assert problem is not None
    assert field in problem and wrong_unit in problem and needed in problem


def test_a_program_that_is_a_binary_but_not_a_tree_is_refused() -> None:
    catalog = _catalog()
    catalog["brouter"] = PackageManifest.model_validate(
        _manifest(
            "brouter",
            {
                "method": "binary",
                "artifact": {"url": "https://example.invalid/brouter", "sha256": SHA},
                "format": "executable",
            },
        )
        | {"binaries": [{"produced": "brouter", "install_as": "brouter"}]}
    )
    problem = derived_source_method_problem(_segments(), catalog)
    assert problem is not None and "install_tree" in problem
