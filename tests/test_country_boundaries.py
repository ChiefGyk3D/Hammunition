# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""Natural Earth countries -> the closed admin_level=2 relations maptool needs.

No network and never the 13 MB file: a tiny synthetic GeoJSON, and a
hand-written excerpt in Natural Earth's own property shape, including the
``ISO_A2: -99`` trap France falls into.
"""

from __future__ import annotations

import itertools
import json
import xml.etree.ElementTree as ET
from typing import Any

import pytest

from hammunition.country_boundaries import (
    FIRST_ID,
    WAY_SEGMENTS,
    CountryBoundaryError,
    boundary_xml,
    read_countries,
)


def _feature(props: dict[str, Any], geometry: dict[str, Any]) -> dict[str, Any]:
    return {"type": "Feature", "properties": props, "geometry": geometry}


def _square(x: float, y: float, size: float) -> list[list[float]]:
    return [[x, y], [x + size, y], [x + size, y + size], [x, y + size], [x, y]]


def _collection(*features: dict[str, Any]) -> str:
    return json.dumps({"type": "FeatureCollection", "features": list(features)})


SYNTHETIC = _collection(
    _feature(
        {"NAME": "Testland", "ISO_A2": "TL", "ISO_A2_EH": "TL"},
        # One square with a hole.
        {"type": "Polygon", "coordinates": [_square(0, 0, 10), _square(4, 4, 2)]},
    ),
    _feature(
        {"NAME": "Two Islands", "ISO_A2": "TI", "ISO_A2_EH": "TI"},
        {"type": "MultiPolygon", "coordinates": [[_square(20, 0, 1)], [_square(30, 0, 1)]]},
    ),
)

#: Natural Earth v5.1.2's own property names, hand-written, three features:
#: France is ISO_A2 -99 and ISO_A2_EH FR; Clipperton is a separate FR feature;
#: Andorra is ordinary. Coordinates are coarse, not Natural Earth's.
NATURAL_EARTH_EXCERPT = _collection(
    _feature(
        {
            "featurecla": "Admin-0 country",
            "ADMIN": "France",
            "NAME": "France",
            "ADM0_A3": "FRA",
            "ISO_A2": "-99",
            "ISO_A2_EH": "FR",
            "ISO_A3_EH": "FRA",
        },
        {
            "type": "MultiPolygon",
            "coordinates": [
                [[[-4.8, 48.4], [2.5, 51.1], [8.2, 49.0], [7.5, 43.8], [3.1, 42.4], [-4.8, 48.4]]],
                [[[8.5, 41.4], [9.6, 42.9], [9.4, 41.4], [8.5, 41.4]]],
            ],
        },
    ),
    _feature(
        {
            "featurecla": "Admin-0 country",
            "ADMIN": "Clipperton Island",
            "NAME": "Clipperton I.",
            "ADM0_A3": "CLP",
            "ISO_A2": "-99",
            "ISO_A2_EH": "FR",
            "ISO_A3_EH": "FRA",
        },
        {
            "type": "Polygon",
            "coordinates": [[[-109.2, 10.3], [-109.2, 10.4], [-109.3, 10.3], [-109.2, 10.3]]],
        },
    ),
    _feature(
        {
            "featurecla": "Admin-0 country",
            "ADMIN": "Andorra",
            "NAME": "Andorra",
            "ADM0_A3": "AND",
            "ISO_A2": "AD",
            "ISO_A2_EH": "AD",
            "ISO_A3_EH": "AND",
        },
        {
            "type": "Polygon",
            "coordinates": [[[1.4, 42.4], [1.7, 42.5], [1.7, 42.6], [1.4, 42.6], [1.4, 42.4]]],
        },
    ),
    _feature(
        {"NAME": "Bir Tawil", "ADM0_A3": "BRT", "ISO_A2": "-99", "ISO_A2_EH": "-99"},
        {"type": "Polygon", "coordinates": [_square(33, 21, 1)]},
    ),
)


def _parse(xml: str) -> ET.Element:
    return ET.fromstring(xml)


def _ways_of(root: ET.Element, relation: ET.Element) -> list[tuple[list[int], str]]:
    by_id = {int(w.get("id", "0")): w for w in root.iter("way")}
    out = []
    for member in relation.iter("member"):
        way = by_id[int(member.get("ref", "0"))]
        out.append(([int(nd.get("ref", "0")) for nd in way.iter("nd")], member.get("role", "")))
    return out


def _rings(ways: list[tuple[list[int], str]]) -> list[tuple[list[int], str]]:
    """Join consecutive ways sharing an end node into rings."""
    rings: list[tuple[list[int], str]] = []
    for nodes, role in ways:
        if rings and rings[-1][0][-1] == nodes[0] and rings[-1][0][0] != rings[-1][0][-1]:
            rings[-1][0].extend(nodes[1:])
        else:
            rings.append((list(nodes), role))
    return rings


def test_each_country_is_one_closed_admin_level_2_relation_maptool_reads() -> None:
    result = boundary_xml(read_countries(SYNTHETIC), ["TL", "TI"])
    root = _parse(result.xml)
    relations = root.findall("relation")
    assert [int(r.get("id", "0")) for r in relations] == [result.relations[c] for c in ("TL", "TI")]
    for relation in relations:
        tags = {t.get("k"): t.get("v") for t in relation.iter("tag")}
        # The two tags maptool's process_boundaries_setup reads.
        assert tags["admin_level"] == "2"
        assert tags["ISO3166-1"] in ("TL", "TI")
        assert tags["type"] == "boundary"
        assert tags["boundary"] == "administrative"
        for nodes, _ in _rings(_ways_of(root, relation)):
            assert nodes[0] == nodes[-1], "every ring is closed on the same node"
            assert len(set(nodes)) == len(nodes) - 1
    tl = relations[0]
    assert {t.get("k"): t.get("v") for t in tl.iter("tag")}["name"] == "Testland"
    assert [role for _, role in _rings(_ways_of(root, tl))] == ["outer", "inner"]
    assert [role for _, role in _rings(_ways_of(root, relations[1]))] == ["outer", "outer"]
    assert result.missing == ()


def test_every_id_is_above_nine_quadrillion_and_in_merge_order() -> None:
    # Review M-10: deterministic, byte for byte.
    assert boundary_xml(read_countries(SYNTHETIC), ["TL", "TI"]).xml == (
        boundary_xml(read_countries(SYNTHETIC), ["TL", "TI"]).xml
    )
    root = _parse(boundary_xml(read_countries(SYNTHETIC), ["TL", "TI"]).xml)
    kinds = [child.tag for child in root]
    assert kinds == sorted(kinds, key=["node", "way", "relation"].index)
    for kind in ("node", "way", "relation"):
        ids = [int(e.get("id", "0")) for e in root.iter(kind)]
        assert ids and min(ids) > FIRST_ID == 9 * 10**15
        assert ids == sorted(ids) and len(set(ids)) == len(ids)


def test_a_long_ring_is_split_into_ways_that_share_their_end_nodes() -> None:
    import math

    n = 2 * WAY_SEGMENTS + 500
    ring = [
        [round(10 * math.cos(2 * math.pi * i / n), 7), round(10 * math.sin(2 * math.pi * i / n), 7)]
        for i in range(n)
    ]
    ring.append(ring[0])
    text = _collection(
        _feature({"NAME": "Round", "ISO_A2_EH": "RD"}, {"type": "Polygon", "coordinates": [ring]})
    )
    root = _parse(boundary_xml(read_countries(text), ["RD"]).xml)
    ways = _ways_of(root, root.findall("relation")[0])
    assert len(ways) == 3
    assert all(len(nodes) <= 2000 for nodes, _ in ways)
    for (a, _), (b, _) in itertools.pairwise(ways):
        assert a[-1] == b[0]
    ((joined, role),) = _rings(ways)
    assert joined[0] == joined[-1] and len(joined) == n + 1 and role == "outer"


def test_a_code_natural_earth_does_not_have_is_named_not_invented() -> None:
    result = boundary_xml(read_countries(SYNTHETIC), ["TL", "ZZ", "ZZ"])
    assert list(result.relations) == ["TL"]
    assert result.missing == ("ZZ",)


def test_nothing_known_is_an_empty_file_with_no_relation() -> None:
    result = boundary_xml(read_countries(SYNTHETIC), ["ZZ"])
    assert result.relations == {}
    assert _parse(result.xml).findall("relation") == []


def test_the_real_shape_finds_france_by_iso_a2_eh_with_its_overseas_part() -> None:
    countries = read_countries(NATURAL_EARTH_EXCERPT)
    # -99 in both fields names no country.
    assert sorted(countries) == ["AD", "FR"]
    assert countries["FR"].name == "France"  # the ADM0_A3 == ISO_A3_EH feature
    assert len(countries["FR"].polygons) == 3  # mainland, Corsica, Clipperton
    result = boundary_xml(countries, ["FR", "AD"])
    root = _parse(result.xml)
    names = [{t.get("k"): t.get("v") for t in r.iter("tag")}["name"] for r in root.iter("relation")]
    assert names == ["France", "Andorra"]
    first = next(root.iter("node"))
    assert (first.get("lat"), first.get("lon")) == ("48.4000000", "-4.8000000")


def test_a_name_with_markup_characters_is_escaped() -> None:
    text = _collection(
        _feature(
            {"NAME": 'Côte "d" <&> Test', "ISO_A2_EH": "CT"},
            {"type": "Polygon", "coordinates": [_square(0, 0, 1)]},
        )
    )
    root = _parse(boundary_xml(read_countries(text), ["CT"]).xml)
    tags = {t.get("k"): t.get("v") for t in root.iter("tag")}
    assert tags["name"] == 'Côte "d" <&> Test'


@pytest.mark.parametrize(
    ("text", "match"),
    [
        ("not json", "not valid JSON"),
        ('{"type": "Feature"}', "FeatureCollection"),
        (
            _collection(
                _feature(
                    {"NAME": "Line", "ISO_A2_EH": "LN"}, {"type": "LineString", "coordinates": []}
                )
            ),
            "LineString",
        ),
        (
            _collection(
                _feature(
                    {"NAME": "Thin", "ISO_A2_EH": "TH"},
                    {"type": "Polygon", "coordinates": [[[0, 0], [1, 1], [0, 0]]]},
                )
            ),
            "three",
        ),
        (
            _collection(
                _feature(
                    {"NAME": "Far", "ISO_A2_EH": "FA"},
                    {"type": "Polygon", "coordinates": [[[0, 0], [200, 0], [0, 1], [0, 0]]]},
                )
            ),
            "off the globe",
        ),
    ],
)
def test_a_file_that_is_not_the_shape_read_is_refused_by_name(text: str, match: str) -> None:
    with pytest.raises(CountryBoundaryError, match=match):
        read_countries(text)


def test_osm_navit_names_a_boundary_unit_whose_one_file_is_the_pinned_geojson() -> None:
    from pathlib import Path

    from hammunition.country_boundaries import boundary_source
    from hammunition.manifest.load import load_catalog
    from hammunition.manifest.schema import DerivedDataInstall

    catalog = load_catalog(Path(__file__).parent.parent / "catalog" / "packages")
    block = catalog["osm-navit"].install[0].install
    assert isinstance(block, DerivedDataInstall)
    assert block.boundaries == "country-boundaries"
    assert "osmium-tool" in catalog["osm-navit"].depends
    source = boundary_source(catalog[block.boundaries], Path("/usr/local"))
    assert source.path == Path(
        "/usr/local/share/hammunition/data/country-boundaries/ne_10m_admin_0_countries.geojson"
    )
    assert source.sha256 == "239eec57ac17f100a11e2536cffc56752c318b50ae765b0918ff7aab4ce8f255"
    assert source.size == 13_287_234
    assert "f1890d9f152c896d250a77557a5751a93d494776" in source.url
    assert source.licence.startswith("Public domain")


def test_a_boundary_unit_that_is_not_one_geojson_file_is_refused() -> None:
    from pathlib import Path

    from hammunition.country_boundaries import boundary_source
    from hammunition.manifest.load import load_catalog

    catalog = load_catalog(Path(__file__).parent.parent / "catalog" / "packages")
    with pytest.raises(CountryBoundaryError, match="country-files"):
        boundary_source(catalog["country-files"], Path("/usr/local"))
    with pytest.raises(CountryBoundaryError, match="navit"):
        boundary_source(catalog["navit"], Path("/usr/local"))


def test_a_file_where_no_feature_names_a_country_is_refused() -> None:
    """Review M-9: a renamed-schema release would read as no countries at
    all, and every region would convert unmerged with a note."""
    text = _collection(
        _feature(
            {"NAME": "Renamed", "ISO_CODE": "TL"},
            {"type": "Polygon", "coordinates": [_square(0, 0, 1)]},
        )
    )
    with pytest.raises(CountryBoundaryError, match="ISO_A2_EH"):
        read_countries(text)
