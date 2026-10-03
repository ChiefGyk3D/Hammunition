# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""The bound on the topographic selection: a radius around the home square by
default, ``--topo-regions``, ``--topo-all``, the size consent above 10 GB and
the walk-through line.  D-068 (amended 2026-10-02), issue #232.

Synthetic sheets and a placeholder grid square (FN31pr) only; no network.
"""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest

from hammunition.backends.topo import (
    RegionQuads,
    TopoDisclosure,
    TopoResolution,
    read_record,
    render_record,
)
from hammunition.consent import (
    TOPO_SIZE_ENV,
    ConsentDeclined,
    ConsentUnavailable,
    resolve_topo_size_consent,
)
from hammunition.maidenhead import centre
from hammunition.station import Station, StationError, load_station, save_station
from hammunition.topo_bound import (
    ALL,
    CONSENT_BYTES,
    BoundUnavailable,
    TopoBound,
    bound_line,
    distance_km,
    make_bound,
    split_bound,
)
from hammunition.topo_plan import (
    outside_installed,
    resolve_topo,
    selection_note,
    size_consent,
    topo_size,
)
from hammunition.ustopo import Quad, QuadIndex

cli = importlib.import_module("hammunition.cli.main")

GRID = "FN31pr"
MD5 = "0123456789abcdef0123456789abcdef"
STEP = 0.125  # a 7.5-minute sheet


def _fixture_index() -> QuadIndex:
    """576 sheets, a 24 x 24 grid of 7.5-minute boxes over 3 x 3 degrees that
    contain the placeholder square's centre (40.0..43.0 N, 74.0..71.0 W)."""
    quads = []
    for i in range(24):
        for j in range(24):
            south, west = 40.0 + i * STEP, -74.0 + j * STEP
            quads.append(
                Quad(
                    south,
                    west,
                    south + STEP,
                    west + STEP,
                    9_000_000,
                    MD5,
                    f"ZZ/ZZ_S{i:02d}x{j:02d}_20240101",
                )
            )
    return QuadIndex.of(quads)


INDEX = _fixture_index()
OUTLINE = "fixture\n1\n -74.0 40.0\n -71.0 40.0\n -71.0 43.0\n -74.0 43.0\nEND\nEND\n"


class _Outlines:
    def __init__(self) -> None:
        self.asked: list[str] = []

    def head(self, url: str) -> tuple[int, int, str | None]:  # pragma: no cover
        raise AssertionError("never HEADs Geofabrik")

    def text(self, url: str) -> str:
        self.asked.append(url)
        return OUTLINE


class _Bucket:
    def head(self, url: str) -> tuple[int, int, str | None]:
        return 200, 9_000_000, f'"{MD5}"'


REGION = ("north-america/us/fixture", "north-america-us-fixture")
OTHER = ("north-america/us/other", "north-america-us-other")


def _bound(**kw: object) -> TopoBound:
    base: dict[str, object] = {
        "radius_km": None,
        "regions": (),
        "everything": None,
        "grid_square": GRID,
    }
    return make_bound(**{**base, **kw})  # type: ignore[arg-type]


def _resolve(
    tmp_path: Path, bound: TopoBound, *regions: tuple[str, str], probe: _Outlines | None = None
) -> TopoResolution:
    got, _ = resolve_topo(
        list(regions or (REGION,)),
        installed=tmp_path,
        index=INDEX,
        region_probe=probe or _Outlines(),
        quad_probe=_Bucket(),
        bound=bound,
    )
    return got


# ---- the arithmetic -------------------------------------------------------


def test_a_degree_of_latitude_is_about_111_km() -> None:
    assert distance_km(40.0, -73.0, 41.0, -73.0) == pytest.approx(111.19, abs=0.1)
    assert distance_km(40.0, -73.0, 40.0, -73.0) == 0.0


def test_the_default_is_100_km_around_the_grid_squares_centre() -> None:
    bound = _bound()
    assert bound.mode == "radius" and bound.radius_km == 100
    assert bound.centre == centre(GRID)


def test_precedence_all_then_regions_then_zero_then_the_circle() -> None:
    assert _bound(everything=True, radius_km=5, regions=("a",)).mode == "all"
    assert _bound(regions=("a",)).mode == "regions"
    assert _bound(regions=("a",), radius_km=50).mode == "radius"
    assert _bound(radius_km=0).mode == "none"
    assert _bound(radius_km=0, regions=("a",)).mode == "none"
    assert _bound(everything=False).mode == "radius"


