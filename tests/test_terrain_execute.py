# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""Piece 2's units in a transaction: dispatch, order, and the failing end.  D-061."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from fake_tools import install_fakes
from hammunition.backends import Action, AptBackend, BackendError, RecordingRunner
from hammunition.backends.dem import DemResolution, DemTilesBackend, RegionTiles
from hammunition.backends.derived import DerivedBackend
from hammunition.backends.garmin import MKGMAP_HEAP, SPLITTER_HEAP, GarminConverter
from hammunition.backends.gdal_dem import GdalDemConverter
from hammunition.backends.regions import MapLedger
from hammunition.backends.routino import RoutinoConverter
from hammunition.backends.staging import Staging
from hammunition.backends.terrain import TerrainLedger
from hammunition.copernicus import TileFile, tile_url
from hammunition.distro import Target
from hammunition.execute import commands_for
from hammunition.manifest.schema import DerivedDataInstall, PackageManifest
from hammunition.plan import InstallPlan, PlannedPackage
from test_dem_backend import BODY, FakeFetcher
from test_dem_backend import manifest as dem_manifest
from test_garmin import MKGMAP_OK, SPLITTER_OK
from test_garmin import manifest as garmin_manifest
from test_gdal_dem import manifest as gdal_manifest
from test_regions_backend import VT, _regions, regions_manifest
from test_routino import manifest as routino_manifest

A = "Copernicus_DSM_COG_10_N00_00_E000_00_DEM"
TILE = TileFile(A, tile_url(A), len(BODY), None, "0" * 32)
RESOLUTION = DemResolution(
    regions=(RegionTiles("atlantis/oceania", "atlantis-oceania", (A,), 0),), fetch=(TILE,)
)
#: The engine is not root, whoever runs the suite (``unshare -r`` included).
NOT_ROOT = 4242


def _plan() -> InstallPlan:
    dem, gdal = dem_manifest(), gdal_manifest()
    return InstallPlan(
        target=Target(distro="debian", version="13", arch="x86_64"),
        # `after` order: the converter's unit sorts before the data it reads.
        packages=(
            PlannedPackage(manifest=gdal, block=gdal.install[0], apt_packages=("gdal-bin",)),
            PlannedPackage(manifest=dem, block=dem.install[0], apt_packages=()),
        ),
    )


def _backends(tmp_path: Path, ledger: TerrainLedger) -> dict[str, Any]:
    dem = DemTilesBackend(
        fetcher=FakeFetcher(tmp_path / "cache"),
        prefix=tmp_path,
        resolution=RESOLUTION,
        ledger=ledger,
    )
    gdal = GdalDemConverter(
        prefix=tmp_path, resolution=RESOLUTION, staging=Staging(tmp_path / "staging"), ledger=ledger
    )
    derived = DerivedBackend(
        prefix=tmp_path, files=(), staging=tmp_path / "navit", converters={"gdal-dem": gdal}
    )
    return {"dem": dem, "derived": derived}


def test_a_terrain_plan_without_its_backends_is_refused_not_skipped(tmp_path: Path) -> None:
    with pytest.raises(BackendError, match="no dem-tiles backend"):
        commands_for(
            _plan(),
            AptBackend(RecordingRunner()),
            derived=_backends(tmp_path, TerrainLedger())["derived"],
        )
    derived = DerivedBackend(prefix=tmp_path, files=(), staging=tmp_path / "navit")
    dem = _backends(tmp_path, TerrainLedger())["dem"]
    with pytest.raises(BackendError, match="converter 'gdal-dem' has no backend"):
        commands_for(_plan(), AptBackend(RecordingRunner()), derived=derived, dem=dem)


def test_tiles_are_fetched_first_drawn_after_apt_and_the_ledger_checks_last(
    tmp_path: Path,
) -> None:
    ledger = TerrainLedger()
    steps = commands_for(_plan(), AptBackend(RecordingRunner()), **_backends(tmp_path, ledger))
    shape = [
        s.kind if isinstance(s, Action) else ("apt" if "apt-get" in s.argv else "cmd")
        for s in steps
    ]
    assert shape[0] == "fetch"
    apt_at = shape.index("apt")
    assert shape[apt_at + 1 :] == [
        "install-data",  # the tile
        "install-data",  # its region's record
        "convert",  # contours
        "install-data",  # contours installed
        "install-data",  # both rasters
        "check-terrain",
    ]
    assert shape.count("check-terrain") == 1, "one shared ledger, one check"


# ---------------------------------------------------------------------------
# Every converter reaches its own backend
# ---------------------------------------------------------------------------


def _block(m: PackageManifest) -> DerivedDataInstall:
    block = m.install[0].install
    assert isinstance(block, DerivedDataInstall)
    return block


