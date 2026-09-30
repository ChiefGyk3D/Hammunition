# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""US Topo sheets resolved before the plan prints, and how the plan says so.
D-068.

Synthetic regions with synthetic outlines and synthetic sheets near 0/0 only.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from hammunition.backends.topo import (
    RegionQuads,
    TopoDisclosure,
    TopoResolution,
    no_quads_line,
    render_record,
)
from hammunition.copernicus import UNPINNED, CopernicusError
from hammunition.geofabrik import GeofabrikError
from hammunition.interface.plan import _render_topo, _topo_section
from hammunition.topo_plan import MemoProbe, poly_url, resolve_topo
from hammunition.ustopo import Quad, UstopoError, parse_index

MD5 = "0123456789abcdef0123456789abcdef"
ALPHA = Quad(0.0, 0.0, 0.125, 0.125, 9_000_000, MD5, "ZZ/ZZ_Alpha_20240101")
BETA = Quad(0.0, 0.125, 0.125, 0.25, 8_000_000, f"{MD5}-2", "ZZ/ZZ_Beta_20240101")
FAR = Quad(10.0, 10.0, 10.125, 10.125, 7_000_000, MD5, "ZZ/ZZ_Far_20240101")
NEWER = Quad(0.0, 0.0, 0.125, 0.125, 9_100_000, MD5, "ZZ/ZZ_Alpha_20260606")
INDEX = parse_index(
    "\n".join(
        f"{q.south} {q.west} {q.north} {q.east} {q.size} {q.etag} {q.path}"
        for q in (ALPHA, BETA, FAR)
    )
)
#: Touches Alpha's and Beta's cells, nothing else.
OUTLINE = "oceania\n1\n 0.05 0.05\n 0.2 0.05\n 0.2 0.1\n 0.05 0.1\nEND\nEND\n"
#: Far from every sheet: a region outside the United States.
ABROAD = "lemuria\n1\n 50.05 50.05\n 50.2 50.05\n 50.2 50.1\nEND\nEND\n"
OCEANIA = ("atlantis/oceania", "atlantis-oceania")
LEMURIA = ("atlantis/lemuria", "atlantis-lemuria")


class RegionProbe:
    def __init__(self, texts: dict[str, str]) -> None:
        self.texts = texts
        self.asked: list[str] = []

    def head(self, url: str) -> tuple[int, int, str | None]:  # pragma: no cover
        raise AssertionError("US Topo never HEADs Geofabrik")

    def text(self, url: str) -> str:
        self.asked.append(url)
        if url not in self.texts:
            raise GeofabrikError(f"{url} could not be fetched: offline")
        return self.texts[url]


class QuadProbe:
    def __init__(self, heads: dict[str, tuple[int, int, str | None]]) -> None:
        self.heads = heads
        self.asked: list[str] = []

    def head(self, url: str) -> tuple[int, int, str | None]:
        self.asked.append(url)
        if url not in self.heads:
            raise CopernicusError(f"{url} could not be reached: offline")
        return self.heads[url]


def _ok(*quads: Quad) -> dict[str, tuple[int, int, str | None]]:
    return {q.url: (200, q.size, f'"{q.etag}"') for q in quads}


def _resolve(
    tmp_path: Path, regions: RegionProbe, quads: QuadProbe, *pairs: tuple[str, str]
) -> tuple[TopoResolution, tuple[str, ...]]:
    return resolve_topo(
        list(pairs or (OCEANIA,)),
        installed=tmp_path,
        index=INDEX,
        region_probe=regions,
        quad_probe=quads,
    )


def test_a_new_region_is_resolved_from_its_outline_and_each_sheet_by_head(
    tmp_path: Path,
) -> None:
    regions = RegionProbe({poly_url("atlantis/oceania"): OUTLINE})
    quads = QuadProbe(_ok(ALPHA, BETA))
    got, notes = _resolve(tmp_path, regions, quads)
    assert got.regions == (RegionQuads(*OCEANIA, (ALPHA, BETA)),)
    assert got.fetch == (ALPHA, BETA) and got.current == ()
    assert quads.asked == [ALPHA.url, BETA.url]
    assert notes == ()


def test_a_recorded_region_with_every_sheet_installed_needs_no_network(tmp_path: Path) -> None:
    entry = RegionQuads(*OCEANIA, (ALPHA, BETA))
    (tmp_path / "atlantis-oceania.quads").write_text(render_record(entry))
    for quad in (ALPHA, BETA):
        (tmp_path / f"{quad.name}.tif").write_bytes(b"x")
    regions, quads = RegionProbe({}), QuadProbe({})
    got, _ = _resolve(tmp_path, regions, quads)
    assert got.regions == (entry,) and got.current == (ALPHA, BETA) and got.fetch == ()
    assert regions.asked == [] and quads.asked == []