def test_a_circle_with_no_grid_square_is_unavailable_but_everything_is_not() -> None:
    with pytest.raises(BoundUnavailable, match="grid square"):
        _bound(grid_square=None)
    assert _bound(grid_square=None, everything=True).mode == "all"
    assert _bound(grid_square=None, radius_km=0).mode == "none"
    assert _bound(grid_square=None, regions=("a",)).mode == "regions"


def test_the_token_never_carries_the_position_and_whole_regions_share_one() -> None:
    assert _bound(everything=True).token == _bound(regions=("a",)).token == "all"
    assert _bound(radius_km=0).token == "none"
    token = _bound().token
    assert token.startswith("r") and GRID.lower() not in token.lower()
    assert str(centre(GRID)[0])[:5] not in token
    assert _bound(radius_km=50).token != token
    assert _bound(grid_square="FN32pr").token != token


def test_a_box_is_kept_when_any_part_of_it_is_within_the_radius() -> None:
    here = _bound(radius_km=10)
    lat, lon = centre(GRID)
    inside = Quad(lat - 0.01, lon - 0.01, lat + 0.01, lon + 0.01, 1, MD5, "ZZ/ZZ_In_20240101")
    # 0.2 degrees of latitude is about 22 km north of the box's edge.
    clear = Quad(lat + 0.2, lon - 0.01, lat + 0.3, lon + 0.01, 1, MD5, "ZZ/ZZ_Out_20240101")
    assert here.keeps(inside) and not here.keeps(clear)
    assert _bound(radius_km=25).keeps(clear)


# ---- the selection over a synthetic index ---------------------------------


def test_100_km_selects_a_few_hundred_of_the_576_and_all_selects_every_one(
    tmp_path: Path,
) -> None:
    radius = _resolve(tmp_path, _bound())
    everything = _resolve(tmp_path, ALL)
    assert len(everything.fetch) == 576
    # A 100 km circle is about 31,000 km2 and a sheet about 145 km2 here.
    assert 200 <= len(radius.fetch) <= 260
    assert set(radius.fetch) < set(everything.fetch)
    lat, lon = centre(GRID)
    assert any(q.south <= lat <= q.north and q.west <= lon <= q.east for q in radius.fetch)
    assert all(
        distance_km(
            lat,
            lon,
            min(max(lat, q.south), q.north),
            min(max(lon, q.west), q.east),
        )
        <= 100
        for q in radius.fetch
    )
    # The corner of the fixture is 200 km and more away.
    assert not any(q.path.endswith("S00x00_20240101") for q in radius.fetch)


def test_the_selection_grows_with_the_radius(tmp_path: Path) -> None:
    counts = [len(_resolve(tmp_path, _bound(radius_km=r)).fetch) for r in (10, 50, 100, 200)]
    assert counts == sorted(counts) and counts[0] < counts[-1]


def test_zero_selects_nothing_and_asks_for_no_outline(tmp_path: Path) -> None:
    probe = _Outlines()
    got = _resolve(tmp_path, _bound(radius_km=0), probe=probe)
    assert got.regions == () and got.fetch == () and probe.asked == []


def test_topo_regions_narrows_to_those_regions_whole(tmp_path: Path) -> None:
    probe = _Outlines()
    bound = _bound(regions=(REGION[0],))
    got = _resolve(tmp_path, bound, REGION, OTHER, probe=probe)
    assert [r.region for r in got.regions] == [REGION[0]]
    assert len(got.fetch) == 576
    assert len(probe.asked) == 1


def test_topo_regions_with_a_radius_cuts_the_circle_to_them(tmp_path: Path) -> None:
    bound = _bound(regions=(REGION[0],), radius_km=100)
    got = _resolve(tmp_path, bound, REGION, OTHER)
    assert [r.region for r in got.regions] == [REGION[0]]
    assert 200 <= len(got.fetch) <= 260


# ---- records are kept per bound -------------------------------------------


def test_a_record_carries_its_bound_and_an_old_one_reads_as_the_whole_region(
    tmp_path: Path,
) -> None:
    bound = _bound()
    got = _resolve(tmp_path, bound)
    entry = got.regions[0]
    assert entry.bound == bound.token
    assert bound_line(bound.token) in render_record(entry)
    path = tmp_path / f"{REGION[1]}.quads"
    path.write_text(render_record(entry))
    assert read_record(path, *REGION) == entry
    whole = RegionQuads(*REGION, entry.quads)
    assert "# bound:" not in render_record(whole)
    path.write_text(render_record(whole))
    assert read_record(path, *REGION) == whole and whole.bound == "all"
    assert split_bound(["a", "# bound: r1", "b"]) == ("r1", ["a", "b"])


