# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""The phone converters' schema: two enum members and one pinned tool.  D-067."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from hammunition.manifest.schema import (
    CONVERTER_SOURCE_METHOD,
    CONVERTERS_WITH_TOOL,
    DerivedDataInstall,
    ManifestError,
)

URL = (
    "https://repo1.maven.org/maven2/org/mapsforge/mapsforge-poi-writer/0.25.0/"
    "mapsforge-poi-writer-0.25.0-jar-with-dependencies.jar"
)
TOOL: dict[str, Any] = {
    "artifact": {
        "url": URL,
        "sha256": "85dd23488511f51a710139dffc8c622d184ea93e817c4ec27dde1c222b7432a7",
        "signature_url": f"{URL}.asc",
    },
    "size": 18827962,
    "licence": "LGPL-3.0-only",
    "licence_url": "https://github.com/mapsforge/mapsforge/blob/master/LICENSE",
}


def _block(converter: str = "mapsforge-poi", **extra: Any) -> dict[str, Any]:
    return {
        "method": "derived",
        "converter": converter,
        "source": "osm-regions",
        "licence": "ODbL-1.0",
        "licence_url": "https://www.openstreetmap.org/copyright",
        **extra,
    }


def test_both_phone_converters_read_osm_regions() -> None:
    assert CONVERTER_SOURCE_METHOD["mapsforge-map"] == "osm-regions"
    assert CONVERTER_SOURCE_METHOD["mapsforge-poi"] == "osm-regions"
    assert set(CONVERTERS_WITH_TOOL) == {"mapsforge-poi"}


def test_mapsforge_map_needs_no_tool() -> None:
    block = DerivedDataInstall.model_validate(_block("mapsforge-map"))
    assert block.tool is None


def test_mapsforge_poi_requires_its_tool() -> None:
    with pytest.raises((ValidationError, ManifestError), match="tool"):
        DerivedDataInstall.model_validate(_block())


@pytest.mark.parametrize("converter", ["mapsforge-map", "mkgmap", "navit-maptool"])
def test_a_tool_on_any_other_converter_is_refused(converter: str) -> None:
    with pytest.raises((ValidationError, ManifestError), match="tool"):
        DerivedDataInstall.model_validate(_block(converter, tool=TOOL))


def test_the_tool_is_pinned_and_names_a_bare_file() -> None:
    block = DerivedDataInstall.model_validate(_block(tool=TOOL))
    assert block.tool is not None
    assert block.tool.file_name == "mapsforge-poi-writer-0.25.0-jar-with-dependencies.jar"
    assert block.tool.size == 18827962


@pytest.mark.parametrize(
    "change",
    [
        {"size": 0},
        {"licence_url": "http://example.org/licence"},
        {"artifact": {**TOOL["artifact"], "url": URL.replace("https://", "http://")}},
        {"artifact": {**TOOL["artifact"], "url": "https://example.org/dir/"}},
        {"artifact": {**TOOL["artifact"], "url": "https://example.org/..%2F.jar"}},
        {"artifact": {**TOOL["artifact"], "sha256": "0" * 63}},
    ],
)
def test_a_tool_that_is_not_a_plain_pinned_https_file_is_refused(change: dict[str, Any]) -> None:
    with pytest.raises((ValidationError, ManifestError)):
        DerivedDataInstall.model_validate(_block(tool={**TOOL, **change}))
