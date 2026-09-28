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
import stat
from pathlib import Path

__all__ = [
    "APP",
    "OperatorDirError",
    "artifact_cache_dir",
    "build_root",
    "ensure_operator_dir",
    "operator_dir_problem",
    "owner_aware_dir",
    "state_dir",
]

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


def build_root(owner: str | None = None) -> Path:
    """``$XDG_CACHE_HOME/hammunition/build`` — where source trees are unpacked
    and compiled.

    A cache for the same reason the artifact store is: it is reproducible from
    the catalog plus a verified download, and deleting it costs only time. It is
    deliberately *not* under the artifact cache — that directory is
    content-addressed and every name in it is a digest, which is a property
    worth keeping true.
    """
    return owner_aware_dir(xdg_var="XDG_CACHE_HOME", home_relative=(".cache",), owner=owner) / (
        "build"
    )


def data_dir(owner: str | None = None) -> Path:
    """``$XDG_DATA_HOME/hammunition`` — installed per-user payloads live here.

    *Data*, not cache: a virtualenv the operator's launchers point into is not
    reproducible-for-free the way a build tree is — deleting it breaks
    installed software until a reinstall. That distinction is why venvs do not
    live under ``build_root``.
    """
    return owner_aware_dir(xdg_var="XDG_DATA_HOME", home_relative=(".local", "share"), owner=owner)


def venv_root(owner: str | None = None) -> Path:
    """``$XDG_DATA_HOME/hammunition/venvs`` — one virtualenv per manifest."""
    return data_dir(owner) / "venvs"


def node_root(owner: str | None = None) -> Path:
    """``$XDG_DATA_HOME/hammunition/node`` — one built Node.js tree per manifest.

    Per-user for the same reason venvs are, plus one of its own: a node
    application writes into its own directory (openhamclock creates ``.env``
    beside ``server.js`` on first start), which a tree under ``/opt`` would
    have to be world-writable to allow (D-037).
    """
    return data_dir(owner) / "node"


def user_bin_dir(owner: str | None = None) -> Path:
    """``~/.local/bin`` for the operator — where venv wrappers land.

    Debian-family shells put it on PATH when it exists. Deliberately not
    ``/usr/local/bin``: a per-user venv reached through a system-wide wrapper
    would break for every user but one, and writing it needs no root, which is
    the privilege rule (CLAUDE.md) doing its job.
    """
    if owner and os.geteuid() == 0:
        entry = None
        with contextlib.suppress(KeyError):
            entry = pwd.getpwnam(owner)
        if entry is not None and entry.pw_uid != 0:
            return Path(entry.pw_dir) / ".local" / "bin"
    return Path.home() / ".local" / "bin"


def applications_dir(owner: str | None = None) -> Path:
    """``~/.local/share/applications`` for the operator — desktop entries.

    Deliberately not hammunition-scoped: this is the freedesktop per-user
    applications directory, the one every DE already reads. Our files are
    recognisable anyway — ``hammunition-*.desktop``, each carrying
    ``X-Hammunition-Package``.
    """
    if owner and os.geteuid() == 0:
        entry = None
        with contextlib.suppress(KeyError):
            entry = pwd.getpwnam(owner)
        if entry is not None and entry.pw_uid != 0:
            return Path(entry.pw_dir) / ".local" / "share" / "applications"
    base = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(base) / "applications"


# ---------------------------------------------------------------------------
# Creating the operator's directories as root
# ---------------------------------------------------------------------------


class OperatorDirError(Exception):
    """A directory under the operator's home that root must not use or create through."""


_DIR_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC


def _operator_home(path: Path, owner: str | None) -> pwd.struct_passwd | None:
    """The operator whose home *path* lies under, when this process is root.

    Named by *owner* when the caller knows it; otherwise the account whose home
    contains *path* (the deepest, should homes nest). None when not root, or
    when *path* is under no other account's home -- root's own, or a system
    directory -- which is a plain mkdir.
    """
    if os.geteuid() != 0:
        return None
    if owner:
        with contextlib.suppress(KeyError):
            entry = pwd.getpwnam(owner)
            if entry.pw_uid != 0 and _under(path, Path(entry.pw_dir)):
                return entry
        return None
    best: pwd.struct_passwd | None = None
    for entry in pwd.getpwall():
        if entry.pw_uid == 0 or entry.pw_dir in ("", "/"):
            continue
        if _under(path, Path(entry.pw_dir)) and (
            best is None or len(entry.pw_dir) > len(best.pw_dir)
        ):
            best = entry
    return best


def _under(path: Path, home: Path) -> bool:
    return path != home and home in path.parents


def _refusal(where: Path, st: os.stat_result, entry: pwd.struct_passwd) -> str | None:
    if stat.S_ISLNK(st.st_mode):
        return (
            f"{where} is a symlink; root will not create or write through it on "
            f"{entry.pw_name}'s behalf. Remove it and run the install again."
        )
    if not stat.S_ISDIR(st.st_mode):
        return f"{where} is not a directory; move it aside and run the install again."
    if st.st_uid != entry.pw_uid:
        return (
            f"{where} is not owned by {entry.pw_name} (an earlier run under sudo can leave "
            f"it root-owned), so {entry.pw_name}'s own processes cannot write under it. "
            f"Fix: sudo chown -R {entry.pw_name}: {where}"
        )
    return None


def _walk(path: Path, entry: pwd.struct_passwd, *, create: bool) -> str | None:
    """Walk *path* from the operator's home by descriptor, never following a link.

    Each existing component must be a directory the operator owns; a missing
    one is created when *create* (0755, handed to the operator with fchown on
    the descriptor root just opened on it) and ends the check otherwise.
    Returns the first refusal, or None.
    """
    home = Path(entry.pw_dir)
    fd = os.open(home, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    try:
        where = home
        for part in path.relative_to(home).parts:
            where = where / part
            try:
                st = os.stat(part, dir_fd=fd, follow_symlinks=False)
            except FileNotFoundError:
                if not create:
                    return None
                os.mkdir(part, 0o755, dir_fd=fd)
                child = os.open(part, _DIR_FLAGS, dir_fd=fd)
                os.fchown(child, entry.pw_uid, entry.pw_gid)
            else:
                refusal = _refusal(where, st, entry)
                if refusal is not None:
                    return refusal
                child = os.open(part, _DIR_FLAGS, dir_fd=fd)
            os.close(fd)
            fd = child
        return None
    finally:
        os.close(fd)


def ensure_operator_dir(path: Path, owner: str | None = None) -> None:
    """``mkdir -p`` that leaves the operator's directories the operator's.

    As root on an operator's behalf, a directory under their home is created a
    component at a time through ``O_NOFOLLOW`` descriptors and each one root
    made is handed over with ``fchown``: a root-owned ``~/.cache/hammunition``
    left by a fetch under sudo made the operator's own later ``install -d``
    fail with EACCES. An existing component that is a symlink, not a
    directory, or not the operator's raises :class:`OperatorDirError` naming it
    and the fix. Anywhere else, and when not root, it is a plain mkdir.
    """
    entry = _operator_home(path, owner)
    if entry is None:
        path.mkdir(parents=True, exist_ok=True)
        return
    refusal = _walk(path, entry, create=True)
    if refusal is not None:
        raise OperatorDirError(refusal)


def operator_dir_problem(path: Path, owner: str | None = None) -> str | None:
    """Why the operator could not create or use *path*, read-only; None if nothing.

    The same checks as :func:`ensure_operator_dir` on the components that
    exist, creating nothing -- for a path the operator's own process will
    create, where root only looks first so a failure is named rather than a
    bare EACCES.
    """
    entry = _operator_home(path, owner)
    if entry is None:
        return None
    return _walk(path, entry, create=False)