def test_a_record_is_reused_only_under_the_bound_it_was_made_under(tmp_path: Path) -> None:
    bound = _bound()
    first = _resolve(tmp_path, bound)
    (tmp_path / f"{REGION[1]}.quads").write_text(render_record(first.regions[0]))
    for quad in first.fetch:
        (tmp_path / f"{quad.name}.tif").write_bytes(b"x")
    probe = _Outlines()
    again = _resolve(tmp_path, bound, probe=probe)
    assert probe.asked == [] and again.current == first.fetch
    # --topo-all must not read the radius's record as the whole region.
    widened = _resolve(tmp_path, ALL, probe=probe)
    assert probe.asked and len(widened.regions[0].quads) == 576
    # Nor a different radius.
    probe2 = _Outlines()
    narrower = _resolve(tmp_path, _bound(radius_km=30), probe=probe2)
    assert probe2.asked and len(narrower.regions[0].quads) < len(first.regions[0].quads)


def test_offline_a_whole_region_on_record_narrows_to_the_bound_without_an_outline(
    tmp_path: Path,
) -> None:
    whole = RegionQuads(*REGION, tuple(INDEX.quads))
    (tmp_path / f"{REGION[1]}.quads").write_text(render_record(whole))

    class Offline(_Outlines):
        def text(self, url: str) -> str:
            raise OSError("offline")

    got = _resolve(tmp_path, _bound(), probe=Offline())
    assert 200 <= len(got.regions[0].quads) <= 260 and got.regions[0].bound == _bound().token


def test_installed_sheets_outside_the_selection_are_counted(tmp_path: Path) -> None:
    got = _resolve(tmp_path, _bound())
    for quad in INDEX.quads:
        (tmp_path / f"{quad.name}.tif").write_bytes(b"x")
    assert outside_installed(tmp_path, got) == 576 - len(got.fetch)
    assert outside_installed(tmp_path, _resolve(tmp_path, ALL)) == 0


# ---- the note and the size ------------------------------------------------


def test_the_walk_through_line_says_what_was_chosen_and_how_to_change_it(
    tmp_path: Path,
) -> None:
    bound = _bound()
    got = _resolve(tmp_path, bound)
    note = selection_note(bound, got)
    assert note.startswith("US Topo: using a 100 km radius around your grid square (")
    assert f"({len(got.wanted):,} sheets, about " in note
    assert "`hammunition station set --topo-radius-km`" in note
    assert "`--topo-regions` or `--topo-all` change this" in note
    assert GRID not in note
    assert "installed sheets lie outside" in selection_note(bound, got, outside=3)
    assert "every sheet of every region" in selection_note(ALL, got)


def _disclosure(sheets: int, *, everything: bool = False, size: int = 9_000_000) -> TopoDisclosure:
    quads = tuple(
        Quad(0.0, i * STEP, STEP, (i + 1) * STEP, size, MD5, f"ZZ/ZZ_Q{i:05d}_20240101")
        for i in range(sheets)
    )
    return TopoDisclosure(
        resolution=TopoResolution(fetch=quads),
        licence="PD",
        licence_url="u",
        warp=quads,
        everything=everything,
    )


def test_the_size_sentence_names_the_count_the_download_and_the_disk() -> None:
    size = topo_size(_disclosure(7284, size=7_550_000))
    assert size is not None and size.count == 7284
    sentence = size.sentence()
    assert sentence.startswith("This installs 7,284 US Topo sheets: about ")
    assert "to download and about " in sentence and "of disk" in sentence
    assert size.disk == 2 * size.download


def test_over_10_gb_or_topo_all_asks_and_a_small_bounded_selection_does_not() -> None:
    assert size_consent(_disclosure(240)) is None
    assert size_consent(_disclosure(0)) is None and size_consent(None) is None
    # 600 x 9 MB x 2 = 10.8 GB
    big = size_consent(_disclosure(600))
    assert big is not None and big.disk > CONSENT_BYTES
    assert size_consent(_disclosure(500)) is None  # 9 GB
    assert size_consent(_disclosure(3, everything=True)) is not None
    assert size_consent(_disclosure(0, everything=True)) is None  # nothing to download


# ---- the consent machinery ------------------------------------------------


SENTENCE = "This installs 7,284 US Topo sheets: about 55 GB to download and about 111 GB of disk."


def test_yes_cannot_satisfy_the_size_and_silence_is_not_consent() -> None:
    with pytest.raises(ConsentUnavailable, match="--yes does not satisfy"):
        resolve_topo_size_consent(SENTENCE, 7284, environ={}, prompt=None, assume_yes=True)


