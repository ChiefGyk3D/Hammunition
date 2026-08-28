# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""Where the engine keeps things, and whose they are.

Two directories matter: the transaction log under ``$XDG_STATE_HOME`` and the
verified-artifact cache under ``$XDG_CACHE_HOME``. Both face the same problem
and it is subtle enough that two copies of the answer would drift, which is why
it is written once here.

**The problem is sudo.** ``hammunition install`` needs root for ``apt-get`` and
for ``make install``, so it is usually run under sudo — and sudo resets ``HOME``
to ``/root``. Following ``$HOME`` would put the operator's transaction history
and their downloaded artifacts somewhere they cannot read, while the same
command run as themselves reports an empty log and an empty cache. The engine
already works out who the operator is, because ``gpasswd`` needs a name; this
uses that name.

``$XDG_*`` is deliberately **not** consulted in the root-with-an-owner case: it
either does not survive ``env_reset`` or it belongs to root, and neither is the
operator's.
"""

from __future__ import annotations

import contextlib
import os
import pwd
from pathlib import Path

__all__ = ["APP", "artifact_cache_dir", "owner_aware_dir", "state_dir"]

APP = "hammunition"


def owner_aware_dir(
    *,
    xdg_var: str,
    home_relative: tuple[str, ...],
    owner: str | None = None,
) -> Path:
    """The per-user ``hammunition`` directory under one XDG base.

    ``owner`` is the operator the run is *on behalf of*. It changes the answer
    only when this process is root and that operator is somebody else, which is
    exactly the ``sudo hammunition ...`` case.

    ``home_relative`` is the XDG default path from a home directory, e.g.
    ``(".local", "state")`` or ``(".cache",)``.
    """
    if owner and os.geteuid() == 0:
        entry = None
        with contextlib.suppress(KeyError):
            entry = pwd.getpwnam(owner)
        # A root-named owner is not somebody else, so it takes the ordinary
        # path rather than being treated as a handoff.
        if entry is not None and entry.pw_uid != 0:
            return Path(entry.pw_dir).joinpath(*home_relative) / APP
    base = os.environ.get(xdg_var) or str(Path.home().joinpath(*home_relative))
    return Path(base) / APP


def state_dir(owner: str | None = None) -> Path:
    """``$XDG_STATE_HOME/hammunition`` — the transaction log lives here."""
    return owner_aware_dir(xdg_var="XDG_STATE_HOME", home_relative=(".local", "state"), owner=owner)


def artifact_cache_dir(owner: str | None = None) -> Path:
    """``$XDG_CACHE_HOME/hammunition/artifacts`` — verified downloads live here.

    A *cache* rather than state: every file in it is content-addressed by its
    verified digest and can be deleted at any time, costing only a re-download.
    Nothing here is a record of what was done — that is the transaction log's
    job, and conflating the two would put something un-deletable in a directory
    users and cleaners treat as disposable.
    """
    return owner_aware_dir(xdg_var="XDG_CACHE_HOME", home_relative=(".cache",), owner=owner) / (
        "artifacts"
    )
