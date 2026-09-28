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

Every command is ``env -C <dir> [NAME=VALUE...] <argv>``: the chdir is the
child's own, after the drop, never root's before it; and the argv is fixed
by the converter that calls this, never read from a manifest.

Two conversions never share a working directory. maptool writes fixed-name
temporary files into its cwd, and two runs in one directory crash each other
(measured 2026-09-28: two parallel runs segfaulted). :meth:`Staging.workdir`
gives each conversion its own subdirectory, named by the conversion and this
process, so two engines on one staging directory do not collide either; and
:meth:`Staging.run` refuses, without starting it, a run in a directory
another run of this process is still using.
"""

from __future__ import annotations

import os
import pwd
import stat
import subprocess
import threading
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..paths import operator_dir_problem
from .base import BackendError
from .verified import PrefixWriter, digest_of

__all__ = ["Staging", "staging_refusal"]

EMPTY_SHA256 = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"

#: Working directories a run of this process is using now.
_BUSY: set[str] = set()
_BUSY_LOCK = threading.Lock()


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

    def drop(self) -> tuple[int, int] | None:
        """(uid, gid) to run as, when the engine is root on an operator's behalf."""
        euid = os.geteuid() if self.euid is None else self.euid
        if euid != 0 or not self.owner or self.owner == "root":
            return None
        entry = pwd.getpwnam(self.owner)
        return entry.pw_uid, entry.pw_gid

    def _as(self) -> dict[str, Any]:
        drop = self.drop()
        if drop is None:
            return {}
        return {"user": drop[0], "group": drop[1], "extra_groups": []}

    def prepare(self, *subdirectories: Path) -> str | None:
        """Create the staging directory and *subdirectories*; why not, or None."""
        if self.drop() is not None:
            refusal = staging_refusal(self.directory) or operator_dir_problem(
                self.directory, self.owner
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
        slug, a tile); the process id keeps two engines apart. The caller
        creates it with :meth:`prepare` and removes it with :meth:`remove_tree`.
        """
        if not name or name in (".", "..") or "/" in name or "\0" in name:
            raise ValueError(f"not a plain working-directory name: {name!r}")
        return self.directory / f"{name}.{os.getpid()}.work"

    def run(self, argv: Sequence[str], *, cwd: Path) -> subprocess.CompletedProcess[str]:
        """*argv* in *cwd*, as the operator when the engine is root.

        Refused, with a non-zero result and nothing started, while another run
        of this process is using *cwd*.
        """
        assignments = [f"{name}={value}" for name, value in self.environ.items()]
        command = ["env", "-C", str(cwd), *assignments, *argv]
        key = os.path.normpath(os.path.abspath(cwd))
        with _BUSY_LOCK:
            if key in _BUSY:
                return subprocess.CompletedProcess(
                    command,
                    125,
                    "",
                    f"{cwd} is already the working directory of another conversion; "
                    f"two conversions never share one",
                )
            _BUSY.add(key)
        try:
            return self._subprocess(command)
        finally:
            with _BUSY_LOCK:
                _BUSY.discard(key)

    def _subprocess(self, argv: Sequence[str]) -> subprocess.CompletedProcess[str]:
        try:
            return subprocess.run(
                list(argv), capture_output=True, text=True, check=False, **self._as()
            )
        except OSError as exc:
            return subprocess.CompletedProcess(list(argv), 127, "", str(exc))

    def digest(self, path: Path) -> str | None:
        """sha256 of *path* when it is a non-empty file, else None (D-031: the
        output is checked, not the exit status)."""
        if self.drop() is None:
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
        """Remove *path* and everything under it, as the operator; never fails."""
        self._subprocess(["rm", "-rf", "--one-file-system", "--", str(path)])

    def publish(self, staged: Path, dest: Path, *, digest: str, writer: PrefixWriter) -> None:
        """Install *staged* at *dest*, only if it still hashes to *digest*."""
        if self.drop() is None:
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