def test_the_environment_answer_names_the_sheet_count_and_a_bare_1_is_refused() -> None:
    record = resolve_topo_size_consent(
        SENTENCE, 7284, environ={TOPO_SIZE_ENV: "7284"}, prompt=None, assume_yes=False
    )
    assert record.decision.value == "environment" and record.extra["sheets"] == "7284"
    assert record.to_log_entry()["event"] == "consent_affirmed"
    with pytest.raises(ConsentUnavailable, match=f"{TOPO_SIZE_ENV}=7284"):
        resolve_topo_size_consent(SENTENCE, 7284, environ={TOPO_SIZE_ENV: "1"}, prompt=None)
    with pytest.raises(ConsentUnavailable):
        resolve_topo_size_consent(SENTENCE, 7285, environ={TOPO_SIZE_ENV: "7284"}, prompt=None)


def test_the_typed_answer_is_recorded_with_the_text_shown_and_no_is_declined() -> None:
    shown: list[str] = []

    def yes(text: str) -> bool:
        shown.append(text)
        return True

    record = resolve_topo_size_consent(SENTENCE, 7284, environ={}, prompt=yes)
    assert record.decision.value == "interactive" and SENTENCE in shown[0]
    assert record.disclosure_text == shown[0] and "station set --topo-radius-km" in shown[0]
    with pytest.raises(ConsentDeclined):
        resolve_topo_size_consent(SENTENCE, 7284, environ={}, prompt=lambda _t: False)


# ---- the station values ---------------------------------------------------


def test_the_three_values_round_trip_and_default_when_unset(tmp_path: Path) -> None:
    assert Station().topo_radius == 100
    station = Station(
        map_regions=("a/b", "c/d"), topo_radius_km=0, topo_regions=("c/d",), topo_all=False
    )
    path = tmp_path / "station.yml"
    save_station(station, path=path)
    assert load_station(path=path) == station
    assert station.as_dict()["topo_radius_km"] == 0 and station.as_dict()["topo_all"] is False
    assert Station().as_dict() == {}


def test_topo_regions_must_be_a_subset_of_the_map_regions() -> None:
    with pytest.raises(StationError, match="subset of the station's map regions"):
        Station(map_regions=("a/b",), topo_regions=("c/d",))
    with pytest.raises(StationError, match="subset"):
        Station(topo_regions=("a/b",))


def test_a_negative_or_absurd_radius_is_refused() -> None:
    for bad in (-1, 20001):
        with pytest.raises(StationError, match="outside 0 to 20000"):
            Station(topo_radius_km=bad)


def _env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.delenv("SUDO_USER", raising=False)
    monkeypatch.setenv("USER", "op")
    return tmp_path / "hammunition" / "station.yml"


