# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""The plan's text groups repeated same-shape steps; ``--full`` expands them.  D-016.

Grouping is rendering only: the JSON document and the transaction log carry
every step, and ``--full`` prints every step as the plan always did. The
fixtures here are real backends fed synthetic items (made-up regions, sheets
and tiles); nothing touches a network, a disk outside ``tmp_path`` or root.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Sequence
from pathlib import Path

import pytest

import test_fstopo_backend as fstopo_tests
import test_gdal_dem as gdal_dem_tests
import test_kiwix_backend as kiwix_tests
import test_pmtiles as pmtiles_tests
import test_splat_sdf as splat_tests
import test_topo_mosaic as mosaic_tests
from hammunition.backends import Action, Command
from hammunition.backends.dem import (
    DemResolution,
    DemTilesBackend,
    RegionTiles,
)
from hammunition.backends.fstopo import FsTopoResolution, RegionSheets
from hammunition.backends.kiwix import KiwixBooksBackend
from hammunition.backends.splat_sdf import SplatSdfConverter
from hammunition.backends.topo import RegionQuads, TopoQuadsBackend, TopoResolution
from hammunition.copernicus import TileFile, tile_url
from hammunition.fetch import Fetcher
from hammunition.fstopo import FsQuadFile, parse_row
from hammunition.interface.plan import StepView, step_view
from hammunition.interface.plan_group import MIN_REPEATS, Group, group_steps, render_steps
from hammunition.kiwix import BookFile, BookPin
from hammunition.ustopo import Quad

N = 12


def _view(step: Action | Command) -> StepView:
    return step_view(step, euid=1000)


def _views(steps: Sequence[Action | Command]) -> list[StepView]:
    return [_view(s) for s in steps]


def _tile(lat: int, lon: int) -> str:
    return f"Copernicus_DSM_COG_10_N{lat:02d}_00_E{lon:03d}_00_DEM"