def test_a_region_outside_the_us_gets_no_sheet_and_is_not_refused(tmp_path: Path) -> None:
    regions = RegionProbe({poly_url("atlantis/lemuria"): ABROAD})
    got, _ = _resolve(tmp_path, regions, QuadProbe({}), LEMURIA)
    assert got.regions == (RegionQuads(*LEMURIA, ()),)
    assert got.fetch == ()


def test_a_sheet_the_bucket_changed_is_refused_by_name(tmp_path: Path) -> None:
    regions = RegionProbe({poly_url("atlantis/oceania"): OUTLINE})
    heads = _ok(ALPHA, BETA)
    heads[BETA.url] = (200, BETA.size, '"ffffffffffffffffffffffffffffffff"')
    with pytest.raises(UstopoError, match="ZZ_Beta_20240101") as excinfo:
        _resolve(tmp_path, regions, QuadProbe(heads))
    assert "gen_ustopo_index.py --fetch" in str(excinfo.value)


def test_offline_every_unresolvable_region_and_sheet_is_named_together(tmp_path: Path) -> None:
    regions = RegionProbe({poly_url("atlantis/oceania"): OUTLINE})
    with pytest.raises(UstopoError) as excinfo:
        _resolve(tmp_path, regions, QuadProbe({}), OCEANIA, LEMURIA)
    message = str(excinfo.value)
    assert message.startswith("3 US Topo item(s)")
    assert "atlantis/lemuria" in message and "ZZ_Alpha" in message and "ZZ_Beta" in message


def test_a_record_naming_an_edition_the_index_no_longer_carries_is_reselected(
    tmp_path: Path,
) -> None:
    # The record names an older Alpha; the index carries only Alpha 2024.
    old = Quad(0.0, 0.0, 0.125, 0.125, 5, MD5, "ZZ/ZZ_Alpha_20200101")
    (tmp_path / "atlantis-oceania.quads").write_text(
        render_record(RegionQuads(*OCEANIA, (old, BETA)))
    )
    regions = RegionProbe({poly_url("atlantis/oceania"): OUTLINE})
    got, notes = _resolve(tmp_path, regions, QuadProbe(_ok(ALPHA, BETA)))
    assert [q.path for q in got.regions[0].quads] == [ALPHA.path, BETA.path]
    assert notes == ()


def test_offline_a_stale_record_is_kept_with_a_note(tmp_path: Path) -> None:
    old = Quad(0.0, 0.0, 0.125, 0.125, 5, MD5, "ZZ/ZZ_Alpha_20200101")
    entry = RegionQuads(*OCEANIA, (old,))
    (tmp_path / "atlantis-oceania.quads").write_text(render_record(entry))
    (tmp_path / f"{old.name}.tif").write_bytes(b"x")
    got, notes = _resolve(tmp_path, RegionProbe({}), QuadProbe({}))
    assert got.regions == (entry,) and got.current == (old,)
    assert len(notes) == 1 and "installed quads are kept" in notes[0]


def test_one_plan_asks_for_an_outline_once() -> None:
    inner = RegionProbe({poly_url("atlantis/oceania"): OUTLINE})
    memo = MemoProbe(inner)
    assert memo.text(poly_url("atlantis/oceania")) == memo.text(poly_url("atlantis/oceania"))
    assert inner.asked == [poly_url("atlantis/oceania")]
    with pytest.raises(GeofabrikError):
        memo.text(poly_url("atlantis/lemuria"))
    with pytest.raises(GeofabrikError):
        memo.text(poly_url("atlantis/lemuria"))
    assert inner.asked.count(poly_url("atlantis/lemuria")) == 2, "a failure is not remembered"


# ---------------------------------------------------------------------------
# What the plan prints
# ---------------------------------------------------------------------------


def test_the_plan_names_each_sheet_its_size_and_how_it_is_verified() -> None:
    resolution = TopoResolution(
        regions=(RegionQuads(*OCEANIA, (ALPHA, BETA)), RegionQuads(*LEMURIA, ())),
        fetch=(ALPHA,),
        current=(BETA,),
    )
    view = _topo_section(
        TopoDisclosure(
            resolution=resolution,
            licence="Public domain (USGS)",
            licence_url="https://www.usgs.gov/",
            warp=(ALPHA,),
            building=True,
        )
    )
    assert view is not None
    lines = _render_topo(view)
    text = "\n".join(lines)
    assert lines[0] == "  US Topo, USGS 7.5-minute quads (D-068):"
    assert "atlantis/oceania  2 quad(s), 17.0 MB; 9.0 MB to download" in text
    assert f"note: {no_quads_line('atlantis/lemuria')}" in text
    assert f"ZZ_Alpha_20240101     9.0 MB  {UNPINNED}" in text
    assert "already installed: 1 quad(s)" in text
    assert "licence: Public domain (USGS), stated at https://www.usgs.gov/" in text
    assert "warped for QMapShack: 1 quad(s), about 9.0 MB (1.0x each download" in text
    assert "about 18.0 MB of disk for US Topo (measured on one quad)" in text
    assert view.no_quads == ("atlantis/lemuria",)
    assert [r.region for r in view.regions] == ["atlantis/oceania"]