def test_station_set_takes_the_three_flags_and_refuses_a_region_that_is_not_set(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = _env(monkeypatch, tmp_path)
    assert cli.main(["station", "set", "--map-regions", "a/b,c/d"]) == 0
    assert cli.main(["station", "set", "--topo-radius-km", "0"]) == 0
    assert load_station(path=path).topo_radius_km == 0
    assert cli.main(["station", "set", "--topo-regions", "c/d", "--topo-all"]) == 0
    saved = load_station(path=path)
    assert saved.topo_regions == ("c/d",) and saved.topo_all is True
    assert saved.topo_radius_km == 0 and saved.map_regions == ("a/b", "c/d")
    assert cli.main(["station", "set", "--no-topo-all"]) == 0
    assert load_station(path=path).topo_all is False
    capsys.readouterr()
    assert cli.main(["station", "set", "--topo-regions", "x/y"]) == 1
    assert "subset of the station's map regions" in capsys.readouterr().err
    assert cli.main(["station", "set", "--topo-regions", " , "]) == 1
    assert cli.main(["station", "set", "--topo-radius-km", "-5"]) == 1


def test_station_show_prints_the_three_values_and_only_counts_the_regions(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = _env(monkeypatch, tmp_path)
    assert cli.main(["station", "show"]) == 0
    text = capsys.readouterr().out
    assert "topo radius    100 km (the default)" in text and "topo all       no" in text
    save_station(
        Station(map_regions=("a/b",), topo_radius_km=40, topo_regions=("a/b",), topo_all=True),
        path=path,
    )
    assert cli.main(["station", "show"]) == 0
    text = capsys.readouterr().out
    assert "topo radius    40 km" in text and "topo regions   1 set" in text
    assert "topo all       yes" in text and "a/b" not in text.replace(str(tmp_path), "")


# ---- FSTopo and 3DEP follow the same bound --------------------------------


def test_fstopo_sheets_follow_the_bound() -> None:
    from hammunition.fstopo import GATEWAY, FsQuad, map_url, parse_index
    from hammunition.topo_plan import resolve_fstopo

    rows = []
    for i in range(24):
        for j in range(24):
            south, west = 40.0 + i * STEP, -74.0 + j * STEP
            rows.append(
                f"{south} {west} {south + STEP} {west + STEP} {1230000 + i * 24 + j} 11 ZZ C{i}x{j}"
            )
    index = parse_index("\n".join(rows) + "\n")

    class Gateway:
        def __call__(self, url: str) -> tuple[int, int, str | None]:
            for secoord in range(1230000, 1230000 + 576):
                if url == map_url(secoord):
                    return 302, 0, f"{GATEWAY}data3/00000/fstopo/{secoord}.tiff"
            return 200, 1_000_000, None

    from hammunition.fstopo import GatewayProbe

    def run(bound: TopoBound) -> list[FsQuad]:
        got, _ = resolve_fstopo(
            [REGION],
            installed=Path("/nonexistent"),
            index=index,
            pins={},
            region_probe=_Outlines(),
            gateway=GatewayProbe(Gateway()),
            bound=bound,
        )
        return [f.quad for f in got.fetch]

    assert len(run(ALL)) == 576
    assert 200 <= len(run(_bound())) <= 260
    assert run(_bound(radius_km=0)) == []


def test_3dep_tiles_follow_the_bound_and_keep_their_unpublished_count(tmp_path: Path) -> None:
    from hammunition.terrain_plan import resolve_bare_earth
    from hammunition.usgs3dep import parse_tile_list, tile_url

    names = [f"USGS_13_n{n:02d}w{w:03d}" for n in range(41, 44) for w in range(71, 75)]
    tiles = parse_tile_list("".join(f"{n} 12 {MD5}\n" for n in names))
    heads = {tile_url(n): (200, 12, f'"{MD5}"') for n in names}

    class Heads:
        def head(self, url: str) -> tuple[int, int, str | None]:
            return heads[url]

    def run(bound: TopoBound, where: Path) -> object:
        return resolve_bare_earth(
            [REGION],
            installed=where,
            tiles=tiles,
            region_probe=_Outlines(),
            tile_probe=Heads(),
            bound=bound,
        )

    everything = run(ALL, tmp_path)
    near = run(_bound(radius_km=60), tmp_path)
    assert len(everything.fetch) == 12  # type: ignore[attr-defined]
    assert 0 < len(near.fetch) < 12  # type: ignore[attr-defined]
    assert run(_bound(radius_km=0), tmp_path).fetch == ()  # type: ignore[attr-defined]
    entry = near.regions[0]  # type: ignore[attr-defined]
    assert entry.bound == _bound(radius_km=60).token
    # Bounded-out tiles are not "unpublished": that count is the list's.
    assert entry.unpublished == everything.regions[0].unpublished  # type: ignore[attr-defined]


def test_narrowing_the_map_regions_drops_topo_regions_that_are_gone_and_they_can_be_cleared(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = _env(monkeypatch, tmp_path)
    assert cli.main(["station", "set", "--map-regions", "a/b,c/d", "--topo-regions", "c/d"]) == 0
    assert cli.main(["station", "set", "--map-regions", "a/b"]) == 0
    assert "dropped" in capsys.readouterr().out
    assert load_station(path=path).topo_regions == ()
    assert cli.main(["station", "set", "--map-regions", "a/b,c/d", "--topo-regions", "a/b"]) == 0
    assert cli.main(["station", "set", "--clear-topo-regions"]) == 0
    assert load_station(path=path).topo_regions == ()


def test_a_radius_must_be_a_whole_number_not_a_bool() -> None:
    for bad in (True, 100.5):
        with pytest.raises(StationError):
            Station(topo_radius_km=bad)  # type: ignore[arg-type]


def test_a_bound_out_3dep_region_is_not_called_unpublished() -> None:
    from hammunition.terrain_plan import resolve_bare_earth
    from hammunition.usgs3dep import parse_tile_list

    tiles = parse_tile_list(f"USGS_13_n41w074 12 {MD5}\n")

    class Heads:
        def head(self, url: str) -> tuple[int, int, str | None]:  # pragma: no cover
            raise AssertionError("nothing is selected")

    got = resolve_bare_earth(
        [REGION],
        installed=Path("/nonexistent"),
        tiles=tiles,
        region_probe=_Outlines(),
        tile_probe=Heads(),
        bound=_bound(radius_km=1, grid_square="FN20aa"),
    )
    assert got.regions[0].tiles == () and not got.regions[0].no_terrain
