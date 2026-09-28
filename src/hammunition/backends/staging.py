# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""Converters run as the operator, in the operator's staging directory.  D-061.

The rule piece 1 wrote into :mod:`hammunition.backends.derived` for maptool
(D-057), made one object for the converters piece 2 adds -- mkgmap, Routino's
planetsplitter and GDAL: a parser of downloaded data does not run as root
where it need not. When the engine is root on an operator's behalf, every
staging-side operation -- create, run, hash, read, remove -- is a process
dropped to the operator, who can only do to a path under their own home what
they could already do; root's one look is an ``lstat`` that refuses a staging
directory that is a symlink or not a directory. Publishing into the prefix
reads the staged file through a pipe the operator's own ``cat`` fills, and
installs the bytes only when they hash to what the operator's ``sha256sum``
measured (:meth:`PrefixWriter.install_stream`).

Root never runs a converter as root. With no ``owner`` named, the operator is
the account whose home the staging directory is under; with nobody there,
every operation is refused by name. A dropped process gets a minimal
environment -- ``PATH``, the operator's ``HOME``, ``USER``, ``LOGNAME``, the
locale when set, and the converter's own ``environ`` -- never root's.

Every command is ``env -C <dir> [NAME=VALUE...] flock ... <argv>``: the chdir
is the child's own, after the drop, never root's before it; and the argv is
fixed by the converter that calls this, never read from a manifest.

