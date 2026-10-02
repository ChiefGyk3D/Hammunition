# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""Pointing SPLAT! at Hammunition's terrain.  D-061, amended 2026-10-02.

SPLAT looks for its terrain files in the working directory, then in ``-d
<dir>``, then in the one line of ``~/.splat_path``, its "directory path of
last resort" (``splat(1)``; measured on 1.4.2: with or without the trailing
slash). That file is the operator's, so it is written only when it is
absent, atomically, mode 0644; one naming another directory is the
operator's choice and is left alone; a symbolic link or anything but a
regular file in its place is refused and nothing changes. Nothing writes it
during an install, which runs under ``sudo``.
"""

from __future__ import annotations

import os
import stat
from pathlib import Path
from typing import Literal

State = Literal["written", "already", "other"]


class SplatPathError(Exception):
    """``~/.splat_path`` is something this will not read or replace."""


def splat_path_file(home: Path | None = None) -> Path:
    return (home or Path.home()) / ".splat_path"


def _same(line: str, directory: Path) -> bool:
    return line.strip().rstrip("/") == str(directory).rstrip("/")


def read_line(path: Path) -> str | None:
    """The first line of *path*, None when it does not exist."""
    try:
        info = os.lstat(path)
    except FileNotFoundError:
        return None
    if stat.S_ISLNK(info.st_mode):
        raise SplatPathError(f"{path} is a symbolic link; it is left alone")
    if not stat.S_ISREG(info.st_mode):
        raise SplatPathError(f"{path} is not a regular file; it is left alone")
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    with os.fdopen(fd) as handle:
        return handle.readline()


def ensure_splat_path(path: Path, directory: Path) -> State:
    """Name *directory* in *path* if it is absent; what was found."""
    line = read_line(path)
    if line is not None:
        return "already" if _same(line, directory) else "other"
    temporary = path.with_name(f"{path.name}.part.{os.getpid()}")
    fd = os.open(
        temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600
    )
    try:
        with os.fdopen(fd, "w") as handle:
            handle.write(f"{str(directory).rstrip('/')}/\n")
        os.chmod(temporary, 0o644)
        # Linked, not renamed: an operator who created the file meanwhile
        # keeps theirs, and the temporary goes either way.
        os.link(temporary, path)
    except FileExistsError:
        return "already" if _same(read_line(path) or "", directory) else "other"
    finally:
        temporary.unlink(missing_ok=True)
    return "written"
