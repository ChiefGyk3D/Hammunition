# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""The derived backend: another unit's data, converted for an application.  D-057.

The catalog names the converter by enum (``navit-maptool``) and the engine
owns what that means, exactly as ``build_system: cmake`` is an enum the
source backend implements; no command line ever comes from a manifest.

For ``navit-maptool``, each region takes two steps:

* **convert**, unprivileged: ``maptool --protobuf -i <pbf> <staged>`` runs
  as the operator into a staging directory the operator owns -- under root
  it drops to the operator first. maptool parses downloaded data, and a
  parser of downloaded data does not run as root where it need not (the
  "drop to user where possible" rule). The effect is checked, not the exit
  status (D-031): the output must exist and be non-empty, and its digest is
  taken there.
* **install**, as root only where the prefix needs it: the staged map is
  copied into ``<data>/<unit>/<slug>.bin`` re-verified against that digest
  without following a symlink, with a ``<slug>.bin.source`` sidecar holding
  the snapshot.

A region already converted from the same snapshot is not converted again; a
region no longer in station config loses its ``.bin`` (one the plan kept
because it could not be checked for a newer map does not). Last,
``navit.xml`` is written beside the maps from the installed stock config
(:mod:`hammunition.navit_config`), listing every map that exists then.

A region that failed -- to download, to verify, to convert -- is recorded in
the shared :class:`~hammunition.backends.regions.MapLedger`, the others
continue, and the ledger fails the transaction by name at its end.
"""

from __future__ import annotations

import os
import pwd
import subprocess
from collections.abc import Sequence
from dataclasses import dataclass, field
from functools import partial
from pathlib import Path

from .. import navit_config
from ..geofabrik import RegionFile
from ..manifest.schema import DerivedDataInstall, PackageManifest
from .base import Action, BackendError, Command, CommandRunner
from .data import human_size
from .regions import (
    DERIVED_FACTOR,
    PBF,
    SOURCE,
    MapLedger,
    data_root,
    installed_snapshot,
    prefix_writer,
    removal_steps,
)
from .verified import PrefixWriter, digest_of

BIN = ".bin"


@dataclass(frozen=True)
class DerivedBackend:
    """Turns a ``derived`` block and the resolved regions into conversion steps."""

    prefix: Path
    files: Sequence[RegionFile]
    staging: Path
    """The operator's directory maptool writes into; never under the prefix."""
    stock: Path = navit_config.STOCK
    keep: frozenset[str] = frozenset()
    ledger: MapLedger = field(default_factory=MapLedger)
    owner: str | None = None
    """Who maptool runs as when the engine itself is root."""
    runner: CommandRunner | None = None
    euid: int | None = None
    privileged: bool | None = None
    method = "derived"

    @property
    def writer(self) -> PrefixWriter:
        return prefix_writer(self.prefix, self.privileged, self.runner, self.euid)

    def data_dir(self, manifest: PackageManifest) -> Path:
        return data_root(self.prefix) / manifest.name

    def steps(self, manifest: PackageManifest, block: DerivedDataInstall) -> list[Action | Command]:
        # One converter today; the schema's enum refuses anything else, and a
        # new member must be implemented here before a manifest can name it.
        if block.converter != "navit-maptool":  # pragma: no cover
            raise BackendError(f"{manifest.name}: converter {block.converter!r} is not implemented")
        out = self.data_dir(manifest)
        source_dir = data_root(self.prefix) / block.source
        writer = self.writer
        steps: list[Action | Command] = []
        for region in self.files:
            pbf = source_dir / f"{region.slug}{PBF}"
            dest = out / f"{region.slug}{BIN}"
            if dest.is_file() and installed_snapshot(dest) == region.snapshot:
                continue
            staged = self.staging / f"{region.slug}{BIN}.part"
            converted: dict[str, str] = {}
            estimate = human_size(region.size * DERIVED_FACTOR)
            steps.append(
                Action(
                    kind="convert",
                    description=(
                        f"Convert map region {region.region} ({region.snapshot}) for Navit, "
                        f"as the operator: maptool --protobuf -i {pbf} {staged}; output about "
                        f"{estimate} (an estimate: {DERIVED_FACTOR}x the download, until measured)"
                    ),
                    detail=str(staged),
                    perform=partial(self._convert, region, pbf, staged, converted),
                )
            )
            steps.append(
                Action(
                    kind="install-data",
                    description=f"Install the Navit map of {region.region} ({region.snapshot})",
                    # The destination, verbatim, for uninstall's attribution replay.
                    detail=str(dest),
                    perform=partial(self._install, region, staged, dest, converted, writer),
                    requires_root=writer.privileged,
                )
            )
        keep = {f.slug for f in self.files} | set(self.keep)
        steps.extend(removal_steps(out, BIN, keep, writer))
        slugs = [*(f.slug for f in self.files), *sorted(self.keep - {f.slug for f in self.files})]
        config = out / "navit.xml"
        steps.append(
            Action(
                kind="install-data",
                description=(
                    f"Write Navit's config for these maps, built from {self.stock} "
                    f"(speech through espeak-ng, one mapset of the regions above)"
                ),
                detail=str(config),
                perform=partial(
                    self._write_config, tuple(out / f"{s}{BIN}" for s in slugs), config, writer
                ),
                requires_root=writer.privileged,
            )
        )
        return steps

    def _as_operator(self) -> tuple[int, int] | None:
        """(uid, gid) to drop to, when the engine is root on an operator's behalf."""
        euid = os.geteuid() if self.euid is None else self.euid
        if euid != 0 or not self.owner or self.owner == "root":
            return None
        entry = pwd.getpwnam(self.owner)
        return entry.pw_uid, entry.pw_gid

    def _convert(
        self, region: RegionFile, pbf: Path, staged: Path, converted: dict[str, str]
    ) -> str:
        if region.slug in self.ledger.failed:
            return f"skipped: {region.region} did not install"
        if not pbf.is_file():
            return self.ledger.fail(region.slug, f"{region.region}: {pbf} is not installed")
        drop = self._as_operator()
        self.staging.mkdir(parents=True, exist_ok=True)
        if drop is not None:
            os.chown(self.staging, *drop)
        staged.unlink(missing_ok=True)
        argv = ["maptool", "--protobuf", "-i", str(pbf), str(staged)]
        try:
            if drop is not None:
                result = subprocess.run(
                    argv,
                    capture_output=True,
                    text=True,
                    check=False,
                    user=drop[0],
                    group=drop[1],
                    extra_groups=[],
                )
            else:
                result = subprocess.run(argv, capture_output=True, text=True, check=False)
        except OSError as exc:
            staged.unlink(missing_ok=True)
            return self.ledger.fail(
                region.slug, f"{region.region}: maptool could not be run on {pbf.name}: {exc}"
            )
        if result.returncode != 0 or not staged.is_file() or staged.stat().st_size == 0:
            staged.unlink(missing_ok=True)
            return self.ledger.fail(
                region.slug,
                f"{region.region}: maptool did not convert {pbf.name} "
                f"(exit {result.returncode}): {result.stderr.strip()[-300:]}",
            )
        try:
            converted["sha256"] = digest_of(staged)
        except BackendError as exc:
            staged.unlink(missing_ok=True)
            return self.ledger.fail(region.slug, f"{region.region}: {exc}")
        return f"converted {pbf.name} ({staged.stat().st_size} bytes, staged)"

    def _install(
        self,
        region: RegionFile,
        staged: Path,
        dest: Path,
        converted: dict[str, str],
        writer: PrefixWriter,
    ) -> str:
        if region.slug in self.ledger.failed or "sha256" not in converted:
            return f"skipped: {region.region} was not converted"
        try:
            writer.install_verified(staged, dest, algorithm="sha256", digest=converted["sha256"])
            writer.write_text(dest.with_name(dest.name + SOURCE), f"{region.snapshot}\n")
        except (BackendError, OSError) as exc:
            return self.ledger.fail(region.slug, f"{region.region}: {exc}")
        finally:
            staged.unlink(missing_ok=True)
        return f"installed {dest}"

    def _write_config(self, bins: Sequence[Path], dest: Path, writer: PrefixWriter) -> str:
        present = [b for b in bins if b.is_file()]
        if not present and self.ledger.failed:
            # Nothing converted; the ledger's step fails the run naming why.
            return "not written: no region has a Navit map"
        try:
            text = self.stock.read_text()
        except OSError as exc:
            raise BackendError(
                f"cannot read Navit's stock config {self.stock}: {exc.strerror or exc}. "
                f"It comes from the navit package; install it and run this again."
            ) from exc
        try:
            body = navit_config.rewrite(text, present)
        except navit_config.NavitConfigError as exc:
            raise BackendError(f"{self.stock}: {exc}") from exc
        writer.write_text(dest, body)
        return f"wrote {dest} ({len(present)} map(s))"
