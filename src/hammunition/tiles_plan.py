# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""The vector-tile converter for one install run, and what it costs on disk.  D-071.

One :class:`~hammunition.backends.pmtiles.TilesConverter`, staging in its own
directory under the operator's build tree, over the regions piece 1 resolved
for the run. Its disk needs are added to the other map pieces' before
anything is fetched.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from .backends.base import CommandRunner
from .backends.derived import Converter
from .backends.pmtiles import FACTOR, SCRATCH_FACTOR, TilesConverter, TilesLedger, estimate
from .backends.regions import MapLedger
from .backends.staging import Staging
from .geofabrik import RegionFile
from .manifest.schema import DerivedDataInstall
from .plan import InstallPlan

KEY = "tilemaker-pmtiles"


@dataclass(frozen=True)
class TilesRun:
    """The vector-tile converter for one run."""

    ledger: TilesLedger
    tiles: TilesConverter

    @property
    def converters(self) -> dict[str, Converter]:
        return {KEY: self.tiles}

    def _planned(self, plan: InstallPlan) -> list[tuple[str, DerivedDataInstall]]:
        out: list[tuple[str, DerivedDataInstall]] = []
        for planned in plan.packages:
            block = planned.block.install
            if isinstance(block, DerivedDataInstall) and block.converter == KEY:
                out.append((planned.name, block))
        return out

    def idle(self, plan: InstallPlan) -> frozenset[str]:
        """The vector-tile units in *plan* with nothing to build this run."""
        return frozenset(
            planned.name
            for planned in plan.packages
            if isinstance(planned.block.install, DerivedDataInstall)
            and planned.block.install.converter == KEY
            and not self.tiles.pending(planned.manifest, planned.block.install)
        )

    def needs(self, plan: InstallPlan, *, prefix: Path) -> dict[Path, int]:
        """Bytes each location needs this run: the largest build's scratch
        and its staged output in the staging directory (one region at a time,
        each cleared before the next) and every output under the prefix."""
        needs: dict[Path, int] = {}
        for planned in plan.packages:
            block = planned.block.install
            if not isinstance(block, DerivedDataInstall) or block.converter != KEY:
                continue
            sizes = [f.size for f in self.tiles.pending(planned.manifest, block)]
            for where, amount in (
                (
                    self.tiles.staging.directory,
                    (SCRATCH_FACTOR + FACTOR) * max(sizes, default=0),
                ),
                (prefix, sum(estimate(size) for size in sizes)),
            ):
                if amount:
                    needs[where] = needs.get(where, 0) + round(amount)
        return needs


def build_tiles_run(
    *,
    prefix: Path,
    builds: Path,
    owner: str | None,
    runner: CommandRunner | None,
    files: Sequence[RegionFile],
    keep: frozenset[str],
    regions: MapLedger,
) -> TilesRun:
    """The vector-tile converter for one run, staging as the operator."""
    ledger = TilesLedger()
    return TilesRun(
        ledger=ledger,
        tiles=TilesConverter(
            prefix=prefix,
            files=files,
            staging=Staging(builds / "osm-pmtiles", owner=owner),
            keep=keep,
            regions=regions,
            ledger=ledger,
            runner=runner,
        ),
    )
