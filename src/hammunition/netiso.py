# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""Network isolation for offline builds.  #381, Task 13.

Only a pinned source tarball comes from the Bunker. Upstream's own build then
runs arbitrary code (a Makefile may ``curl`` anything), so an offline build
runs in a fresh network namespace: ``bwrap --unshare-net`` if it works, else
``unshare -rn``. :func:`detect` asks the machine, once, at plan time; with
neither usable an offline source build is refused.
"""

from __future__ import annotations

import shutil
import subprocess
from collections.abc import Callable, Sequence
from typing import Any

__all__ = ["BWRAP", "UNSHARE", "detect", "wrap"]

BWRAP = "bwrap"
UNSHARE = "unshare"

_BWRAP_PREFIX = ("bwrap", "--unshare-net", "--dev-bind", "/", "/", "--")


def wrap(argv: Sequence[str], kind: str, *, privileged: bool) -> tuple[str, ...]:
    """*argv* inside the sandbox *kind*. A privileged command already runs as
    root (through sudo), where a user namespace is not needed."""
    if kind == BWRAP:
        return (*_BWRAP_PREFIX, *argv)
    if kind == UNSHARE:
        return ("unshare", "-n" if privileged else "-rn", "--", *argv)
    raise ValueError(f"unknown network sandbox {kind!r}")


def detect(
    run: Callable[..., Any] = subprocess.run,
) -> str | None:
    """The first sandbox that really runs a command on this machine, else None."""
    for kind in (BWRAP, UNSHARE):
        if shutil.which(kind) is None:
            continue
        try:
            result = run(
                wrap(("true",), kind, privileged=False),
                capture_output=True,
                timeout=10,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            continue
        if result.returncode == 0:
            return kind
    return None
