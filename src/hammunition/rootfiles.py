# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""Writing a root-owned file so nobody ever reads half of it.  D-056, D-058.

Two rules, both learned on the kept-off rules file (#119):

- **Write a unique temp file beside the target, fsync it, then ``os.replace``.**
  A reader sees the old file or the new one, never a splice. A fixed temp name
  lets two runs interleave into one file; ``mkstemp`` cannot collide. The temp
  name is hidden and ends ``.tmp``, so neither udev (``*.rules``) nor ntpd
  (``*.conf``) ever reads it, and it is unlinked on any failure.
- **Hold an flock on the directory across a read-modify-write**, so a second
  run reads the first run's result instead of overwriting it. The directory
  itself is locked, so no lock file is left behind.

Neither decides *which* path may be written. Every caller admits its own
paths with an exact-path guard before it gets here.
"""

from __future__ import annotations

import contextlib
import fcntl
import os
import tempfile
from collections.abc import Iterator
from pathlib import Path

__all__ = ["atomic_write", "dir_lock"]


def atomic_write(path: Path, content: str, *, mode: int = 0o644) -> None:
    """Replace ``path`` with ``content`` in one step, at ``mode``."""
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.stem}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(content)
            fh.flush()
            os.fsync(fh.fileno())
        os.chmod(tmp, mode)
        os.replace(tmp, path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise


@contextlib.contextmanager
def dir_lock(directory: Path) -> Iterator[None]:
    """An exclusive flock on ``directory`` for the length of the ``with`` block."""
    fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        os.close(fd)
