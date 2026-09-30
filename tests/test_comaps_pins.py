# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""CoMaps' map index, the generated pins and the region table.  D-069.

The index is a small fixture shaped like CoMaps' ``data/countries.txt``: a
tree of groups whose leaves carry a size and a base64 SHA-1. Nothing here
touches the network; the generator's fetch and HEAD are injected.
"""

from __future__ import annotations

import base64
import hashlib
import importlib.util
import json
import subprocess
import sys
from datetime import date
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from hammunition.comaps import (
    ComapsError,
    flatten,
    load_pins,
    map_url,
    parse_pins,
    region_table,
    resolve_regions,
    sha1_hex,
    version_date,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
COMMIT = "72632e4de65a98dfed827d8e447f0287168639d0"


def _sha1(text: str) -> str:
    return base64.b64encode(hashlib.sha1(text.encode()).digest()).decode()


def _leaf(name: str, size: int = 1000) -> dict[str, Any]:
    return {"id": name, "s": size, "sha1_base64": _sha1(name)}


INDEX: dict[str, Any] = {
    "id": "Countries",
    "v": 260830,
    "map_series": "2026.06.28",
    "g": [
        _leaf("World", 53387231),
        _leaf("WorldCoasts", 8494206),
        {
            "id": "United States of America",
            "g": [
                _leaf("US_Vermont", 60883711),
                _leaf("US_Delaware", 32804869),
                {"id": "US_New Hampshire", "s": 2000, "sha1_base64": _sha1("nh")},
                {
                    "id": "Maryland",
                    "g": [_leaf("US_Maryland_Baltimore"), _leaf("US_Maryland_and_DC")],
                },
                {
                    "id": "California",
                    "g": [_leaf("US_California_LA"), _leaf("US_California_Chico")],
                },
            ],
        },
        {"id": "Germany", "g": [_leaf("Germany_Berlin"), _leaf("Germany_Saarland")]},
        _leaf("Luxembourg"),
    ],
}

REGIONS = [
    "europe/germany",
    "europe/germany/berlin",
    "europe/germany/bayern",
    "europe/luxembourg",
    "north-america/us",
    "north-america/us/california",
    "north-america/us/delaware",
    "north-america/us/district-of-columbia",
    "north-america/us/maryland",
    "north-america/us/new-hampshire",
    "north-america/us/vermont",
]


def test_the_index_flattens_to_its_leaves() -> None:
    maps = flatten(INDEX)
    assert maps["US_Vermont"].size == 60883711
    assert "California" not in maps and "US_California_LA" in maps
    assert len(maps) == 12


def test_a_map_listed_under_two_groups_is_one_map() -> None:
    shared: dict[str, Any] = {
        "id": "Countries",
        "g": [{"id": "A", "g": [_leaf("Crimea")]}, {"id": "B", "g": [_leaf("Crimea")]}],
    }
    assert list(flatten(shared)) == ["Crimea"]
    shared["g"][1]["g"][0]["s"] = 5
    with pytest.raises(ComapsError, match="two different maps"):
        flatten(shared)


def test_sha1_is_decoded_from_the_index_form() -> None:
    assert sha1_hex(_sha1("US_Vermont")) == hashlib.sha1(b"US_Vermont").hexdigest()
    with pytest.raises(ComapsError):
        sha1_hex("not base64 of twenty bytes")


def test_the_region_table_follows_the_rule() -> None:
    table = region_table(INDEX, REGIONS)
    assert table["north-america/us/vermont"] == ("US_Vermont",)
    assert table["north-america/us/new-hampshire"] == ("US_New Hampshire",)
    assert table["north-america/us/california"] == ("US_California_Chico", "US_California_LA")
    assert table["north-america/us/maryland"] == ("US_Maryland_Baltimore", "US_Maryland_and_DC")
    # The two reviewed aliases.
    assert table["north-america/us/district-of-columbia"] == ("US_Maryland_and_DC",)
    assert len(table["north-america/us"]) == 7
    assert table["europe/germany/berlin"] == ("Germany_Berlin",)
    assert table["europe/luxembourg"] == ("Luxembourg",)
    # A name CoMaps spells differently is left out, never guessed.
    assert "europe/germany/bayern" not in table


def test_regions_resolve_to_maps_once_each_and_name_what_is_unmapped() -> None:
    pins = parse_pins(_render(), known_regions=REGIONS)
    maps, unmapped = resolve_regions(
        [
            "north-america/us/maryland",
            "north-america/us/district-of-columbia",
            "europe/germany/bayern",
        ],
        pins,
    )
    assert [m.id for m in maps] == ["US_Maryland_Baltimore", "US_Maryland_and_DC"]
    assert unmapped == ["europe/germany/bayern"]
    assert maps[1].url == (
        "https://cdn-fi-1.comaps.app/maps/2026.06.28/260830/US_Maryland_and_DC.mwm"
    )


def test_a_map_name_with_a_space_is_quoted_in_its_url() -> None:
    pins = parse_pins(_render(), known_regions=REGIONS)
    assert map_url(pins, "US_New Hampshire").endswith("/260830/US_New%20Hampshire.mwm")


def test_the_version_is_a_date() -> None:
    assert version_date(260830) == date(2026, 8, 30)
    with pytest.raises(ComapsError):
        version_date(261399)


# -- the generator ---------------------------------------------------------


def _generator() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "gen_comaps_pins", REPO_ROOT / "scripts" / "gen_comaps_pins.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _render() -> str:
    gen = _generator()
    text: str = gen.render(INDEX, commit=COMMIT, measured=date(2026, 9, 29), regions=REGIONS)
    return text


def test_the_rendered_file_parses_and_says_it_is_generated() -> None:
    text = _render()
    assert "GENERATED by scripts/gen_comaps_pins.py" in text
    pins = parse_pins(text, known_regions=REGIONS)
    assert pins.commit == COMMIT and pins.version == 260830 and pins.series == "2026.06.28"
    assert pins.maps["US_Delaware"].size == 32804869
    assert pins.regions["north-america/us/vermont"] == ("US_Vermont",)


def test_rendering_is_deterministic() -> None:
    assert _render() == _render()


@pytest.mark.parametrize(
    ("before", "after", "why"),
    [
        ("GENERATED by", "written by", "generated"),
        ("  US_Vermont: {size: 60883711", "  US_Vermont: {size: -1", "size"),
        ("[US_Vermont]", "[US_Nowhere]", "US_Nowhere"),
        ("version: 260830", "version: 999999", "version"),
    ],
)
def test_a_damaged_pin_file_is_refused_by_name(before: str, after: str, why: str) -> None:
    text = _render()
    assert before in text, before
    with pytest.raises(ComapsError, match=why):
        parse_pins(text.replace(before, after, 1), known_regions=REGIONS)


def test_a_region_not_in_the_carried_lists_is_refused() -> None:
    with pytest.raises(ComapsError, match="not a region"):
        parse_pins(_render(), known_regions=[r for r in REGIONS if "vermont" not in r])


def test_check_offline_on_the_carried_file_writes_nothing() -> None:
    pins = REPO_ROOT / "catalog" / "data" / "comaps-pins.yaml"
    before = pins.stat().st_mtime_ns
    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "gen_comaps_pins.py"), "--check", "--offline"],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        check=False,
    )
    assert result.returncode == 0, f"{result.stdout}{result.stderr}"
    assert "well formed" in result.stdout
    assert pins.stat().st_mtime_ns == before


def test_the_carried_file_pins_the_commit_comaps_builds() -> None:
    """The maps must be the version the app's own index names."""
    pins = load_pins(REPO_ROOT / "catalog")
    import yaml

    manifest = yaml.safe_load((REPO_ROOT / "catalog" / "packages" / "comaps.yaml").read_text())
    assert pins.commit == manifest["install"][0]["install"]["commit"]
    assert {"World", "WorldCoasts", "US_Vermont", "US_Delaware"} <= set(pins.maps)
    assert pins.regions["north-america/us/delaware"] == ("US_Delaware",)


