# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""A data item the log attributes is not re-asked of its publisher at plan time
until its attribution is seven days old.  #197, D-049 (amended 2026-10-02).

Synthetic regions, tiles and logs; no network.
"""

from __future__ import annotations

import shutil
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from hammunition.attributed import (
    RECHECK_AFTER_DAYS,
    PublisherChecks,
    read_attributions,
)
from hammunition.backends.comaps_maps import map_dest, resolve_station_maps
from hammunition.backends.dem import RegionTiles, render_record
from hammunition.backends.kiwix import resolve_station_books
from hammunition.comaps import load_pins as load_comaps_pins
from hammunition.copernicus import CopernicusError, tile_url
from hammunition.fstopo import GatewayProbe
from hammunition.kiwix import load_book_list, load_pin_file
from hammunition.state import TransactionLog
from hammunition.terrain_plan import poly_url, resolve_terrain
from hammunition.topo_plan import resolve_fstopo, resolve_topo
from test_fstopo_plan import ALPHA as FS_ALPHA
from test_fstopo_plan import BETA as FS_BETA
from test_fstopo_plan import INDEX as FS_INDEX
from test_fstopo_plan import OCEANIA as FS_OCEANIA
from test_fstopo_plan import Head as FsHead
from test_fstopo_plan import RegionProbe as FsRegionProbe
from test_terrain_plan import LIST, MD5, OUTLINE, A, B, RegionProbe, TileProbe
from test_topo_plan import ALPHA as TOPO_ALPHA
from test_topo_plan import BETA as TOPO_BETA
from test_topo_plan import INDEX as TOPO_INDEX
from test_topo_plan import OCEANIA as TOPO_OCEANIA
from test_topo_plan import QuadProbe
from test_topo_plan import RegionProbe as TopoRegionProbe

NOW = datetime(2026, 10, 2, 12, 0, tzinfo=UTC)
FRESH = NOW - timedelta(days=1)
STALE = NOW - timedelta(days=10)
REPO_ROOT = Path(__file__).resolve().parent.parent
CATALOG = REPO_ROOT / "catalog"
OCEANIA = ("atlantis/oceania", "atlantis-oceania")


class FakeLog:
    def __init__(self, entries: list[dict[str, Any]]) -> None:
        self.entries = entries

    def read(self) -> list[dict[str, Any]]:
        return self.entries


def installed(path: Path, when: datetime, **facts: Any) -> dict[str, Any]:
    return {
        "event": "action_end",
        "kind": "install-data",
        "detail": str(path),
        "timestamp": when.isoformat(),
        **facts,
    }


def checks_for(entries: list[dict[str, Any]], *, recheck: bool = False) -> PublisherChecks:
    return PublisherChecks.from_log(FakeLog(entries), now=NOW, recheck=recheck)


# -- the helper -----------------------------------------------------------------


def test_the_constant_is_seven_days() -> None:
    assert RECHECK_AFTER_DAYS == 7


def test_attributions_carry_the_last_install_and_a_removal_takes_one_away() -> None:
    a, b = "/data/u/a.tif", "/data/u/b.tif"
    got = read_attributions(
        FakeLog(
            [
                installed(Path(a), STALE, size="5", digest="abc"),
                installed(Path(a), FRESH),
                installed(Path(b), FRESH),
                {"event": "action_end", "kind": "remove-data", "detail": b},
                {"event": "action_end", "kind": "install-data", "detail": "relative"},
                {"event": "command_end", "kind": "install-data", "detail": "/data/u/c.tif"},
            ]
        )
    )
    assert set(got) == {a}
    assert got[a].when == FRESH and got[a].size is None


def test_attributions_are_read_through_the_archives_in_order(tmp_path: Path) -> None:
    """A rotation moves old transactions into archives; the attribution lives on."""
    log = TransactionLog(path=tmp_path / "transactions.jsonl")
    tile = tmp_path / "t.tif"
    log.append({"event": "transaction_begin", "version": 2, "timestamp": STALE.isoformat()})
    log.append(installed(tile, STALE, size="1"))
    log.append({"event": "transaction_end", "version": 2, "timestamp": STALE.isoformat()})
    log.append({"event": "transaction_begin", "version": 2, "timestamp": FRESH.isoformat()})
    log.append({"event": "transaction_end", "version": 2, "timestamp": FRESH.isoformat()})
    assert log.rotate(threshold=0, keep=1) is not None
    assert log.archives()
    got = read_attributions(log)
    assert got[str(tile)].when == STALE and got[str(tile)].size == 1


def test_a_fresh_attribution_is_skipped_a_stale_one_is_due(tmp_path: Path) -> None:
    fresh, stale = tmp_path / "f.tif", tmp_path / "s.tif"
    checks = checks_for([installed(fresh, FRESH), installed(stale, STALE)])
    assert checks.due("u", "f", fresh) is False
    assert checks.due("u", "s", stale) is True
    by_item = {line.item: line for line in checks.lines}
    assert by_item["f"].checked is False and by_item["f"].attributed == "2026-10-01"
    assert "not re-checked (attributed 2026-10-01)" in by_item["f"].reason
    assert by_item["s"].checked is True and "more than 7 days" in by_item["s"].reason


def test_the_plan_says_how_many_were_skipped_and_the_oldest_date(tmp_path: Path) -> None:
    older = NOW - timedelta(days=5)
    one, two = tmp_path / "1.tif", tmp_path / "2.tif"
    checks = checks_for([installed(one, FRESH), installed(two, older)])
    checks.due("u", "1", one)
    checks.due("u", "2", two)
    [note] = checks.notes()
    assert note.startswith("2 installed data item(s) were not re-checked")
    assert "2026-09-27" in note and "--recheck" in note


def test_an_item_on_disk_but_not_attributed_keeps_the_old_behaviour(tmp_path: Path) -> None:
    path = tmp_path / "x.tif"
    checks = checks_for([])
    assert checks.due("u", "x", path) is False
    [line] = checks.lines
    assert line.checked is False and line.attributed is None and "not attributed" in line.reason
    assert checks.notes() == []


def test_recheck_asks_even_a_fresh_attribution(tmp_path: Path) -> None:
    path = tmp_path / "f.tif"
    assert checks_for([installed(path, FRESH)], recheck=True).due("u", "f", path) is True


def test_a_file_that_is_not_the_one_the_log_recorded_is_asked_again(tmp_path: Path) -> None:
    path = tmp_path / "f.tif"
    path.write_bytes(b"12345")
    same = checks_for([installed(path, FRESH, size="5")])
    assert same.due("u", "f", path) is False
    differs = checks_for([installed(path, FRESH, size="9")])
    assert differs.due("u", "f", path) is True
    assert "not the one the log recorded" in differs.lines[0].reason
    moved = checks_for([installed(path, FRESH, size="5", digest="old")])
    assert moved.due("u", "f", path, digest="new") is True


def test_a_failed_recheck_is_kept_on_its_line_and_named_in_the_notes(tmp_path: Path) -> None:
    path = tmp_path / "s.tif"
    checks = checks_for([installed(path, STALE)])
    assert checks.due("u", "s", path)
    checks.report("u", "s", "the publisher dropped it")
    [note] = checks.notes()
    assert "the publisher dropped it" in note and "installed copy is kept" in note


# -- terrain ---------------------------------------------------------------------


def _terrain_dir(tmp_path: Path) -> Path:
    (tmp_path / "atlantis-oceania.tiles").write_text(
        render_record(RegionTiles(*OCEANIA, (A, B), 0))
    )
    for name in (A, B):
        (tmp_path / f"{name}.tif").write_bytes(b"t")
    return tmp_path


def _terrain(tmp_path: Path, checks: PublisherChecks, tiles: TileProbe) -> Any:
    return resolve_terrain(
        [OCEANIA],
        installed=tmp_path,
        tile_list=LIST,
        pins={},
        region_probe=RegionProbe({poly_url(OCEANIA[0]): OUTLINE}),
        tile_probe=tiles,
        checks=checks,
    )


def test_terrain_a_fresh_tile_asks_nothing_and_a_stale_one_is_probed(tmp_path: Path) -> None:
    root = _terrain_dir(tmp_path)
    checks = checks_for([installed(root / f"{A}.tif", FRESH), installed(root / f"{B}.tif", STALE)])
    tiles = TileProbe({tile_url(B): (200, 39_000_000, f'"{MD5}"')})
    got = _terrain(root, checks, tiles)
    assert tiles.asked == [tile_url(B)]
    assert got.current == (A, B) and got.fetch == ()


def test_terrain_recheck_probes_both(tmp_path: Path) -> None:
    root = _terrain_dir(tmp_path)
    checks = checks_for(
        [installed(root / f"{A}.tif", FRESH), installed(root / f"{B}.tif", STALE)], recheck=True
    )
    ok: dict[str, tuple[int, int, str | None]] = {
        tile_url(n): (200, 39_000_000, f'"{MD5}"') for n in (A, B)
    }
    tiles = TileProbe(ok)
    _terrain(root, checks, tiles)
    assert sorted(tiles.asked) == sorted([tile_url(A), tile_url(B)])


def test_terrain_a_file_that_differs_from_its_attribution_is_probed(tmp_path: Path) -> None:
    root = _terrain_dir(tmp_path)
    checks = checks_for(
        [
            installed(root / f"{A}.tif", FRESH, size="99"),
            installed(root / f"{B}.tif", FRESH, size="1"),
        ]
    )
    tiles = TileProbe({tile_url(A): (200, 39_000_000, f'"{MD5}"')})
    _terrain(root, checks, tiles)
    assert tiles.asked == [tile_url(A)]


def test_terrain_a_failed_recheck_never_refuses_or_refetches(tmp_path: Path) -> None:
    root = _terrain_dir(tmp_path)
    checks = checks_for([installed(root / f"{A}.tif", STALE), installed(root / f"{B}.tif", FRESH)])
    got = _terrain(root, checks, TileProbe({}))  # offline: the probe raises
    assert got.current == (A, B) and got.fetch == () and got.deferred == ()
    assert any("installed copy is kept" in note for note in checks.notes())


def test_terrain_without_checks_behaves_as_before(tmp_path: Path) -> None:
    root = _terrain_dir(tmp_path)
    tiles = TileProbe({})
    got = resolve_terrain(
        [OCEANIA],
        installed=root,
        tile_list=LIST,
        pins={},
        region_probe=RegionProbe({}),
        tile_probe=tiles,
    )
    assert got.current == (A, B) and tiles.asked == []


def test_terrain_an_unattributed_tile_is_not_asked(tmp_path: Path) -> None:
    root = _terrain_dir(tmp_path)
    tiles = TileProbe({})
    _terrain(root, checks_for([]), tiles)
    assert tiles.asked == []


def test_terrain_a_failed_check_is_a_copernicus_error_only_for_a_missing_tile(
    tmp_path: Path,
) -> None:
    """A missing tile still refuses offline: only an installed one is spared."""
    (tmp_path / "atlantis-oceania.tiles").write_text(render_record(RegionTiles(*OCEANIA, (A,), 0)))
    with pytest.raises(CopernicusError):
        _terrain(tmp_path, checks_for([]), TileProbe({}))


# -- US Topo and FSTopo ----------------------------------------------------------


def test_topo_fresh_asks_nothing_stale_is_probed(tmp_path: Path) -> None:
    (tmp_path / f"{TOPO_ALPHA.name}.tif").write_bytes(b"x")
    (tmp_path / f"{TOPO_BETA.name}.tif").write_bytes(b"x")
    checks = checks_for(
        [
            installed(tmp_path / f"{TOPO_ALPHA.name}.tif", FRESH),
            installed(tmp_path / f"{TOPO_BETA.name}.tif", STALE),
        ]
    )
    quads = QuadProbe({TOPO_BETA.url: (200, TOPO_BETA.size, f'"{TOPO_BETA.etag}"')})
    got, _ = resolve_topo(
        [TOPO_OCEANIA],
        installed=tmp_path,
        index=TOPO_INDEX,
        region_probe=TopoRegionProbe({poly_url(TOPO_OCEANIA[0]): TOPO_OUTLINE}),
        quad_probe=quads,
        checks=checks,
    )
    assert quads.asked == [TOPO_BETA.url]
    assert got.current == (TOPO_ALPHA, TOPO_BETA) and got.fetch == ()


def test_fstopo_fresh_asks_nothing_stale_is_probed(tmp_path: Path) -> None:
    for quad in (FS_ALPHA, FS_BETA):
        (tmp_path / f"{quad.name}.tif").write_bytes(b"x")
    checks = checks_for(
        [
            installed(tmp_path / f"{FS_ALPHA.name}.tif", FRESH),
            installed(tmp_path / f"{FS_BETA.name}.tif", STALE),
        ]
    )
    head = FsHead({1230001: 22})
    got, _ = resolve_fstopo(
        [FS_OCEANIA],
        installed=tmp_path,
        index=FS_INDEX,
        pins={},
        region_probe=FsRegionProbe({poly_url(FS_OCEANIA[0]): FS_OUTLINE}),
        gateway=GatewayProbe(head),
        checks=checks,
    )
    assert head.asked and all("1230001" in url for url in head.asked)
    assert got.fetch == ()


# -- Kiwix books and CoMaps maps -------------------------------------------------

HAM = "ham.stackexchange.com_en_all"


def _books_catalog(tmp_path: Path) -> Path:
    root = tmp_path / "catalog"
    (root / "data").mkdir(parents=True)
    for name in ("kiwix-books.yaml", "kiwix-pins.yaml"):
        shutil.copy(CATALOG / "data" / name, root / "data" / name)
    return root


def _book_file(root: Path, directory: Path) -> Path:
    books = load_pin_file(root)
    assert load_book_list(root)  # the list is the catalog's own
    pin = books[HAM]
    path = directory / pin.file
    directory.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as handle:
        handle.truncate(pin.size)
    return path


def test_kiwix_fresh_asks_nothing_stale_and_recheck_ask(tmp_path: Path) -> None:
    root = _books_catalog(tmp_path)
    book = _book_file(root, tmp_path / "d")
    asked: list[str] = []

    def head(url: str) -> int:
        asked.append(url)
        return 200

    def run(entry_when: datetime, *, recheck: bool = False) -> None:
        checks = checks_for([installed(book, entry_when)], recheck=recheck)
        resolve_station_books((HAM,), root, installed=tmp_path / "d", head=head, checks=checks)

    run(FRESH)
    assert asked == []
    run(STALE)
    assert len(asked) == 1
    run(FRESH, recheck=True)
    assert len(asked) == 2


def test_kiwix_a_dropped_pin_on_an_installed_book_is_a_note_not_a_refusal(
    tmp_path: Path,
) -> None:
    root = _books_catalog(tmp_path)
    book = _book_file(root, tmp_path / "d")
    checks = checks_for([installed(book, STALE)])
    files = resolve_station_books(
        (HAM,), root, installed=tmp_path / "d", head=lambda url: 404, checks=checks
    )
    assert [f.pin.id for f in files] == [HAM]
    assert any("404" in note for note in checks.notes())


def test_comaps_fresh_asks_nothing_stale_is_probed(tmp_path: Path) -> None:
    pins = load_comaps_pins(CATALOG)
    root = tmp_path / "catalog"
    (root / "data").mkdir(parents=True)
    shutil.copy(CATALOG / "data" / "comaps-pins.yaml", root / "data" / "comaps-pins.yaml")
    mapfile = pins.maps["US_Delaware"]
    from hammunition.comaps import resolve_regions

    [f], _ = resolve_regions(("north-america/us/delaware",), pins)
    dest = map_dest(tmp_path / "d", f)
    dest.parent.mkdir(parents=True)
    with dest.open("wb") as handle:
        handle.truncate(mapfile.size)
    asked: list[str] = []

    def head(url: str) -> tuple[int, int]:
        asked.append(url)
        return 200, mapfile.size

    def run(when: datetime) -> None:
        resolve_station_maps(
            ("north-america/us/delaware",),
            root,
            installed=tmp_path / "d",
            head=head,
            checks=checks_for([installed(dest, when)]),
        )

    run(FRESH)
    assert asked == []
    run(STALE)
    assert len(asked) == 1


TOPO_OUTLINE = "oceania\n1\n 0.05 0.05\n 0.2 0.05\n 0.2 0.1\n 0.05 0.1\nEND\nEND\n"
FS_OUTLINE = TOPO_OUTLINE


# -- what the install records, and what is unchanged ---------------------------


def test_a_tile_install_records_the_size_the_next_plan_checks(tmp_path: Path) -> None:
    from hammunition.backends import Action
    from hammunition.backends.dem import DemResolution, DemTilesBackend
    from hammunition.copernicus import TileFile
    from hammunition.manifest.schema import DemTilesInstall
    from test_dem_backend import BODY, FakeFetcher
    from test_dem_backend import manifest as dem_manifest

    tile = TileFile(A, tile_url(A), len(BODY), None, "0" * 32)
    backend = DemTilesBackend(
        fetcher=FakeFetcher(tmp_path / "cache"),
        prefix=tmp_path,
        resolution=DemResolution(regions=(RegionTiles(*OCEANIA, (A,), 0),), fetch=(tile,)),
    )
    manifest = dem_manifest()
    block = manifest.install[0].install
    assert isinstance(block, DemTilesInstall)
    steps = backend.steps(manifest, block)
    [install] = [s for s in steps if isinstance(s, Action) and s.kind == "install-data"][:1]
    assert install.facts == {"size": str(len(BODY))}


def test_the_status_document_reads_the_same_with_or_without_the_new_facts() -> None:
    from hammunition.interface.status import _latest

    def log(**facts: Any) -> list[dict[str, Any]]:
        return [
            {"event": "transaction_begin", "version": 2, "timestamp": STALE.isoformat()},
            installed(Path("/data/u/a.tif"), STALE, **facts),
            {"event": "transaction_end", "version": 2, "timestamp": STALE.isoformat()},
        ]

    assert _latest(log()) == _latest(log(size="5", digest="abc"))


def test_install_has_a_recheck_flag() -> None:
    from hammunition.cli.main import build_parser

    parser = build_parser()
    assert parser.parse_args(["install", "station", "--recheck"]).recheck is True
    assert parser.parse_args(["install", "station"]).recheck is False
