# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""USGS 3DEP 1/3-arc-second tiles: names, the carried list, the plan-time
check.  D-068, amended 2026-10-01. No network."""

from __future__ import annotations

import pytest

from hammunition.copernicus import CopernicusError
from hammunition.copernicus import tile_name as copernicus_name
from hammunition.usgs3dep import (
    PIXELS,
    TileRow,
    check_tile,
    dem_square,
    parse_tile_list,
    square_of,
    tile_name,
    tile_url,
)

MD5 = "0123456789abcdef0123456789abcdef"


def test_a_tile_is_named_by_its_north_west_corner() -> None:
    # The square from latitude 38 to 39 and longitude -79 to -78.
    assert tile_name((38, -79)) == "USGS_13_n39w079"
    assert square_of("USGS_13_n39w079") == (38, -79)


@pytest.mark.parametrize(
    "square", [(38, -79), (-15, -171), (13, 144), (-1, 5), (0, -1), (70, -150)]
)
def test_names_and_squares_round_trip_in_every_hemisphere(square: tuple[int, int]) -> None:
    assert square_of(tile_name(square)) == square


def test_american_samoa_and_guam_names() -> None:
    assert tile_name((-15, -171)) == "USGS_13_s14w171"
    assert tile_name((13, 144)) == "USGS_13_n14e144"


def test_dem_square_reads_either_provider() -> None:
    assert dem_square("USGS_13_n39w079") == (38, -79)
    assert dem_square(copernicus_name((38, -79))) == (38, -79)
    with pytest.raises(CopernicusError):
        dem_square("srtm_20_05")


def test_the_url_is_the_bucket_current_folder() -> None:
    assert tile_url("USGS_13_n39w079") == (
        "https://prd-tnm.s3.amazonaws.com/StagedProducts/Elevation/13/TIFF/current/"
        "n39w079/USGS_13_n39w079.tif"
    )
    with pytest.raises(CopernicusError):
        tile_url("../n39w079")


def test_pixels_keep_the_one_third_second_grid() -> None:
    assert PIXELS == 10812


def test_the_list_parses_and_refuses_what_it_should() -> None:
    rows = parse_tile_list(f"# list\nUSGS_13_n39w079 487654321 {MD5}-94\n")
    assert rows == {"USGS_13_n39w079": TileRow("USGS_13_n39w079", 487654321, f"{MD5}-94")}
    for bad in (
        "",
        "# nothing\n",
        f"USGS_13_n39w079 0 {MD5}\n",
        f"USGS_13_n39w079 12 {MD5}\nUSGS_13_n39w079 12 {MD5}\n",
        "USGS_13_n39w079 12 nothex\n",
        f"Copernicus 12 {MD5}\n",
    ):
        with pytest.raises(CopernicusError):
            parse_tile_list(bad)


class Probe:
    def __init__(self, answer: tuple[int, int, str | None]) -> None:
        self.answer = answer
        self.asked: list[str] = []

    def head(self, url: str) -> tuple[int, int, str | None]:
        self.asked.append(url)
        return self.answer


ROW = TileRow("USGS_13_n39w079", 1000, f"{MD5}-2")


def test_check_tile_passes_the_same_object() -> None:
    probe = Probe((200, 1000, f'"{MD5}-2"'))
    check_tile(ROW, probe)
    assert probe.asked == [tile_url(ROW.name)]


@pytest.mark.parametrize(
    "answer", [(404, 0, None), (200, 999, f'"{MD5}-2"'), (200, 1000, f'"{MD5}-3"')]
)
def test_check_tile_refuses_a_changed_or_missing_object(
    answer: tuple[int, int, str | None],
) -> None:
    with pytest.raises(CopernicusError, match=r"gen_3dep_tiles\.py --fetch"):
        check_tile(ROW, Probe(answer))