def test_check_online_regenerates_and_heads_the_world_map(tmp_path: Path) -> None:
    gen = _generator()
    pins_path = tmp_path / "comaps-pins.yaml"
    pins_path.write_text(_render())
    body = json.dumps(INDEX)
    ok = gen.main(
        ["--check"],
        text=lambda url: body,
        head=lambda url: (200, 53387231),
        pins_path=pins_path,
        commit=COMMIT,
        regions=REGIONS,
    )
    assert ok == 0
    # A mirror answering 200 with an HTML page: the size is the check.
    stale = gen.main(
        ["--check"],
        text=lambda url: body,
        head=lambda url: (200, 1234),
        pins_path=pins_path,
        commit=COMMIT,
        regions=REGIONS,
    )
    assert stale == 1
    changed = json.loads(body)
    changed["g"][2]["g"][0]["s"] = 1
    assert (
        gen.main(
            ["--check"],
            text=lambda url: json.dumps(changed),
            head=lambda url: (200, 53387231),
            pins_path=pins_path,
            commit=COMMIT,
            regions=REGIONS,
        )
        == 1
    )


def test_generate_from_a_local_index(tmp_path: Path) -> None:
    gen = _generator()
    index = tmp_path / "countries.txt"
    index.write_text(json.dumps(INDEX))
    pins_path = tmp_path / "comaps-pins.yaml"
    assert (
        gen.main(
            ["--from", str(index)],
            pins_path=pins_path,
            commit=COMMIT,
            regions=REGIONS,
        )
        == 0
    )
    pins = parse_pins(pins_path.read_text(), known_regions=REGIONS)
    assert pins.maps["World"].size == 53387231