def _garmin_staging(tmp_path: Path) -> Staging:
    """The Garmin converter's staging as a run builds it: the splitter's heap
    through ``JAVA_OPTS``, mkgmap's through ``JAVA_TOOL_OPTIONS`` (Debian's
    mkgmap wrapper ignores ``JAVA_OPTS``)."""
    return Staging(
        tmp_path / "garmin",
        euid=NOT_ROOT,
        environ={"JAVA_OPTS": SPLITTER_HEAP, "JAVA_TOOL_OPTIONS": MKGMAP_HEAP},
    )


def _all_converters(tmp_path: Path, ledger: TerrainLedger) -> DerivedBackend:
    common: dict[str, Any] = {"prefix": tmp_path, "ledger": ledger, "euid": NOT_ROOT}
    return DerivedBackend(
        prefix=tmp_path,
        files=[VT],
        staging=tmp_path / "navit",
        converters={
            "mkgmap": GarminConverter(
                files=[VT], staging=_garmin_staging(tmp_path), privileged=False, **common
            ),
            "routino-planetsplitter": RoutinoConverter(
                files=[VT],
                staging=Staging(tmp_path / "routino", euid=NOT_ROOT),
                privileged=False,
                **common,
            ),
            "gdal-dem": GdalDemConverter(
                resolution=RESOLUTION,
                staging=Staging(tmp_path / "gdal", euid=NOT_ROOT),
                privileged=False,
                **common,
            ),
        },
    )


@pytest.mark.parametrize(
    ("manifest", "says"),
    [
        (garmin_manifest, "Build the Garmin map of north-america/us/vermont"),
        (routino_manifest, "Parse north-america/us/vermont into the Routino database"),
        (gdal_manifest, "contour"),
    ],
)
def test_each_converter_is_dispatched_to_its_own_backend_and_ledger(
    tmp_path: Path, manifest: Any, says: str
) -> None:
    ledger = TerrainLedger()
    derived = _all_converters(tmp_path, ledger)
    m = manifest()
    steps = derived.steps(m, _block(m))
    assert steps and any(says in s.description for s in steps)
    (reported,) = derived.ledgers(_block(m))
    assert reported is ledger


def test_navit_reports_into_the_map_ledger(tmp_path: Path) -> None:
    from test_regions_backend import navit_manifest

    derived = _all_converters(tmp_path, TerrainLedger())
    m = navit_manifest()
    assert derived.ledgers(_block(m)) == (derived.ledger,)


def test_a_dispatched_garmin_run_gives_each_program_its_heap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    install_fakes(
        monkeypatch,
        tmp_path / "bin",
        {
            "mkgmap-splitter": f'echo "$JAVA_OPTS" > {tmp_path}/heap; {SPLITTER_OK}',
            "mkgmap": f'echo "$JAVA_TOOL_OPTIONS" > {tmp_path}/mkgmap-heap; {MKGMAP_OK}',
        },
    )
    pbf = tmp_path / "share" / "hammunition" / "data" / "osm-regions" / f"{VT.slug}.osm.pbf"
    pbf.parent.mkdir(parents=True)
    pbf.write_bytes(b"p" * 10)
    ledger = TerrainLedger()
    derived = _all_converters(tmp_path, ledger)
    m = garmin_manifest()
    outcomes = [s.perform() for s in derived.steps(m, _block(m)) if isinstance(s, Action)]
    assert ledger.failed == {}, outcomes
    assert (tmp_path / "heap").read_text().strip() == SPLITTER_HEAP
    assert (tmp_path / "mkgmap-heap").read_text().strip() == MKGMAP_HEAP


def test_the_regions_install_before_the_map_converters_run(tmp_path: Path) -> None:
    """Plan order is `after`, so osm-garmin sorts before osm-regions; the
    conversion still runs after the region it reads is installed."""
    garmin, regions = garmin_manifest(), regions_manifest()
    plan = InstallPlan(
        target=Target(distro="debian", version="13", arch="x86_64"),
        packages=(
            PlannedPackage(manifest=garmin, block=garmin.install[0], apt_packages=("mkgmap",)),
            PlannedPackage(manifest=regions, block=regions.install[0], apt_packages=()),
        ),
    )
    maps = MapLedger()
    steps = commands_for(
        plan,
        AptBackend(RecordingRunner()),
        regions=_regions(tmp_path, [VT], ledger=maps),
        derived=_all_converters(tmp_path, TerrainLedger()),
    )
    actions = [s for s in steps if isinstance(s, Action)]
    region_installed = next(
        i for i, s in enumerate(actions) if s.detail.endswith(f"osm-regions/{VT.slug}.osm.pbf")
    )
    converted = next(i for i, s in enumerate(actions) if s.kind == "convert")
    assert region_installed < converted
    kinds = [s.kind for s in actions]
    assert sorted(kinds[-2:]) == ["check-map-regions", "check-terrain"]
