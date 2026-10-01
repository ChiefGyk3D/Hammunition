# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""Forest Service FSTopo quads: the index, the pins and the gateway.
D-068, amended 2026-10-01. Synthetic quads near 0/0; no network."""

from __future__ import annotations

from pathlib import Path

import pytest

from hammunition.copernicus import parse_poly
from hammunition.fstopo import (
    GATEWAY,
    PINNED,
    UNVERIFIED,
    FsQuad,
    FsQuadFile,
    FstopoError,
    GatewayProbe,
    load_pins,
    map_url,
    parse_index,
    parse_row,
    render_row,
)

ROW = "0 0 0.125 0.125 1230000 11 ZZ Mount O'Brien"


def test_a_row_reads_back_with_a_name_holding_spaces_and_an_apostrophe() -> None:
    quad = parse_row(ROW)
    assert quad == FsQuad(0.0, 0.0, 0.125, 0.125, 1230000, 11, "ZZ", "Mount O'Brien")
    assert render_row(quad) == ROW
    assert quad.name == "ZZ_Mount_O_Brien_1230000_11"
    assert quad.map_url == (f"{GATEWAY}downloadMap.php?mapID=1230000&mapType=tif&seriesType=FSTopo")


@pytest.mark.parametrize(
    "bad",
    [
        "0 0 0.125 0.125 1230000 11 zz Lower",
        "0 0 0.125 0.125 12 11 ZZ Short secoord",
        "0.2 0 0.125 0.125 1230000 11 ZZ Upside down",
        "0 0 0.125 0.125 1230000 11 ZZ",
    ],
)
def test_a_malformed_row_is_refused(bad: str) -> None:
    with pytest.raises(FstopoError):
        parse_row(bad)


def test_an_empty_or_duplicated_index_is_refused() -> None:
    with pytest.raises(FstopoError, match="names no quads"):
        parse_index("# nothing\n")
    with pytest.raises(FstopoError, match="second time"):
        parse_index(f"{ROW}\n{ROW}\n")


def test_selection_is_by_the_eighth_degree_cells_the_outline_touches() -> None:
    near = "0 0.125 0.125 0.25 1230001 11 ZZ Beta"
    far = "10 10 10.125 10.125 1230002 11 ZZ Far"
    index = parse_index(f"{ROW}\n{near}\n{far}\n")
    outer, holes = parse_poly("o\n1\n 0.05 0.05\n 0.2 0.05\n 0.2 0.1\n 0.05 0.1\nEND\nEND\n")
    assert [q.secoord for q in index.select(outer, holes)] == [1230000, 1230001]


def _pins(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "fstopo-pins.yaml"
    path.write_text(text)
    return path


def test_pins_load_and_refuse_by_name(tmp_path: Path) -> None:
    sha = "a" * 64
    pins = load_pins(_pins(tmp_path, f"pins:\n- secoord: 1230000\n  size: 10\n  sha256: {sha}\n"))
    assert pins[1230000].size == 10 and pins[1230000].sha256 == sha
    assert load_pins(_pins(tmp_path, "pins: []\n")) == {}
    for bad in (
        "nothing: here\n",
        "pins:\n- secoord: 1230000\n  size: 10\n",
        f"pins:\n- secoord: 1230000\n  size: 10\n  sha256: {'A' * 64}\n",
        f"pins:\n- {{secoord: 1, size: 1, sha256: {sha}}}\n- {{secoord: 1, size: 1, sha256: {sha}}}\n",
        "pins: [\n",
    ):
        with pytest.raises(FstopoError, match=r"fstopo-pins\.yaml"):
            load_pins(_pins(tmp_path, bad))


def test_a_file_says_how_it_is_checked() -> None:
    quad = parse_row(ROW)
    assert FsQuadFile(quad, "u", 1, "a" * 64).verified_by == PINNED
    assert FsQuadFile(quad, "u", 1, None).verified_by == UNVERIFIED
    assert "publishes no checksum" in PINNED and "publishes no checksum" in UNVERIFIED


FILE = f"{GATEWAY}data3/00000/fstopo/FSTopo Mount O'Brien 1230000.tiff"


class Head:
    def __init__(self, answers: dict[str, tuple[int, int, str | None]]) -> None:
        self.answers = answers
        self.asked: list[str] = []

    def __call__(self, url: str) -> tuple[int, int, str | None]:
        self.asked.append(url)
        return self.answers[url]


def test_the_gateway_s_one_redirect_is_followed_by_the_probe_and_sized() -> None:
    encoded = f"{GATEWAY}data3/00000/fstopo/FSTopo%20Mount%20O%27Brien%201230000.tiff"
    head = Head({map_url(1230000): (302, 0, FILE), encoded: (200, 21_000_000, None)})
    assert GatewayProbe(head).locate(1230000) == (encoded, 21_000_000)
    assert head.asked == [map_url(1230000), encoded]


@pytest.mark.parametrize(
    "location",
    [
        "https://elsewhere.example/FSTopo.tiff",
        "http://data.fs.usda.gov/geodata/rastergateway/data3/x.tiff",
        f"{GATEWAY}data3/00000/fstopo/FSTopo.pdf",
        f"{GATEWAY}../../etc/x.tiff",
    ],
)
def test_a_redirect_anywhere_else_is_refused_not_followed(location: str) -> None:
    head = Head({map_url(1230000): (302, 0, location)})
    with pytest.raises(FstopoError):
        GatewayProbe(head).locate(1230000)
    assert head.asked == [map_url(1230000)]


def test_no_redirect_or_an_empty_file_is_refused() -> None:
    with pytest.raises(FstopoError, match="no redirect"):
        GatewayProbe(Head({map_url(1230000): (200, 512, None)})).locate(1230000)
    encoded = f"{GATEWAY}data3/x.tiff"
    head = Head({map_url(1230000): (302, 0, encoded), encoded: (404, 0, None)})
    with pytest.raises(FstopoError, match="404"):
        GatewayProbe(head).locate(1230000)
