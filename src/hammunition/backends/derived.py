# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""The derived backend: another unit's data, converted for an application.  D-057.

The catalog names the converter by enum (``navit-maptool``) and the engine
owns what that means, exactly as ``build_system: cmake`` is an enum the
source backend implements; no command line ever comes from a manifest.

For ``navit-maptool``, each region takes two steps:

* **convert**, unprivileged, as the operator in a staging directory the
  operator owns -- under root it drops to the operator first. maptool
  parses downloaded data, and a parser of downloaded data does not run as
  root where it need not (the "drop to user where possible" rule). First
  the region is merged with a closed border for its country (the
  address-search fix, D-057 amendment, 2026-09-28): the border is written
  as OSM XML from the ``boundaries`` unit's Natural Earth file
  (:mod:`hammunition.country_boundaries`), piped into ``osmium cat`` and
  merged with ``osmium merge``; then ``maptool --protobuf -U -i <merged>
  <staged>``. A region whose country is not known is converted unmerged,
  and the step says so. maptool's log is read for "Broken country
  polygon" on the merged border's relation (the warning for the extract's
  own partial relation is expected), and the merged copies are removed. The
  effect is checked, not the exit status (D-031): the output must exist
  and be non-empty, and its digest is taken there.
* **install**, as root only where the prefix needs it: the staged map is
  copied into ``<data>/<unit>/<slug>.bin`` re-verified against that digest
  without following a symlink, with a ``<slug>.bin.source`` sidecar holding
  the snapshot. maptool's leftover per-country scratch is then removed from
  the staging directory, by name through a descriptor that never follows a
  link (a successful conversion left it there on the field laptop).

A region already converted from the same snapshot is not converted again; a
region no longer in station config loses its ``.bin`` (one the plan kept
because it could not be checked for a newer map does not). Last,
``navit.xml`` is written beside the maps from the installed stock config
(:mod:`hammunition.navit_config`), listing every map that exists then,
opening on the first of them -- the midpoint of the bbox in its source
``.osm.pbf``'s header (:mod:`hammunition.osm_pbf`) -- and following the
gpsd vehicle. The stock centre is Munich; Navit opened there, on a blank
screen, on the field laptop (2026-09-28).