TILES = [_tile(i // 4, i % 4) for i in range(N)]


# -- fixtures: each is the real backend's plan for N synthetic items -----------------------


def ustopo(tmp_path: Path) -> list[StepView]:
    quads = [
        Quad(
            i * 0.125,
            0.0,
            i * 0.125 + 0.125,
            0.125,
            9_000_000 + i * 37_000,
            mosaic_tests.MD5,
            f"ZZ/ZZ_Sheet{i:02d}_20240101",
        )
        for i in range(N)
    ]
    region = RegionQuads("atlantis/oceania", "atlantis-oceania", tuple(quads))
    conv = mosaic_tests._converter(
        tmp_path, resolution=TopoResolution(regions=(region,), fetch=tuple(quads))
    )
    m = mosaic_tests.manifest()
    return _views(conv.steps(m, mosaic_tests._block(m)))


def contours(tmp_path: Path) -> list[StepView]:
    gdal_dem_tests._install_tiles(tmp_path, *TILES)
    resolution = DemResolution(
        regions=(RegionTiles("atlantis/oceania", "atlantis-oceania", tuple(TILES), 0),)
    )
    conv = gdal_dem_tests._converter(tmp_path, resolution=resolution)
    m = gdal_dem_tests.manifest()
    return _views(conv.steps(m, gdal_dem_tests._block(m)))


def splat(tmp_path: Path) -> list[StepView]:
    splat_tests._install_tiles(tmp_path, *TILES)
    conv: SplatSdfConverter = splat_tests._converter(tmp_path, *TILES)
    m = splat_tests.manifest()
    return _views(conv.steps(m, splat_tests._block(m)))


def terrain_tiles(tmp_path: Path) -> list[StepView]:
    files = [
        TileFile(
            t,
            tile_url(t),
            1_000_000 + 21_000 * i,
            None,
            hashlib.md5(t.encode(), usedforsecurity=False).hexdigest(),
        )
        for i, t in enumerate(TILES)
    ]
    resolution = DemResolution(
        regions=(RegionTiles("atlantis/oceania", "atlantis-oceania", tuple(TILES), 0),),
        fetch=tuple(files),
    )
    backend = DemTilesBackend(
        prefix=tmp_path, resolution=resolution, fetcher=Fetcher(tmp_path / "cache")
    )
    from test_dem_backend import _block, manifest

    m = manifest()
    return _views(backend.steps(m, _block(m)))


def fstopo(tmp_path: Path) -> list[StepView]:

    rows = [
        parse_row(f"0 {i * 0.125} 0.125 {i * 0.125 + 0.125} {1_230_000 + i} 11 ZZ Sheet{i:02d}")
        for i in range(N)
    ]
    files = tuple(
        FsQuadFile(
            q,
            f"https://data.fs.usda.gov/geodata/rastergateway/data3/s{q.secoord}.tiff",
            1_000_000 + 33_000 * q.secoord % 977,
            None,
        )
        for q in rows
    )
    resolution = FsTopoResolution(
        regions=(RegionSheets("atlantis/oceania", "atlantis-oceania", tuple(rows)),),
        fetch=files,
    )
    pair: TopoQuadsBackend = fstopo_tests._pair(tmp_path, resolution)
    return _views(fstopo_tests._steps(pair))


def kiwix(tmp_path: Path) -> list[StepView]:
    files = []
    for i in range(N):
        book = kiwix_tests.BOOK.__class__(
            id=f"book{i:02d}.example_en_all",
            name=f"book{i:02d}.example_en_all",
            flavour=None,
            category="stack_exchange",
            title=f"Book {i}",
            licence="CC BY-SA",
            licence_url=kiwix_tests.BOOK.licence_url,
        )
        name = f"book{i:02d}.example_en_all_2026-08.zim"
        files.append(
            BookFile(
                book,
                BookPin(
                    id=book.id,
                    file=name,
                    url=f"https://mirror.invalid/{name}",
                    size=50_000_000 + i * 1_300_000,
                    sha256="0" * 64,
                    published="2026-08",
                    measured="2026-09-29",
                ),
            )
        )
    backend: KiwixBooksBackend = kiwix_tests._backend(tmp_path, *files)
    return _views(kiwix_tests._steps(backend))


def infra_tiles(tmp_path: Path) -> list[StepView]:
    regions = [pmtiles_tests._region(f"north-america/us/state{i:02d}") for i in range(N)]
    for r in regions:
        pmtiles_tests._install_region(tmp_path, r)
    conv = pmtiles_tests._converter(tmp_path, regions)
    m = pmtiles_tests.manifest()
    return _views(conv.steps(m, pmtiles_tests._block(m)))


#: Every step kind the ruling named, and the kind of step each repeats.
FIXTURES: dict[str, Callable[[Path], list[StepView]]] = {
    "ustopo-qmapshack": ustopo,
    "dem-qmapshack contours": contours,
    "splat-sdf": splat,
    "dem-copernicus tiles": terrain_tiles,
    "usfs-fstopo": fstopo,
    "kiwix-library": kiwix,
    "osm-pmtiles (infra layer)": infra_tiles,
}


def _groups(views: list[StepView]) -> list[Group]:
    return [g for g in group_steps(views) if isinstance(g, Group)]


@pytest.mark.parametrize("name", sorted(FIXTURES))
def test_a_repeated_step_kind_is_grouped_and_every_step_is_rebuilt_exactly(
    name: str, tmp_path: Path
) -> None:
    views = FIXTURES[name](tmp_path)
    groups = _groups(views)
    assert groups, f"{name}: nothing grouped; steps were {[v.description[:60] for v in views[:4]]}"
    biggest = max(groups, key=lambda g: len(g.items))
    assert len(biggest.items) == N
    # Lossless: template plus item values give every step's description and display back.
    assert biggest.expand() == [(s.description, s.display) for s in biggest.steps]


@pytest.mark.parametrize("name", sorted(FIXTURES))
def test_the_grouped_text_names_every_item_the_steps_name(name: str, tmp_path: Path) -> None:
    views = FIXTURES[name](tmp_path)
    grouped = render_steps(views)
    for group in _groups(views):
        for index, item in enumerate(group.items):
            assert "    " + "  ".join(item) in grouped, f"{name}: item {index} is not listed"
        # Set equality with what the steps name: the item lists carry every value that
        # differs between the steps, so a value in a step is in a listed item or in the
        # template, never nowhere.
        listed = {value for item in group.items for value in item}
        for step in group.steps:
            for text in (step.description, step.display):
                for value in listed:
                    if value in text:
                        break
                else:
                    pytest.fail(f"{name}: a step names no item value: {text[:80]}")
    assert len(grouped) < len(render_steps(views, full=True))


def test_full_prints_every_step_as_the_plan_always_did(tmp_path: Path) -> None:
    views = ustopo(tmp_path)
    expected: list[str] = []
    for view in views:
        expected.append(f"  # {view.description}")
        expected.append(f"  $ {view.display}")
    assert render_steps(views, full=True) == expected


def _action(i: int, kind: str = "fetch", root: bool = False, word: str = "Fetch") -> StepView:
    return StepView(f"{word} tile {i} (1.0 MB, ok)", f"[{kind}] /d/t{i}.tif", (), kind, root, ())


def test_commands_never_group() -> None:
    """Each `install` of a file under /usr/local is a modification read on its own."""
    steps = [
        StepView(
            f"Install {name}",
            f"sudo install -m 0644 {name} /usr/local/{name}",
            ("sudo", "install", "-m", "0644", name, f"/usr/local/{name}"),
            None,
            True,
            (),
        )
        for name in ("a.py", "b.py", "c.py", "d.py", "e.py", "f.py")
    ]
    assert not _groups(steps)
    assert render_steps(steps) == render_steps(steps, full=True)


def test_steps_that_differ_in_more_than_arguments_never_group() -> None:
    assert not _groups([_action(i) for i in range(MIN_REPEATS - 1)]), "too few to collapse"
    assert len(_groups([_action(i) for i in range(MIN_REPEATS)])[0].items) == MIN_REPEATS
    other_kinds = [_action(i, kind=("fetch", "convert")[i % 3 == 0]) for i in range(8)]
    assert not _groups(other_kinds), "no run of four steps of one kind"
    worded = [_action(i, word=("Fetch", "Remove", "Install")[i % 3]) for i in range(9)]
    assert not _groups(worded), "another verb is another step"


def test_a_different_kind_or_privilege_breaks_a_run() -> None:
    steps = [_action(i, root=i != 5) for i in range(10)]
    groups = _groups(steps)
    assert [len(g.items) for g in groups] == [5, 4], (
        "the step with another privilege splits the run"
    )


def test_the_total_sums_the_size_column(tmp_path: Path) -> None:
    views = terrain_tiles(tmp_path)
    text = "\n".join(render_steps(views))
    assert f"Total: {N} " in text
    assert "about" in text.split("Total:")[1]


def test_an_installed_group_keeps_its_unrelated_steps_after_it(tmp_path: Path) -> None:
    views = ustopo(tmp_path)
    text = render_steps(views)
    assert text[-2].startswith("  # Build QMapShack's US Topo map"), "the VRT step is not grouped"
    assert text[-1].startswith("  $ [install-data]")


def test_json_is_unchanged_by_grouping(tmp_path: Path) -> None:
    views = ustopo(tmp_path)
    before = json.dumps([v.__dict__ for v in views], sort_keys=True)
    group_steps(views)
    render_steps(views)
    assert json.dumps([v.__dict__ for v in views], sort_keys=True) == before


# -- the whole plan, through render_plan and main() ---------------------------------------


def _steps(tmp_path: Path) -> list[Action | Command]:
    m = mosaic_tests.manifest()
    quads = [
        Quad(
            i * 0.125,
            0.0,
            i * 0.125 + 0.125,
            0.125,
            9_000_000,
            mosaic_tests.MD5,
            f"ZZ/ZZ_S{i:02d}_2024",
        )
        for i in range(N)
    ]
    region = RegionQuads("atlantis/oceania", "atlantis-oceania", tuple(quads))
    conv = mosaic_tests._converter(
        tmp_path, resolution=TopoResolution(regions=(region,), fetch=tuple(quads))
    )
    return conv.steps(m, mosaic_tests._block(m))


def test_full_equals_the_plan_as_it_was_printed_before_grouping_byte_for_byte(
    tmp_path: Path,
) -> None:
    from hammunition.cli.main import render_plan
    from test_cli import _plan

    steps = _steps(tmp_path)
    plan = _plan()
    head = render_plan(plan, [], euid=1000)[:-2]  # without "Commands (0):" and its "(none" line
    before = [*head, f"Commands ({len(steps)}):"]
    for step in steps:
        before.append(f"  # {step.description}")
        before.append(f"  $ {step.display(euid=1000)}")
    assert render_plan(plan, steps, euid=1000, full=True) == before
    grouped = render_plan(plan, steps, euid=1000)
    assert len(grouped) < len(before)
    assert grouped[: len(head) + 1] == before[: len(head) + 1], "only the step listing is grouped"


def test_the_json_document_carries_every_step_whatever_the_text_does(
    tmp_path: Path,
) -> None:
    from hammunition.interface.envelope import target_view
    from hammunition.interface.plan import build_install_view
    from test_cli import _plan

    steps = _steps(tmp_path)
    plan = _plan()
    view = build_install_view(
        plan, steps, euid=1000, log_destination=None, hands_log_to=None, built=frozenset()
    )
    listed = {c.display for c in view.commands}
    assert listed == {s.display(euid=1000) for s in steps}, "the JSON names every item"
    assert target_view(plan.target)


def test_install_accepts_full_for_a_dry_run_and_a_real_listing(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from hammunition.cli.main import EXIT_OK, main
    from test_cli import CATALOG, _mock_apt

    _mock_apt(monkeypatch, populated=True)
    rc = main(["--catalog", str(CATALOG), "install", "--dry-run", "--full", "git"])
    assert rc == EXIT_OK
    assert "Dry run: nothing above was executed." in capsys.readouterr().out