Two conversions never share a working directory. maptool writes fixed-name
temporary files into its cwd, and two runs in one directory crash each other
(measured 2026-09-28: two parallel runs segfaulted). :meth:`Staging.workdir`
gives each conversion its own subdirectory at a stable path, so the next run's
``remove_tree`` clears a crashed run's leftovers; and :meth:`Staging.run`
holds an ``flock`` on ``<cwd>.lock`` beside it for the whole run, taken by the
operator's own ``flock(1)``, so a run in a directory another run -- in this
process or any other -- is using is refused with return code 125, not started.
"""

from __future__ import annotations

import os
import pwd
import re
import stat
import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..paths import _operator_home, operator_dir_problem
from .base import BackendError
from .verified import PrefixWriter, digest_of

__all__ = ["Staging", "staging_refusal"]

EMPTY_SHA256 = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"

#: The return code of a refused run: the directory was busy, or there was
#: nobody but root to run it as. ``env`` exits 125 for its own failures too.
REFUSED = 125

#: ``flock --verbose``'s own lines on success, removed from the converter's stderr.
_FLOCK_CHATTER = re.compile(r"^flock: (getting lock took .* seconds|executing .*)$")
_FLOCK_BUSY = "flock: failed to get lock"


def staging_refusal(staging: Path) -> str | None:
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
class Staging:
    """One converter's staging directory, and who works in it."""

    directory: Path
    owner: str | None = None
    """Who the converter runs as when the engine itself is root."""
    euid: int | None = None
    """Who the engine is; None reads this process."""
    environ: Mapping[str, str] = field(default_factory=dict)
    """Extra environment for every command (``JAVA_OPTS`` for the splitter)."""

    def _operator(self) -> tuple[pwd.struct_passwd | None, str | None]:
        """(the account to drop to, None); (None, None) when the engine is not
        root; (None, why) when root has nobody to run as but itself."""
        euid = os.geteuid() if self.euid is None else self.euid
        if euid != 0:
            return None, None
        if self.owner and self.owner != "root":
            try:
                entry = pwd.getpwnam(self.owner)
            except KeyError:
                return None, (
                    f"the operator {self.owner!r} has no account on this machine; "
                    f"refusing to run a converter in {self.directory} as root"
                )
            if entry.pw_uid != 0:
                return entry, None
        found = _operator_home(self.directory, None)
        if found is None:
            return None, (
                f"{self.directory} is under no operator's home and no operator was named; "
                f"refusing to run a converter as root. Run the install with sudo from "
                f"the operator's account."
            )
        return found, None

    def drop(self) -> tuple[int, int] | None:
        """(uid, gid) to run as, when the engine is root on an operator's behalf.

        None when the engine is not root -- or when it is and has nobody to drop
        to, which every operation then refuses rather than run as root.
        """
        entry, _ = self._operator()
        return None if entry is None else (entry.pw_uid, entry.pw_gid)

    def _as(self) -> dict[str, Any]:
        entry, _ = self._operator()
        if entry is None:
            return {}
        env = {
            "PATH": os.environ.get("PATH") or os.defpath,
            "HOME": entry.pw_dir,
            "USER": entry.pw_name,
            "LOGNAME": entry.pw_name,
        }
        for name in ("LANG", "LC_ALL"):
            if name in os.environ:
                env[name] = os.environ[name]
        env.update(self.environ)
        return {"user": entry.pw_uid, "group": entry.pw_gid, "extra_groups": [], "env": env}

    def _refusal(self) -> str | None:
        return self._operator()[1]

    def prepare(self, *subdirectories: Path) -> str | None:
        """Create the staging directory and *subdirectories*; why not, or None."""
        entry, refusal = self._operator()
        if refusal is not None:
            return refusal
        if entry is not None:
            refusal = staging_refusal(self.directory) or operator_dir_problem(
                self.directory, entry.pw_name
            )
            if refusal is not None:
                return refusal
        made = self._subprocess(
            ["install", "-d", "-m", "0755", "--", str(self.directory), *map(str, subdirectories)]
        )
        if made.returncode != 0:
            return f"could not create {self.directory}: {made.stderr.strip()[-300:]}"
        return None

    def workdir(self, name: str) -> Path:
        """This conversion's own working directory under the staging directory.

        *name* is one plain path component naming the conversion (a region's
        slug, a tile). The path is stable, so the caller's ``remove_tree`` before
        :meth:`prepare` clears whatever a crashed run left there.
        """
        if not name or name in (".", "..") or "/" in name or "\0" in name:
            raise ValueError(f"not a plain working-directory name: {name!r}")
        return self.directory / f"{name}.work"

    def run(self, argv: Sequence[str], *, cwd: Path) -> subprocess.CompletedProcess[str]:
        """*argv* in *cwd*, as the operator when the engine is root.

        Holds an ``flock`` on ``<cwd>.lock`` for the run. Returns
        :data:`REFUSED` (125) without starting *argv* when another run holds
        it, or when root has nobody to run as.
        """
        assignments = [f"{name}={value}" for name, value in self.environ.items()]
        lock = cwd.with_name(cwd.name + ".lock")
        command = [
            "env",
            "-C",
            str(cwd),
            *assignments,
            "flock",
            "--verbose",
            "--nonblock",
            "--conflict-exit-code",
            str(REFUSED),
            str(lock),
            *argv,
        ]
        result = self._subprocess(command)
        lines = result.stderr.splitlines(keepends=True)
        if result.returncode == REFUSED and any(line.strip() == _FLOCK_BUSY for line in lines):
            result.stderr = (
                f"{cwd} is the working directory of another conversion that is still "
                f"running ({lock} is held); two conversions never share one\n"
            )
            return result
        result.stderr = "".join(
            line for line in lines if not _FLOCK_CHATTER.match(line.rstrip("\n"))
        )
        return result

    def _subprocess(self, argv: Sequence[str]) -> subprocess.CompletedProcess[str]:
        refusal = self._refusal()
        if refusal is not None:
            return subprocess.CompletedProcess(list(argv), REFUSED, "", refusal)
        try:
            return subprocess.run(
                list(argv), capture_output=True, text=True, check=False, **self._as()
            )
        except OSError as exc:
            return subprocess.CompletedProcess(list(argv), 127, "", str(exc))

    def digest(self, path: Path) -> str | None:
        """sha256 of *path* when it is a non-empty file, else None (D-031: the
        output is checked, not the exit status)."""
        entry, refusal = self._operator()
        if refusal is not None:
            return None
        if entry is None:
            try:
                if path.stat().st_size == 0:
                    return None
                return digest_of(path)
            except (OSError, BackendError):
                return None
        hashed = self._subprocess(["sha256sum", "--", str(path)])
        digest = hashed.stdout.split()[0] if hashed.stdout.split() else ""
        if hashed.returncode != 0 or digest in ("", EMPTY_SHA256):
            return None
        return digest

    def remove_tree(self, path: Path) -> None:
        """Remove *path* and everything under it, as the operator; never fails.
        Does nothing when root has nobody to run as."""
        self._subprocess(["rm", "-rf", "--one-file-system", "--", str(path)])

    def publish(self, staged: Path, dest: Path, *, digest: str, writer: PrefixWriter) -> None:
        """Install *staged* at *dest*, only if it still hashes to *digest*."""
        entry, refusal = self._operator()
        if refusal is not None:
            raise BackendError(refusal)
        if entry is None:
            writer.install_verified(staged, dest, algorithm="sha256", digest=digest)
            return
        # Root never opens the operator's path: the operator's own process
        # reads it into a pipe, and root publishes the bytes only if they hash
        # to what the operator's sha256sum measured.
        reader = subprocess.Popen(
            ["cat", "--", str(staged)],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            **self._as(),
        )
        assert reader.stdout is not None
        try:
            writer.install_stream(
                reader.stdout, dest, algorithm="sha256", digest=digest, what=str(staged)
            )
        finally:
            reader.stdout.close()
            reader.wait()