A region that failed -- to download, to verify, to convert -- is recorded in
the shared :class:`~hammunition.backends.regions.MapLedger`, the others
continue, and the ledger fails the transaction by name at its end.
"""

from __future__ import annotations

import contextlib
import os
import pwd
import re
import stat
import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from functools import partial
from pathlib import Path
from typing import Any

from .. import navit_config, osm_pbf
from ..country_boundaries import (
    BoundarySource,
    Country,
    CountryBoundaryError,
    boundary_xml,
    read_countries,
)
from ..geofabrik import RegionFile
from ..manifest.schema import DerivedDataInstall, PackageManifest
from ..paths import OperatorDirError, open_operator_dir, operator_dir_problem
from .base import Action, BackendError, Command, CommandRunner
from .data import human_size
from .regions import (
    BIN_FACTOR,
    ESTIMATE,
    MERGE_FACTOR,
    PBF,
    SCRATCH_FACTOR,
    SOURCE,
    MapLedger,
    bin_estimate,
    data_root,
    installed_converter,
    installed_snapshot,
    prefix_writer,
    removal_steps,
)
from .verified import PrefixWriter, digest_of

BIN = ".bin"
#: What a ``.bin`` was built by, recorded on the second line of its
#: ``.source`` sidecar. Bumped whenever the converter's output changes, so
#: every map built by an older one is converted again even though its source
#: snapshot has not moved. Version 1, never written, is maptool alone
#: (v0.12.0 and before); 2 merges the country border and runs with -U.
CONVERTER = "navit-maptool 2"
#: maptool's log line for a country relation it could not close:
#: ``OSM Warning:http://www.openstreetmap.org/relation/<id> Broken country
#: polygon 'US'`` (maptool/boundaries.c).
_BROKEN = re.compile(r"relation/(\d+) Broken country polygon")
#: maptool's log line for a relation it took as a country:
#: ``OSM Info:http://www.openstreetmap.org/relation/<id> Country Boundary for
#: 'US'`` (maptool/boundaries.c). The positive half of the success check.
_RECOGNISED = re.compile(r"relation/(\d+) Country Boundary for '")
_EMPTY_SHA256 = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
#: maptool's per-country boundary scratch, the files it left in the staging
#: directory after a successful conversion on the field laptop (2026-09-28):
#: ``country_<id>_broken_.tmp`` and ``country_<id>_poly_.tmp``. Exactly these
#: two shapes; nothing else in the directory is removed, least of all another
#: region's ``.bin.part``.
_SCRATCH = re.compile(r"country_[A-Za-z0-9]+_(?:broken|poly)_\.tmp")
SCRATCH_PATTERNS = "country_*_broken_.tmp, country_*_poly_.tmp"


def _maptool_argv(pbf: Path, staged: Path) -> list[str]:
    """The fixed argv ``navit-maptool`` means. Nothing in it comes from a manifest.

    ``-U`` (``--unknown-country``) indexes a town that lies inside no
    country boundary under a pseudo-country "Unknown" instead of dropping it
    from the search index: the net for the few places Natural Earth's coarse
    border misses (a few, on one US-state-sized region, 2026-09-28)."""
    return ["maptool", "--protobuf", "-U", "-i", str(pbf), str(staged)]


def _osmium_cat_argv(out: Path) -> list[str]:
    """OSM XML on stdin to a pbf: the border never touches disk as XML."""
    return ["osmium", "cat", "-F", "osm", "-o", str(out), "--overwrite", "-"]


def _osmium_merge_argv(pbf: Path, boundary: Path, out: Path) -> list[str]:
    return ["osmium", "merge", str(pbf), str(boundary), "-o", str(out), "--overwrite"]


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
    """Turns a ``derived`` block and the resolved regions into conversion steps.

    **Every conversion runs alone, never in parallel.** maptool writes
    fixed-name scratch files (``coords.tmp``, ``ways_.tmp``, ...) into its
    working directory, and every region converts in the one staging
    directory; two maptool runs there at once segfault (measured on the
    field laptop, 2026-09-28). Each step blocks on ``subprocess.run`` until
    its child exits, and the steps run one after another.
    """

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
    boundaries: BoundarySource | None = None
    """The installed country-border file, when the block names a boundaries unit."""
    countries: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
    """Region path -> ISO codes (``catalog/data/geofabrik-countries.yaml``)."""
    _natural_earth: dict[str, Mapping[str, Country]] = field(
        default_factory=dict, compare=False, repr=False
    )
    """The boundary file, parsed once per run: 13 MB, 239 countries."""
    method = "derived"

    @property
    def writer(self) -> PrefixWriter:
        return prefix_writer(self.prefix, self.privileged, self.runner, self.euid)

    def data_dir(self, manifest: PackageManifest) -> Path:
        return data_root(self.prefix) / manifest.name

    def codes_for(self, region: RegionFile) -> tuple[str, ...]:
        """The countries whose border is merged into *region*; none without a file."""
        if self.boundaries is None:
            return ()
        # The region, else the nearest parent path in the table: a region
        # Geofabrik added after the table was generated (review M-3).
        parts = region.region.split("/")
        for end in range(len(parts), 0, -1):
            codes = self.countries.get("/".join(parts[:end]))
            if codes:
                return tuple(codes)
        return ()

    def steps(self, manifest: PackageManifest, block: DerivedDataInstall) -> list[Action | Command]:
        # One converter today; the schema's enum refuses anything else, and a
        # new member must be implemented here before a manifest can name it.
        if block.converter != "navit-maptool":  # pragma: no cover
            raise BackendError(f"{manifest.name}: converter {block.converter!r} is not implemented")
        if block.boundaries is not None and self.boundaries is None:
            raise BackendError(
                f"{manifest.name}: the block merges country borders from "
                f"{block.boundaries}, and no boundary file was given to the converter"
            )
        out = self.data_dir(manifest)
        source_dir = data_root(self.prefix) / block.source
        writer = self.writer
        changed = self.converter_changed(manifest)
        steps: list[Action | Command] = []
        for region in self.files:
            pbf = source_dir / f"{region.slug}{PBF}"
            dest = out / f"{region.slug}{BIN}"
            if self._current(dest, region):
                continue
            staged = self.staging / f"{region.slug}{BIN}.part"
            converted: dict[str, str] = {}
            estimate = human_size(bin_estimate(region.size))
            codes = self.codes_for(region)
            merged = self.staging / f"{region.slug}.merged{PBF}"
            if codes:
                merge = (
                    f"merge the country border of {', '.join(codes)} (Natural Earth) into "
                    f"{pbf} with osmium merge, as {merged} (about "
                    f"{human_size(region.size * MERGE_FACTOR)}, removed afterwards); then "
                )
                reads = merged
            elif self.boundaries is not None:
                merge = (
                    f"no country is known for {region.region}, so no border is merged "
                    f"and towns outside every boundary are indexed under Unknown; "
                )
                reads = pbf
            else:
                merge, reads = "", pbf
            why = " (converter changed)" if region.slug in changed else ""
            steps.append(
                Action(
                    kind="convert",
                    description=(
                        f"Convert map region {region.region} ({region.snapshot}) for Navit"
                        f"{why}, as the operator, in {self.staging}: {merge}"
                        f"{' '.join(_maptool_argv(reads, staged))}; output about "
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
                    description=(
                        f"Install the Navit map of {region.region} ({region.snapshot}), then "
                        f"remove maptool's leftover scratch ({SCRATCH_PATTERNS}) from "
                        f"{self.staging}"
                    ),
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
                    f"(speech through espeak-ng, one mapset of the regions above, "
                    f"centred on the first region whose header gives a bounding box, else "
                    f'the stock centre; the GPS vehicle with follow="1" where the stock '
                    f"file has exactly one)"
                ),
                detail=str(config),
                perform=partial(
                    self._write_config,
                    tuple((out / f"{s}{BIN}", source_dir / f"{s}{PBF}") for s in slugs),
                    config,
                    writer,
                ),
                requires_root=writer.privileged,
            )
        )
        return steps

    def pending(self, manifest: PackageManifest) -> list[RegionFile]:
        """Regions this run converts: no ``.bin``, one from another snapshot,
        or one an older converter built."""
        out = self.data_dir(manifest)
        return [f for f in self.files if not self._current(out / f"{f.slug}{BIN}", f)]

    def converter_changed(self, manifest: PackageManifest) -> set[str]:
        """Slugs whose ``.bin`` is from the right snapshot and an older converter."""
        out = self.data_dir(manifest)
        return {
            f.slug
            for f in self.files
            if (dest := out / f"{f.slug}{BIN}").is_file()
            and installed_snapshot(dest) == f.snapshot
            and installed_converter(dest) != CONVERTER
        }

    @staticmethod
    def _current(dest: Path, region: RegionFile) -> bool:
        return (
            dest.is_file()
            and installed_snapshot(dest) == region.snapshot
            and installed_converter(dest) == CONVERTER
        )

    def _as_operator(self) -> tuple[int, int] | None:
        """(uid, gid) to drop to, when the engine is root on an operator's behalf."""
        euid = os.geteuid() if self.euid is None else self.euid
        if euid != 0 or not self.owner or self.owner == "root":
            return None
        entry = pwd.getpwnam(self.owner)
        return entry.pw_uid, entry.pw_gid

    def _run(
        self, argv: list[str], drop: tuple[int, int] | None, *, stdin: str | None = None
    ) -> subprocess.CompletedProcess[str]:
        """One staging-side child, blocking until it exits (never in parallel:
        see the class docstring), in the staging directory.

        cwd: maptool writes its *.tmp scratch into its working directory --
        more than 12 GB for a 6.1 GB country-sized region -- and aborts in a
        read-only one (measured: exit 134, buffer.c:39). Under root there is
        no cwd=: subprocess would chdir there as root, before the drop, so
        env -C makes the chdir the operator's own."""
        # UTF-8 both ways, never the locale's (review M-1): the XML declares
        # UTF-8 and names such as Curaçao must reach osmium as UTF-8; a log
        # byte that is not UTF-8 is replaced, never raised.
        if drop is None:
            return subprocess.run(
                argv,
                capture_output=True,
                check=False,
                cwd=self.staging,
                input=stdin,
                encoding="utf-8",
                errors="replace",
            )
        return subprocess.run(
            ["env", "-C", str(self.staging), *argv],
            capture_output=True,
            check=False,
            input=stdin,
            encoding="utf-8",
            errors="replace",
            **_as(drop),
        )

    def _discard(self, drop: tuple[int, int] | None, *paths: Path) -> None:
        for path in paths:
            if drop is None:
                path.unlink(missing_ok=True)
            else:
                _remove_as(drop, path)

    def _countries_file(self) -> Mapping[str, Country]:
        assert self.boundaries is not None
        if "parsed" not in self._natural_earth:
            # Read as whoever the engine is: the file is this engine's own
            # install under the prefix, verified by sha256, not the operator's.
            self._natural_earth["parsed"] = read_countries(
                self.boundaries.path.read_text(encoding="utf-8")
            )
        return self._natural_earth["parsed"]

    def _merge(
        self, region: RegionFile, pbf: Path, drop: tuple[int, int] | None
    ) -> tuple[Path, dict[str, int], list[str]] | str:
        """(what maptool reads, our relation ids by code, notes), or why it failed.

        The border goes to ``osmium cat`` on stdin, so nothing root composes
        is ever written by root into the operator's directory."""
        codes = self.codes_for(region)
        if self.boundaries is None:
            return pbf, {}, []
        if not codes:
            return pbf, {}, [f"no country is known for {region.region}; no border merged"]
        try:
            countries = self._countries_file()
        except UnicodeDecodeError as exc:
            # A ValueError, not an OSError: caught here so a bad file fails
            # each region by name instead of stopping the run (review M-1).
            return f"the country borders {self.boundaries.path} are not UTF-8: {exc}"
        except (OSError, CountryBoundaryError) as exc:
            return f"cannot read the country borders {self.boundaries.path}: {exc}"
        synthesised = boundary_xml(countries, codes)
        notes = [f"Natural Earth has no border for {code}" for code in synthesised.missing]
        if not synthesised.relations:
            notes.append("no border merged")
            return pbf, {}, notes
        boundary = self.staging / f"{region.slug}.boundary{PBF}"
        merged = self.staging / f"{region.slug}.merged{PBF}"
        for argv, stdin in (
            (_osmium_cat_argv(boundary), synthesised.xml),
            (_osmium_merge_argv(pbf, boundary, merged), None),
        ):
            try:
                result = self._run(argv, drop, stdin=stdin)
            except OSError as exc:
                return (
                    f"osmium could not be run ({exc}); it comes from the osmium-tool "
                    f"package, a dependency of osm-navit"
                )
            if result.returncode != 0:
                return (
                    f"osmium {argv[1]} did not merge the country border into {pbf.name} "
                    f"(exit {result.returncode}): {result.stderr.strip()[-300:]}"
                )
        notes.insert(0, f"merged the border of {', '.join(synthesised.relations)}")
        return merged, dict(synthesised.relations), notes

    def _convert(
        self, region: RegionFile, pbf: Path, staged: Path, converted: dict[str, str]
    ) -> str:
        if region.slug in self.ledger.failed:
            return f"skipped: {region.region} did not install"
        if not pbf.is_file():
            return self.ledger.fail(region.slug, f"{region.region}: {pbf} is not installed")
        drop = self._as_operator()
        if drop is None:
            self.staging.mkdir(parents=True, exist_ok=True)
        else:
            # Every existing component from the operator's home down must be the
            # operator's own directory: a root-owned ~/.cache/hammunition left by
            # an older sudo run would make the operator's install -d fail with a
            # bare EACCES, so it is named here with its fix instead.
            refusal = _staging_refusal(self.staging) or operator_dir_problem(
                self.staging, self.owner
            )
            if refusal is not None:
                return self.ledger.fail(region.slug, f"{region.region}: {refusal}")
            try:
                made = subprocess.run(
                    ["install", "-d", "-m", "0755", "--", str(self.staging)],
                    capture_output=True,
                    text=True,
                    check=False,
                    **_as(drop),
                )
            except OSError as exc:
                return self.ledger.fail(region.slug, f"{region.region}: {exc}")
            if made.returncode != 0:
                return self.ledger.fail(
                    region.slug,
                    f"{region.region}: could not create {self.staging} as the operator: "
                    f"{made.stderr.strip()[-300:]}",
                )
        self._discard(drop, staged)
        scratch = (
            self.staging / f"{region.slug}.boundary{PBF}",
            self.staging / f"{region.slug}.merged{PBF}",
        )
        try:
            return self._merge_and_convert(region, pbf, staged, converted, drop)
        finally:
            # Region-sized copies: never left in the operator's cache, whether
            # the map built or not.
            self._discard(drop, *scratch)

    def _merge_and_convert(
        self,
        region: RegionFile,
        pbf: Path,
        staged: Path,
        converted: dict[str, str],
        drop: tuple[int, int] | None,
    ) -> str:
        merged = self._merge(region, pbf, drop)
        if isinstance(merged, str):
            return self.ledger.fail(region.slug, f"{region.region}: {merged}")
        reads, ours, notes = merged
        try:
            result = self._run(_maptool_argv(reads, staged), drop)
        except OSError as exc:
            self._discard(drop, staged)
            return self.ledger.fail(
                region.slug, f"{region.region}: maptool could not be run on {pbf.name}: {exc}"
            )
        if result.returncode != 0:
            self._discard(drop, staged)
            return self.ledger.fail(region.slug, _maptool_failure(region, pbf, result))
        log = result.stdout + result.stderr
        # Both halves (review I-1, D-031): maptool must say it took each
        # merged border as a country, and must not call one broken. With -U
        # on, a border it ignored would leave every town under Unknown and
        # look like success.
        recognised = {int(m.group(1)) for m in _RECOGNISED.finditer(log)}
        unseen = [f"{c} (relation {i})" for c, i in ours.items() if i not in recognised]
        if unseen:
            self._discard(drop, staged)
            return self.ledger.fail(
                region.slug,
                f"{region.region}: the merged country border {', '.join(unseen)} was not "
                f"recognised by maptool as a country (no 'Country Boundary for' line in its "
                f"log), so towns would be filed under Unknown, not their country",
            )
        broken = sorted({int(m.group(1)) for m in _BROKEN.finditer(log)} & set(ours.values()))
        if broken:
            # The extract's own partial relation is always "broken", and that
            # is expected; the merged border being broken means it did not close.
            self._discard(drop, staged)
            names = ", ".join(f"{c} (relation {i})" for c, i in ours.items() if i in broken)
            return self.ledger.fail(
                region.slug,
                f"{region.region}: maptool reports the merged country border {names} as "
                f"broken: it did not close, and towns would not be filed under the country",
            )
        digest = self._staged_digest(staged, drop)
        if digest is None:
            # A missing file fails to hash; an empty one hashes to the empty
            # digest. Either way maptool wrote nothing (D-031).
            self._discard(drop, staged)
            return self.ledger.fail(
                region.slug,
                f"{region.region}: maptool did not convert {pbf.name} (exit "
                f"{result.returncode}): it wrote no output",
            )
        converted["sha256"] = digest
        said = "".join(f"; {note}" for note in notes)
        who = "" if drop is None else ", as the operator"
        return f"converted {pbf.name} (staged{who}){said}"

    def _staged_digest(self, staged: Path, drop: tuple[int, int] | None) -> str | None:
        """sha256 of the staged map, or None when there is nothing there.

        Under root the operator's own ``sha256sum`` reads it: root never
        opens a path in the operator's directory."""
        if drop is None:
            try:
                if not staged.is_file() or staged.stat().st_size == 0:
                    return None
                return digest_of(staged)
            except (BackendError, OSError):
                return None
        try:
            hashed = subprocess.run(
                ["sha256sum", "--", str(staged)],
                capture_output=True,
                text=True,
                check=False,
                **_as(drop),
            )
        except OSError:
            return None
        digest = hashed.stdout.split()[0] if hashed.stdout.split() else ""
        if hashed.returncode != 0 or digest in ("", _EMPTY_SHA256):
            return None
        return digest

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
            writer.write_text(
                dest.with_name(dest.name + SOURCE), f"{region.snapshot}\nconverter: {CONVERTER}\n"
            )
        except (BackendError, OSError) as exc:
            return self.ledger.fail(region.slug, f"{region.region}: {exc}")
        finally:
            if drop is None:
                staged.unlink(missing_ok=True)
            else:
                _remove_as(drop, staged)
        return f"installed {dest}; {self._clear_scratch()}"

    def _clear_scratch(self) -> str:
        """Remove maptool's leftover scratch from the staging directory.

        Only regular files whose whole name matches :data:`_SCRATCH`, only in
        the staging directory itself, and only by name through a descriptor on
        it: :func:`~hammunition.paths.open_operator_dir` walks from the
        operator's home ``O_NOFOLLOW`` and proves each component theirs, so a
        symlink planted anywhere in the path cannot redirect the removal, and
        ``unlinkat`` on a name removes that entry, never what a link points
        at. A symlink named like scratch is not maptool's and is left. Not
        clearing is named in the outcome, never a failure: the map is
        installed, and the files are the operator's, in their cache."""
        try:
            self.staging.lstat()
        except FileNotFoundError:
            return "no maptool scratch to remove"
        except OSError as exc:
            return f"scratch not cleared: cannot inspect {self.staging}: {exc.strerror or exc}"
        try:
            fd = open_operator_dir(self.staging, self.owner)
            if fd is None:
                # Not root on someone's behalf: the plain case, still no link followed.
                fd = os.open(self.staging, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        except OperatorDirError as exc:
            return f"scratch not cleared: {exc}"
        except OSError as exc:
            return f"scratch not cleared: cannot open {self.staging}: {exc.strerror or exc}"
        removed = 0
        try:
            for name in os.listdir(fd):
                if not _SCRATCH.fullmatch(name):
                    continue
                with contextlib.suppress(FileNotFoundError):
                    if stat.S_ISREG(os.stat(name, dir_fd=fd, follow_symlinks=False).st_mode):
                        os.unlink(name, dir_fd=fd)
                        removed += 1
        except OSError as exc:
            return f"scratch not cleared: {self.staging}: {exc.strerror or exc}"
        finally:
            os.close(fd)
        return f"removed {removed} maptool scratch file(s) from {self.staging}"

    @staticmethod
    def _center(
        sources: Sequence[Path],
    ) -> tuple[tuple[float, float] | None, str | None, list[str]]:
        """(lon, lat) Navit opens on, the region it came from, and why any
        region before it was passed over.

        The first region whose ``.osm.pbf`` header has a bbox. One no longer
        installed, one whose header carries no bbox (the format allows it)
        and one that cannot be read give way to the next, and each is named
        in the step's outcome rather than failing it: a map config opening on
        the stock centre is still a working config, where a failed step would
        leave Navit none and hide the ledger's own report."""
        passed: list[str] = []
        for pbf in sources:
            try:
                bbox = osm_pbf.header_bbox(pbf)
            except FileNotFoundError:
                passed.append(f"{pbf}: not installed")
                continue
            except OSError as exc:
                passed.append(f"{pbf}: cannot read it: {exc.strerror or exc}")
                continue
            except osm_pbf.OsmPbfError as exc:
                passed.append(str(exc))
                continue
            if bbox is None:
                passed.append(f"{pbf}: its header has no bounding box")
                continue
            return osm_pbf.bbox_center(bbox), pbf.name.removesuffix(PBF), passed
        return None, None, passed

    def _write_config(
        self, maps: Sequence[tuple[Path, Path]], dest: Path, writer: PrefixWriter
    ) -> str:
        present_maps = [(b, pbf) for b, pbf in maps if b.is_file()]
        present = [b for b, _ in present_maps]
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
        center, origin, passed = self._center([pbf for _, pbf in present_maps])
        not_following = navit_config.follow_problem(text)
        try:
            body = navit_config.rewrite(text, present, center=center)
        except navit_config.NavitConfigError as exc:
            raise BackendError(f"{self.stock}: {exc}") from exc
        writer.write_text(dest, body)
        where = (
            f"opening on {navit_config.format_center(center)} (from {origin})"
            if center is not None
            else "no region's header gave a bounding box, so Navit keeps the stock centre"
        )
        skipped = "".join(f"; passed over {p}" for p in passed)
        follow = (
            "" if not_following is None else f"; Navit will not follow the GPS: {not_following}"
        )
        return f"wrote {dest} ({len(present)} map(s); {where}{skipped}{follow})"
