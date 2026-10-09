# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""Network isolation for offline work.  #381, Task 13.

Only a pinned tarball or .deb comes from the Bunker. Upstream's build code and a
.deb's maintainer scripts then run arbitrary code, so offline they run with no
network — and, because a pathname UNIX socket is not blocked by
``--unshare-net`` (it carries no IP, but ``connect(2)`` to an existing socket
file does not go through the network stack at all), each also has the socket's
usual hiding places hidden behind a private tmpfs rather than merely a
read-only bind, which still leaves an existing socket connectable:

* **Source builds** run in ``bwrap``: ``--unshare-net`` (no IP, no abstract
  sockets), the filesystem read-only (``--ro-bind / /``) with writable binds
  only for the build tree and the install prefix, and private tmpfs over
  ``/run``, ``/var/run``, ``/tmp``, ``/var/tmp``, ``$XDG_RUNTIME_DIR``,
  ``$HOME``, ``/root``, ``/opt``, ``/usr/local``, ``/srv``, ``/mnt`` and
  ``/media`` — nothing a source build legitimately reads from, and exactly
  where a docker, podman, proxy or dbus socket is likely to live. Hiding them
  is safe here because the sandbox is read-only outside the two writable
  binds: a build cannot be relying on writing there, and the two writable
  binds are re-applied after the hides, so a build tree or prefix that lives
  under one of them (``$HOME`` or ``/usr/local`` by default) still works.
  ``unshare -rn`` is *not* used for builds: it hides no filesystem, and
  rebuilding the same isolation from mount namespaces by hand (read-only
  remounts, selective writable binds) would be a second, less reviewed
  sandbox. With no working bwrap an offline source build is refused.
* **Vendor .deb installs** run in ``bwrap`` too, but with the filesystem left
  writable (``--bind / /``): apt is doing a real, system-wide install and may
  legitimately write anywhere dpkg's file lists call for, including ``/opt``
  or ``/usr/local``, so those are not hidden — a private tmpfs over either
  would silently discard whatever the package installed there. Only
  ``/run``, ``/var/run``, ``/tmp``, ``/var/tmp``, ``$XDG_RUNTIME_DIR``,
  ``$HOME`` and ``/root`` are hidden: no .deb's file list legitimately
  touches the operator's home or a runtime directory, so hiding them closes
  the same maintainer-script/trigger socket bridge with no risk of discarding
  an installed file. With no working bwrap the vendor .deb unit is refused.
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
    "bwrap_writable_prefix",
    "detect",
    "home_dir",
    "privileged_sandbox",
    "runtime_dir",
    "sandbox",
]

BWRAP = "bwrap"

# Locations a build or a .deb's maintainer scripts have no legitimate reason
# to read, and where a host service's pathname UNIX socket is likely to be
# found. Only hidden for the read-only build sandbox: a .deb installing to
# any of these would have its files silently discarded by a private tmpfs.
_BUILD_ONLY_HIDDEN = ("/opt", "/usr/local", "/srv", "/mnt", "/media")


def runtime_dir() -> str | None:
    """``$XDG_RUNTIME_DIR``, where a user's dbus, wayland and agent sockets live."""
    return os.environ.get("XDG_RUNTIME_DIR") or None


def home_dir() -> str | None:
    """``$HOME``, where ssh keys, user caches and a user-run proxy or agent
    socket live. Read from the environment of the process building the
    sandbox, not of whatever it eventually runs as (sudo resets ``HOME``)."""
    return os.environ.get("HOME") or None


def _home_and_root_hidden(home: str | None) -> list[str]:
    """``$HOME`` (unless it already is ``/root``) and ``/root``, each listed once."""
    hidden = [home] if home and home != "/root" else []
    hidden.append("/root")
    return hidden


def _common_hidden(
    *, runtime_dir: str | None, var_run_is_directory: bool | None, home: str | None
) -> list[str]:
    if var_run_is_directory is None:
        var_run_is_directory = os.path.isdir("/var/run") and not os.path.islink("/var/run")
    hidden = ["/run", *(["/var/run"] if var_run_is_directory else []), "/tmp", "/var/tmp"]
    if runtime_dir:
        hidden.append(runtime_dir)
    hidden.extend(_home_and_root_hidden(home))
    return hidden


def bwrap_prefix(
    writable: Sequence[Path],
    *,
    runtime_dir: str | None = None,
    var_run_is_directory: bool | None = None,
    home: str | None = None,
) -> tuple[str, ...]:
    """The read-only build sandbox's command line up to and including ``--``.

    Everything is read-only except *writable* (bound if it exists), and
    /run, /var/run (when it is a real directory rather than a link to /run),
    /tmp, /var/tmp, *runtime_dir*, *home*, /root, /opt, /usr/local, /srv,
    /mnt and /media are empty private tmpfs."""
    hidden = _common_hidden(
        runtime_dir=runtime_dir, var_run_is_directory=var_run_is_directory, home=home
    )
    hidden.extend(_BUILD_ONLY_HIDDEN)
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


def bwrap_writable_prefix(
    *,
    runtime_dir: str | None = None,
    var_run_is_directory: bool | None = None,
    home: str | None = None,
) -> tuple[str, ...]:
    """The privileged .deb-install sandbox's command line up to and including
    ``--``. The filesystem stays writable (``--bind / /``) everywhere except
    /run, /var/run, /tmp, /var/tmp, *runtime_dir*, *home* and /root, which are
    empty private tmpfs."""
    hidden = _common_hidden(
        runtime_dir=runtime_dir, var_run_is_directory=var_run_is_directory, home=home
    )
    return (
        "bwrap",
        "--die-with-parent",
        "--new-session",
        "--unshare-net",
        "--bind",
        "/",
        "/",
        "--dev",
        "/dev",
        "--proc",
        "/proc",
        *(arg for path in hidden for arg in ("--tmpfs", path)),
        "--",
    )


def sandbox(
    argv: Sequence[str], *, writable: Sequence[Path], var_run_is_directory: bool | None = None
) -> tuple[str, ...]:
    """*argv* inside the read-only build sandbox, with this environment's
    runtime dir and home hidden."""
    return (
        *bwrap_prefix(
            writable,
            runtime_dir=runtime_dir(),
            var_run_is_directory=var_run_is_directory,
            home=home_dir(),
        ),
        *argv,
    )


def privileged_sandbox(argv: Sequence[str]) -> tuple[str, ...]:
    """*argv* as the real root, filesystem writable, for installing a vendor
    .deb offline — with this environment's runtime dir and home hidden, so a
    maintainer script or triggered handler cannot bridge to a host service
    through a pathname socket there."""
    return (*bwrap_writable_prefix(runtime_dir=runtime_dir(), home=home_dir()), *argv)


def detect(run: Callable[..., Any] = subprocess.run) -> str | None:
    """``"bwrap"`` when bwrap can sandbox a command on this machine, else
    None. Probed with the read-only build sandbox's options: what fails or
    succeeds here is namespace creation, which the writable .deb sandbox
    shares — not which paths are read-only or hidden."""
    if shutil.which(BWRAP) is None:
        return None
    try:
        result = run(
            (*bwrap_prefix((), runtime_dir=runtime_dir(), home=home_dir()), "true"),
            capture_output=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return BWRAP if result.returncode == 0 else None
