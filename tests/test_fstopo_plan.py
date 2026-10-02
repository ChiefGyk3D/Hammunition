# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""Which FSTopo sheets the station's regions need, resolved before the plan
prints.  D-068, amended 2026-10-01. Synthetic regions; no network."""

from __future__ import annotations

from pathlib import Path

import pytest

from hammunition.backends.fstopo import FsTopoResolution, RegionSheets, render_record
from hammunition.backends.topo import TIF
from hammunition.fstopo import (
    GATEWAY,
    FsPin,
    FstopoError,
    GatewayProbe,
    map_url,
    parse_index,
    parse_row,
)
from hammunition.geofabrik import GeofabrikError
from hammunition.topo_plan import poly_url, resolve_fstopo

ALPHA = parse_row("0 0 0.125 0.125 1230000 11 ZZ Alpha")
BETA = parse_row("0 0.125 0.125 0.25 1230001 0 ZZ Beta")
FAR = parse_row("10 10 10.125 10.125 1230002 11 ZZ Far")
INDEX = parse_index(
    "\n".join(
        r
        for r in (
            "0 0 0.125 0.125 1230000 11 ZZ Alpha",
            "0 0.125 0.125 0.25 1230001 0 ZZ Beta",
            "10 10 10.125 10.125 1230002 11 ZZ Far",
        )
    )
    + "\n"
)
OUTLINE = "oceania\n1\n 0.05 0.05\n 0.2 0.05\n 0.2 0.1\n 0.05 0.1\nEND\nEND\n"
ABROAD = "lemuria\n1\n 50.05 50.05\n 50.2 50.05\n 50.2 50.1\nEND\nEND\n"
OCEANIA = ("atlantis/oceania", "atlantis-oceania")
LEMURIA = ("atlantis/lemuria", "atlantis-lemuria")


class RegionProbe:
    def __init__(self, texts: dict[str, str]) -> None:
        self.texts = texts
        self.asked: list[str] = []

    def head(self, url: str) -> tuple[int, int, str | None]:  # pragma: no cover
        raise AssertionError("FSTopo never HEADs Geofabrik")

    def text(self, url: str) -> str:
        self.asked.append(url)
        if url not in self.texts:
            raise GeofabrikError(f"{url} could not be fetched: offline")
        return self.texts[url]


def _file(secoord: int) -> str:
    return f"{GATEWAY}data3/00000/fstopo/{secoord}.tiff"


class Head:
    def __init__(self, sizes: dict[int, int]) -> None:
        self.sizes = sizes
        self.asked: list[str] = []

    def __call__(self, url: str) -> tuple[int, int, str | None]:
        self.asked.append(url)
        for secoord, size in self.sizes.items():
            if url == map_url(secoord):
                return 302, 0, _file(secoord)
            if url == _file(secoord):
                return 200, size, None
        raise FstopoError(f"{url} could not be reached: offline")


def _resolve(
    tmp_path: Path,
    texts: dict[str, str],
    sizes: dict[int, int],
    *pairs: tuple[str, str],
    pins: dict[int, FsPin] | None = None,
) -> tuple[FsTopoResolution, tuple[str, ...], Head]:
    head = Head(sizes)
    resolution, notes = resolve_fstopo(
        list(pairs or (OCEANIA,)),
        installed=tmp_path,
        index=INDEX,
        pins=pins or {},
        region_probe=RegionProbe(texts),
        gateway=GatewayProbe(head),
    )
    return resolution, notes, head


def test_a_region_s_sheets_come_from_its_outline_and_each_is_located(tmp_path: Path) -> None:
    resolution, notes, head = _resolve(
        tmp_path, {poly_url(OCEANIA[0]): OUTLINE}, {1230000: 21, 1230001: 22}
    )
    assert resolution.regions == (RegionSheets(*OCEANIA, (ALPHA, BETA)),)
    fetch = resolution.fetch
    assert [(f.quad, f.url, f.size, f.sha256) for f in fetch] == [
        (ALPHA, _file(1230000), 21, None),
        (BETA, _file(1230001), 22, None),
    ]
    assert notes == ()
    # Four sheets at a time: the order across sheets is the scheduler's.
    assert sorted(head.asked) == sorted(
        [map_url(1230000), _file(1230000), map_url(1230001), _file(1230001)]
    )


def test_a_pin_is_used_and_a_pin_whose_size_changed_is_refused(tmp_path: Path) -> None:
    pins = {1230000: FsPin(1230000, 21, "a" * 64)}
    resolution, _, _ = _resolve(
        tmp_path, {poly_url(OCEANIA[0]): OUTLINE}, {1230000: 21, 1230001: 22}, pins=pins
    )
    assert resolution.fetch[0].sha256 == "a" * 64
    with pytest.raises(FstopoError, match=r"--pin"):
        _resolve(tmp_path, {poly_url(OCEANIA[0]): OUTLINE}, {1230000: 99, 1230001: 22}, pins=pins)


def test_a_region_with_no_sheet_is_noted_and_not_refused(tmp_path: Path) -> None:
    resolution, _, head = _resolve(tmp_path, {poly_url(LEMURIA[0]): ABROAD}, {}, LEMURIA)
    assert resolution.regions == (RegionSheets(*LEMURIA, ()),)
    assert head.asked == []


def test_installed_sheets_with_a_record_need_no_network(tmp_path: Path) -> None:
    (tmp_path / f"{OCEANIA[1]}.quads").write_text(render_record(RegionSheets(*OCEANIA, (ALPHA,))))
    (tmp_path / f"{ALPHA.name}{TIF}").write_bytes(b"II*\x00")
    resolution, _, head = _resolve(tmp_path, {}, {})
    assert resolution.current == (ALPHA,) and resolution.fetch == ()
    assert head.asked == []


def test_offline_every_unresolvable_item_is_named_together(tmp_path: Path) -> None:
    with pytest.raises(FstopoError, match="2 FSTopo item"):
        _resolve(tmp_path, {poly_url(OCEANIA[0]): OUTLINE}, {})
