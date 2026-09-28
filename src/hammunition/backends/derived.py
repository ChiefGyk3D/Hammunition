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

import contextlib
import os
import pwd
import stat
import subprocess
from collections.abc import Sequence
from dataclasses import dataclass, field
from functools import partial
from pathlib import Path
from typing import Any

from .. import navit_config
from ..geofabrik import RegionFile
from ..manifest.schema import DerivedDataInstall, PackageManifest
from ..paths import operator_dir_problem
from .base import Action, BackendError, Command, CommandRunner
from .data import human_size
from .regions import (
    BIN_FACTOR,
    ESTIMATE,
    PBF,
    SCRATCH_FACTOR,
    SOURCE,
    MapLedger,
    bin_estimate,
    data_root,
    installed_snapshot,
    prefix_writer,
    removal_steps,
)
from .verified import PrefixWriter, digest_of

BIN = ".bin"
_EMPTY_SHA256 = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"


def _maptool_argv(pbf: Path, staged: Path) -> list[str]:
    """The fixed argv ``navit-maptool`` means. Nothing in it comes from a manifest."""
    return ["maptool", "--protobuf", "-i", str(pbf), str(staged)]


def _maptool_failure(
    region: RegionFile, pbf: Path, result: subprocess.CompletedProcess[str]
) -> str:
    return (
        f"{region.region}: maptool did not convert {pbf.name} "
        f"(exit {result.returncode}): {result.stderr.strip()[-300:]}"
    )


def _as(drop: tuple[int, int]) -> dict[str, Any]:
    """subprocess arguments that run a child as the operator, with no extra groups."""
    return {"user": drop[0], "group": drop[1], "extra_groups": []}


def _remove_as(drop: tuple[int, int], path: Path) -> None:
    """Remove *path* as the operator; root never unlinks through the operator's path."""
    # rm missing is not worth failing over: the staged file is the operator's.
    with contextlib.suppress(OSError):
        subprocess.run(["rm", "-f", "--", str(path)], capture_output=True, check=False, **_as(drop))


