# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""Piece 2's disk estimate and its failure ledger.  D-061."""

from __future__ import annotations

from pathlib import Path

import pytest

from hammunition.backends import BackendError
from hammunition.backends.terrain import (
    CONTOUR_BYTES,
    CONTOUR_SCRATCH_BYTES,
    GARMIN_SCRATCH_FACTOR,
    MEASURED,
    TerrainLedger,
    TerrainWork,
    combined_shortfall,
    garmin_estimate,
    routino_estimate,
    terrain_needs,
    tile_key,
)

MB = 1_000_000


def _needs(tmp_path: Path, work: TerrainWork) -> dict[Path, int]:
    return terrain_needs(
        work,
        cache=tmp_path / "cache",
        garmin_staging=tmp_path / "garmin",
        routino_staging=tmp_path / "routino",
        contour_staging=tmp_path / "contours",
        prefix=tmp_path / "prefix",
    )


def test_the_factors_are_the_measured_ones() -> None:
    assert garmin_estimate(100 * MB) == 85 * MB
    assert routino_estimate(100 * MB) == 67 * MB
    assert MEASURED == "measured on one region"


def test_garmin_scratch_is_the_largest_region_not_the_sum(tmp_path: Path) -> None:
    needs = _needs(tmp_path, TerrainWork(garmin=(100 * MB, 300 * MB)))
    assert needs[tmp_path / "garmin"] == GARMIN_SCRATCH_FACTOR * 300 * MB
    assert needs[tmp_path / "prefix"] == garmin_estimate(100 * MB) + garmin_estimate(300 * MB)


def test_contours_count_one_tile_of_scratch_and_every_raster(tmp_path: Path) -> None:
    needs = _needs(tmp_path, TerrainWork(tiles=40 * MB * 3, contour_tiles=3))
    assert needs[tmp_path / "contours"] == CONTOUR_SCRATCH_BYTES + 3 * CONTOUR_BYTES
    assert needs[tmp_path / "cache"] == 120 * MB
    assert needs[tmp_path / "prefix"] == 120 * MB + 3 * CONTOUR_BYTES


def test_nothing_to_do_needs_nothing(tmp_path: Path) -> None:
    assert not TerrainWork().any()
    assert not any(_needs(tmp_path, TerrainWork()).values())


def test_the_refusal_names_the_terrain_estimate_only_when_it_counted(tmp_path: Path) -> None:
    same = {tmp_path / "a": 10 * MB}
    terrain = {tmp_path / "b": 10 * MB}
    short = combined_shortfall(same, terrain, free_at=lambda p: 15 * MB, device_of=lambda p: 1)
    assert short is not None and "QMapShack" in short and MEASURED in short
    alone = combined_shortfall(same, {}, free_at=lambda p: 5 * MB, device_of=lambda p: 1)
    assert alone is not None and "QMapShack" not in alone
    assert (
        combined_shortfall(same, terrain, free_at=lambda p: 30 * MB, device_of=lambda p: 1) is None
    )


def test_the_ledger_fails_the_transaction_naming_every_failure() -> None:
    ledger = TerrainLedger()
    assert "every" in ledger.step().perform()
    assert "FAILED" in ledger.fail(tile_key("T1"), "T1: md5 did not match")
    ledger.fail("osm-garmin:atlantis-oceania", "atlantis/oceania: mkgmap wrote no map")
    with pytest.raises(BackendError) as raised:
        ledger.check()
    assert "T1: md5" in str(raised.value) and "mkgmap wrote no map" in str(raised.value)
    assert tile_key("T1") != "atlantis-oceania"
