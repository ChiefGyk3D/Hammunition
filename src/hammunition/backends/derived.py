# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""The derived backend: another unit's data, converted for an application.  D-057.

The catalog names the converter by enum (``navit-maptool``) and the engine
owns what that means, exactly as ``build_system: cmake`` is an enum the
source backend implements; no command line ever comes from a manifest.

For ``navit-maptool``: each region's ``.osm.pbf`` (installed by the source
unit, under its own data directory) becomes ``<slug>.bin`` under this unit's
data directory, with a ``<slug>.bin.source`` sidecar holding the snapshot it
was converted from. A region already converted from the same snapshot is not
converted again; a region no longer in station config loses its ``.bin``.
Last, ``navit.xml`` is written beside the maps from the installed stock
config (:mod:`hammunition.navit_config`), pointing at every region's map.

The effect is checked, not the exit status (D-031): maptool's output must
exist and be non-empty before it replaces anything, and its temporary is
removed when it does not.
"""

from __future__ import annotations

import os
import subprocess
from collections.abc import Sequence
from dataclasses import dataclass
from functools import partial
from pathlib import Path

from .. import navit_config
from ..geofabrik import RegionFile
from ..manifest.schema import DerivedDataInstall, PackageManifest
from .base import Action, BackendError, Command
from .regions import PBF, SOURCE, data_root, installed_snapshot, removal_steps
from .source import needs_root_for

BIN = ".bin"


@dataclass(frozen=True)
class DerivedBackend:
    """Turns a ``derived`` block and the resolved regions into conversion steps."""

    prefix: Path
    files: Sequence[RegionFile]
    stock: Path = navit_config.STOCK
    method = "derived"

    def data_dir(self, manifest: PackageManifest) -> Path:
        return data_root(self.prefix) / manifest.name

    def steps(self, manifest: PackageManifest, block: DerivedDataInstall) -> list[Action | Command]:
        # One converter today; the schema's enum refuses anything else, and a
        # new member must be implemented here before a manifest can name it.
        if block.converter != "navit-maptool":  # pragma: no cover
            raise BackendError(f"{manifest.name}: converter {block.converter!r} is not implemented")
        out = self.data_dir(manifest)
        source_dir = data_root(self.prefix) / block.source
        root = needs_root_for(self.prefix)
        steps: list[Action | Command] = []
        bins: list[Path] = []
        for region in self.files:
            pbf = source_dir / f"{region.slug}{PBF}"
            dest = out / f"{region.slug}{BIN}"
            bins.append(dest)
            if dest.is_file() and installed_snapshot(dest) == region.snapshot:
                continue
            steps.append(
                Action(
                    kind="install-data",
                    description=(
                        f"Convert map region {region.region} ({region.snapshot}) for Navit: "
                        f"maptool --protobuf -i {pbf} {dest}"
                    ),
                    # The destination, verbatim, for uninstall's attribution replay.
                    detail=str(dest),
                    perform=partial(_maptool, region, pbf, dest),
                    requires_root=root,
                )
            )
        steps.extend(removal_steps(out, BIN, {f.slug for f in self.files}, requires_root=root))
        config = out / "navit.xml"
        steps.append(
            Action(
                kind="install-data",
                description=(
                    f"Write Navit's config for these maps, built from {self.stock} "
                    f"(speech through espeak-ng, one mapset of the regions above)"
                ),
                detail=str(config),
                perform=partial(_write_config, self.stock, tuple(bins), config),
                requires_root=root,
            )
        )
        return steps


def _maptool(region: RegionFile, pbf: Path, dest: Path) -> str:
    dest.parent.mkdir(parents=True, exist_ok=True)
    temporary = dest.with_name(dest.name + f".part.{os.getpid()}")
    try:
        result = subprocess.run(
            ["maptool", "--protobuf", "-i", str(pbf), str(temporary)],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as exc:
        temporary.unlink(missing_ok=True)
        raise BackendError(f"maptool could not be run to convert {pbf.name}: {exc}") from exc
    if result.returncode != 0 or not temporary.is_file() or temporary.stat().st_size == 0:
        temporary.unlink(missing_ok=True)
        raise BackendError(
            f"maptool did not convert {pbf.name} (exit {result.returncode}): "
            f"{result.stderr.strip()[-300:]}"
        )
    os.chmod(temporary, 0o644)
    os.replace(temporary, dest)
    sidecar = dest.with_name(dest.name + SOURCE)
    sidecar.write_text(f"{region.snapshot}\n")
    os.chmod(sidecar, 0o644)
    return f"converted {pbf.name} to {dest} ({dest.stat().st_size} bytes)"


def _write_config(stock: Path, bins: Sequence[Path], dest: Path) -> str:
    try:
        text = stock.read_text()
    except OSError as exc:
        raise BackendError(
            f"cannot read Navit's stock config {stock}: {exc.strerror or exc}. "
            f"It comes from the navit package; install it and run this again."
        ) from exc
    try:
        body = navit_config.rewrite(text, bins)
    except navit_config.NavitConfigError as exc:
        raise BackendError(f"{stock}: {exc}") from exc
    dest.parent.mkdir(parents=True, exist_ok=True)
    temporary = dest.with_name(dest.name + f".part.{os.getpid()}")
    temporary.write_text(body)
    os.chmod(temporary, 0o644)
    os.replace(temporary, dest)
    return f"wrote {dest} ({len(bins)} map(s))"
