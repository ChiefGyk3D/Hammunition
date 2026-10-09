# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""Network isolation for offline work.  #381, Task 13.

Only a pinned tarball or .deb comes from the Bunker. Upstream's build code and a
.deb's maintainer scripts then run arbitrary code, so offline they run with no
network:

* **Source builds** run in ``bwrap``: ``--unshare-net`` (no IP, no abstract
  sockets), the whole filesystem read-only (``--ro-bind / /``) with writable
  binds only for the build tree and the install prefix, and private tmpfs over
  ``/run``, ``/var/run``, ``/tmp``, ``/var/tmp`` and ``$XDG_RUNTIME_DIR``, so
  the host's filesystem UNIX sockets (docker, podman, a proxy, dbus) are not
  there to connect to. ``unshare -rn`` is *not* used for builds: it hides no
  filesystem, and rebuilding the same isolation from mount namespaces by hand
  (read-only remounts, selective writable binds) would be a second, less
  reviewed sandbox. With no working bwrap an offline source build is refused.
* **Vendor .deb installs** run under ``unshare --net`` (they are already root),
  which is enough for a root process that must merely not reach the network.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

__all__ = [
    "BWRAP",
    "bwrap_prefix",
    "detect",
    "have_unshare",
    "runtime_dir",
    "sandbox",
    "unshare_net",
]

BWRAP = "bwrap"


def runtime_dir() -> str | None:
    """``$XDG_RUNTIME_DIR``, where a user's dbus, wayland and agent sockets live."""
    return os.environ.get("XDG_RUNTIME_DIR") or None


def bwrap_prefix(
    writable: Sequence[Path],
    *,
    runtime_dir: str | None = None,
    var_run_is_directory: bool | None = None,
) -> tuple[str, ...]:
    """The bwrap command line up to and including ``--``.

    Everything is read-only except *writable* (bound if it exists), and /run,
    /var/run (when it is a real directory rather than a link to /run), /tmp,
    /var/tmp and *runtime_dir* are empty private tmpfs."""
    if var_run_is_directory is None:
        var_run_is_directory = os.path.isdir("/var/run") and not os.path.islink("/var/run")
    hidden = ["/run", *(["/var/run"] if var_run_is_directory else []), "/tmp", "/var/tmp"]
    if runtime_dir:
        hidden.append(runtime_dir)
    return (
        "bwrap",
        "--die-with-parent",
        "--new-session",
        "--unshare-net",
        "--ro-bind",
        "/",
        "/",
        "--dev",
        "/dev",
        "--proc",
        "/proc",
        *(arg for path in hidden for arg in ("--tmpfs", path)),
        *(arg for path in writable for arg in ("--bind-try", str(path), str(path))),
        "--",
    )


def sandbox(
    argv: Sequence[str], *, writable: Sequence[Path], var_run_is_directory: bool | None = None
) -> tuple[str, ...]:
    """*argv* inside the build sandbox, with this environment's runtime dir hidden."""
    return (
        *bwrap_prefix(
            writable, runtime_dir=runtime_dir(), var_run_is_directory=var_run_is_directory
        ),
        *argv,
    )


def unshare_net(argv: Sequence[str]) -> tuple[str, ...]:
    """*argv* in a fresh network namespace. For a command that already runs as
    root (a vendor .deb's apt-get); it needs no user namespace."""
    return ("unshare", "--net", "--", *argv)


def have_unshare(which: Callable[[str], str | None] = shutil.which) -> bool:
    """Whether ``unshare`` is installed (it is part of util-linux)."""
    return which("unshare") is not None


def detect(run: Callable[..., Any] = subprocess.run) -> str | None:
    """``"bwrap"`` when the full build sandbox runs a command on this machine,
    else None. Probed with the same options a build gets."""
    if shutil.which(BWRAP) is None:
        return None
    try:
        result = run(
            (*bwrap_prefix((), runtime_dir=runtime_dir()), "true"),
            capture_output=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return BWRAP if result.returncode == 0 else None
