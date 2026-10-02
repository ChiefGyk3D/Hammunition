# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""GraphHopper's route graph for one install run, and what it costs on disk.  D-076.

One :class:`~hammunition.backends.graphhopper.GraphConverter`, staging in its
own directory under the operator's build tree, over the regions piece 1
resolved for the run. Its disk needs are added to the other map pieces'
before anything is fetched.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from fnmatch import fnmatch
from pathlib import Path

from .backends.base import CommandRunner
from .backends.derived import Converter
from .backends.graphhopper import GraphConverter, GraphLedger
from .backends.regions import MapLedger
from .backends.staging import Staging
from .geofabrik import RegionFile
from .graphhopper import FACTOR, GRAPH_UNIT, JAR_GLOB, estimate
from .manifest.schema import BinaryInstall, DerivedDataInstall
from .plan import InstallPlan

KEY = "graphhopper-import"


def graphhopper_jar(plan: InstallPlan) -> str | None:
    """The jar the plan installs for the graph's build: the planned program
    unit's tree marker, so a GraphHopper bumped in this run is seen before its
    new tree is on disk (D-063's I1, the same shape)."""
    planned = {p.name: p for p in plan.packages}
    for build in plan.packages:
        block = build.block.install
        if isinstance(block, DerivedDataInstall) and block.converter == KEY:
            program = planned.get(block.program or "")
            if program is not None and isinstance(program.block.install, BinaryInstall):
                marker = program.block.install.tree_marker
                if marker is not None and fnmatch(marker, JAR_GLOB):
                    return marker
    return None


@dataclass(frozen=True)
class GraphRun:
    """GraphHopper's route graph for one run."""

    ledger: GraphLedger
    graph: GraphConverter

    @property
    def converters(self) -> dict[str, Converter]:
        return {KEY: self.graph}

    def _planned(self, plan: InstallPlan) -> list[tuple[str, DerivedDataInstall]]:
        out: list[tuple[str, DerivedDataInstall]] = []
        for planned in plan.packages:
            block = planned.block.install
            if isinstance(block, DerivedDataInstall) and block.converter == KEY:
                out.append((planned.name, block))
        return out

    def idle(self, plan: InstallPlan) -> frozenset[str]:
        """The graph units in *plan* with nothing to build this run."""
        return frozenset(
            planned.name
            for planned in plan.packages
            if isinstance(planned.block.install, DerivedDataInstall)
            and planned.block.install.converter == KEY
            and not self.graph.pending(planned.manifest, planned.block.install)
        )

    def needs(self, plan: InstallPlan, *, prefix: Path) -> dict[Path, int]:
        """Bytes each location needs this run: in the staging directory the
        graph as it builds, with the merged input when there are two regions
        or more; under the prefix the graph installed."""
        needs: dict[Path, int] = {}
        for planned in plan.packages:
            block = planned.block.install
            if not isinstance(block, DerivedDataInstall) or block.converter != KEY:
                continue
            sizes = [s.size for s in self.graph.pending(planned.manifest, block)]
            total = sum(sizes)
            merged = total if len(sizes) > 1 else 0
            for where, amount in (
                (self.graph.staging.directory, estimate(total) + merged),
                (prefix, estimate(total)),
            ):
                if amount:
                    needs[where] = needs.get(where, 0) + amount
        return needs


def build_graph_run(
    *,
    prefix: Path,
    builds: Path,
    owner: str | None,
    runner: CommandRunner | None,
    files: Sequence[RegionFile],
    keep: frozenset[str],
    regions: MapLedger,
    jar: str | None,
) -> GraphRun:
    """GraphHopper's route graph for one run, staging as the operator."""
    ledger = GraphLedger()
    return GraphRun(
        ledger=ledger,
        graph=GraphConverter(
            prefix=prefix,
            files=files,
            staging=Staging(builds / GRAPH_UNIT, owner=owner),
            keep=keep,
            regions=regions,
            ledger=ledger,
            runner=runner,
            jar=jar,
        ),
    )


__all__ = ["FACTOR", "KEY", "GraphRun", "build_graph_run", "graphhopper_jar"]