def _staging_refusal(staging: Path) -> str | None:
    """Why root must not use *staging*: a symlink, or something not a directory."""
    try:
        mode = staging.lstat().st_mode
    except FileNotFoundError:
        return None  # the operator creates it
    except OSError as exc:
        return f"cannot inspect the staging directory {staging}: {exc.strerror or exc}"
    if stat.S_ISLNK(mode):
        return (
            f"the staging directory {staging} is a symlink; refusing to convert through it "
            f"as root. Remove it and run the install again."
        )
    if not stat.S_ISDIR(mode):
        return f"the staging directory {staging} is not a directory"
    return None


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
            if self._current(dest, region):
                continue
            staged = self.staging / f"{region.slug}{BIN}.part"
            converted: dict[str, str] = {}
            estimate = human_size(bin_estimate(region.size))
            steps.append(
                Action(
                    kind="convert",
                    description=(
                        f"Convert map region {region.region} ({region.snapshot}) for Navit, "
                        f"as the operator, in {self.staging}: maptool --protobuf -i {pbf} "
                        f"{staged}; output about "
                        f"{estimate} ({BIN_FACTOR}x the download) and up to "
                        f"{human_size(region.size * SCRATCH_FACTOR)} of scratch while it runs, "
                        f"in the staging directory ({ESTIMATE})"
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

    def pending(self, manifest: PackageManifest) -> list[RegionFile]:
        """Regions this run converts: no ``.bin``, or one from another snapshot."""
        out = self.data_dir(manifest)
        return [f for f in self.files if not self._current(out / f"{f.slug}{BIN}", f)]

    @staticmethod
    def _current(dest: Path, region: RegionFile) -> bool:
        return dest.is_file() and installed_snapshot(dest) == region.snapshot

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
        if drop is None:
            return self._convert_here(region, pbf, staged, converted)
        return self._convert_as_operator(region, pbf, staged, converted, drop)

    def _convert_here(
        self, region: RegionFile, pbf: Path, staged: Path, converted: dict[str, str]
    ) -> str:
        """The engine is the operator (or root with nobody to drop to)."""
        self.staging.mkdir(parents=True, exist_ok=True)
        staged.unlink(missing_ok=True)
        try:
            # cwd: maptool writes its *.tmp scratch into its working
            # directory -- more than 12 GB for Canada -- and aborts in a
            # read-only one (measured: exit 134, buffer.c:39).
            result = subprocess.run(
                _maptool_argv(pbf, staged),
                capture_output=True,
                text=True,
                check=False,
                cwd=self.staging,
            )
        except OSError as exc:
            staged.unlink(missing_ok=True)
            return self.ledger.fail(
                region.slug, f"{region.region}: maptool could not be run on {pbf.name}: {exc}"
            )
        if result.returncode != 0 or not staged.is_file() or staged.stat().st_size == 0:
            staged.unlink(missing_ok=True)
            return self.ledger.fail(region.slug, _maptool_failure(region, pbf, result))
        try:
            converted["sha256"] = digest_of(staged)
        except BackendError as exc:
            staged.unlink(missing_ok=True)
            return self.ledger.fail(region.slug, f"{region.region}: {exc}")
        return f"converted {pbf.name} ({staged.stat().st_size} bytes, staged)"

    def _convert_as_operator(
        self,
        region: RegionFile,
        pbf: Path,
        staged: Path,
        converted: dict[str, str],
        drop: tuple[int, int],
    ) -> str:
        """The engine is root: every staging-side step runs as the operator.

        The staging directory is under the operator's home, so any path in it
        is the operator's to point elsewhere -- ``osm-navit -> /etc/sudoers.d``.
        Root therefore creates, writes, reads, hashes and removes nothing
        there itself: each is a process dropped to the operator, who can only
        do to that path what they could already do. Root's one look is an
        lstat, which refuses a staging directory that is a symlink or not a
        directory before anything runs.
        """
        # Every existing component from the operator's home down must be the
        # operator's own directory: a root-owned ~/.cache/hammunition left by
        # an older sudo run would make the operator's install -d fail with a
        # bare EACCES, so it is named here with its fix instead.
        refusal = _staging_refusal(self.staging) or operator_dir_problem(self.staging, self.owner)
        if refusal is not None:
            return self.ledger.fail(region.slug, f"{region.region}: {refusal}")
        as_operator = _as(drop)
        try:
            made = subprocess.run(
                ["install", "-d", "-m", "0755", "--", str(self.staging)],
                capture_output=True,
                text=True,
                check=False,
                **as_operator,
            )
            if made.returncode != 0:
                return self.ledger.fail(
                    region.slug,
                    f"{region.region}: could not create {self.staging} as the operator: "
                    f"{made.stderr.strip()[-300:]}",
                )
            _remove_as(drop, staged)
            # No cwd=: subprocess would chdir there as root, before the drop.
            # env -C makes the chdir the operator's own.
            result = subprocess.run(
                ["env", "-C", str(self.staging), *_maptool_argv(pbf, staged)],
                capture_output=True,
                text=True,
                check=False,
                **as_operator,
            )
            if result.returncode != 0:
                _remove_as(drop, staged)
                return self.ledger.fail(region.slug, _maptool_failure(region, pbf, result))
            hashed = subprocess.run(
                ["sha256sum", "--", str(staged)],
                capture_output=True,
                text=True,
                check=False,
                **as_operator,
            )
        except OSError as exc:
            _remove_as(drop, staged)
            return self.ledger.fail(
                region.slug, f"{region.region}: maptool could not be run on {pbf.name}: {exc}"
            )
        digest = hashed.stdout.split()[0] if hashed.stdout.split() else ""
        if hashed.returncode != 0 or digest in ("", _EMPTY_SHA256):
            # sha256sum fails on a missing file; an empty one hashes to the
            # empty digest. Either way maptool wrote nothing (D-031).
            _remove_as(drop, staged)
            return self.ledger.fail(
                region.slug,
                f"{region.region}: maptool did not convert {pbf.name} (exit "
                f"{result.returncode}): it wrote no output",
            )
        converted["sha256"] = digest
        return f"converted {pbf.name} (staged, as the operator)"

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
        drop = self._as_operator()
        try:
            if drop is None:
                writer.install_verified(
                    staged, dest, algorithm="sha256", digest=converted["sha256"]
                )
            else:
                # Root never opens the operator's path: the operator's own
                # process reads it into a pipe, and root publishes the bytes
                # only if they hash to what the conversion step measured.
                reader = subprocess.Popen(
                    ["cat", "--", str(staged)],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                    **_as(drop),
                )
                assert reader.stdout is not None
                try:
                    writer.install_stream(
                        reader.stdout,
                        dest,
                        algorithm="sha256",
                        digest=converted["sha256"],
                        what=str(staged),
                    )
                finally:
                    reader.stdout.close()
                    reader.wait()
            writer.write_text(dest.with_name(dest.name + SOURCE), f"{region.snapshot}\n")
        except (BackendError, OSError) as exc:
            return self.ledger.fail(region.slug, f"{region.region}: {exc}")
        finally:
            if drop is None:
                staged.unlink(missing_ok=True)
            else:
                _remove_as(drop, staged)
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
