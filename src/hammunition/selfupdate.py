# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""Updating the engine itself: its own checkout, and what version it is.  #303, #311.

Two jobs that share one fact -- where the checkout is:

* :func:`version_pair` says what the checkout's ``pyproject.toml`` declares and
  what the venv's installed metadata says, because an editable install keeps
  answering with the version it was installed at until something re-runs it.
* :func:`plan` and :func:`execute` are ``hammunition self-update``: a fetch, a
  fast-forward, then ``./bootstrap.sh``, each printed before it runs.

The checkout is found from where this package was imported, and only when that
is a git work tree holding ``bootstrap.sh``. Nothing here touches apt, the
catalog's installs or the station.
"""

from __future__ import annotations

import os
import re
import subprocess
import tomllib
from dataclasses import dataclass
from importlib import metadata
from pathlib import Path

__all__ = [
    "PACKAGE_FILE",
    "Refused",
    "Resolved",
    "Step",
    "checkout_version",
    "find_checkout",
    "installed_version",
    "installed_version_in",
    "mismatch_detail",
    "preflight",
    "resolve",
    "steps",
    "version_line",
    "version_pair",
]

#: This file; tests point it at a scratch repository.
PACKAGE_FILE = Path(__file__).resolve()
SELF_UPDATE_ARGV = ["hammunition", "self-update"]
_TAG = re.compile(r"^v\d+(\.\d+)*")


class Refused(Exception):
    """A reason, in a plain sentence, the update will not run."""


@dataclass(frozen=True)
class Step:
    """One command the update runs, named before it runs."""

    description: str
    argv: tuple[str, ...]


@dataclass(frozen=True)
class Resolved:
    """What the fetch found: where HEAD is, where it would go."""

    target: str
    """The ref to fast-forward to: ``origin/main`` or a ``v*`` tag."""
    head: str
    arriving: tuple[str, ...]
    """``git log --oneline HEAD..target``, newest first."""
    up_to_date: bool


def find_checkout(start: Path | None = None) -> Path | None:
    """The checkout this package runs from, or None (a packaged install)."""
    here = (start or PACKAGE_FILE).resolve()
    if len(here.parents) < 3:
        return None
    root = here.parents[2]  # <root>/src/hammunition/<module>.py
    if (root / ".git").exists() and (root / "bootstrap.sh").is_file():
        return root
    return None


def checkout_version(root: Path) -> str | None:
    """The version ``pyproject.toml`` declares, or None when it cannot be read."""
    try:
        data = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return None
    version = data.get("project", {}).get("version")
    return version if isinstance(version, str) else None


def installed_version() -> str | None:
    """What the venv's metadata says, or None when not installed."""
    try:
        return metadata.version("hammunition")
    except metadata.PackageNotFoundError:
        return None


def installed_version_in(root: Path) -> str | None:
    """The metadata version as the checkout's own venv now reports it. bootstrap may
    have rebuilt that venv, so this asks its interpreter; without one, this process."""
    python = root / ".venv" / "bin" / "python"
    if python.is_file():
        result = subprocess.run(
            [
                str(python),
                "-c",
                "import importlib.metadata as m; print(m.version('hammunition'))",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        out = result.stdout.strip()
        return out if result.returncode == 0 and out else None
    return installed_version()


def version_pair() -> tuple[str | None, str | None]:
    """``(checkout, installed)``; the checkout is None outside one."""
    root = find_checkout()
    return (checkout_version(root) if root else None), installed_version()


def mismatch_detail(checkout: str, installed: str | None) -> str:
    return f"{checkout} (checkout), {installed or 'not installed'} (installed)"


def version_line() -> str:
    """What ``--version`` prints after the name."""
    checkout, installed = version_pair()
    if checkout is None:
        return installed or "0+uninstalled"
    if installed == checkout:
        return checkout
    return f"{mismatch_detail(checkout, installed)}; run `hammunition self-update`"


def _git(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0", "LC_ALL": "C"}
    return subprocess.run(
        ["git", "-C", str(root), *args], capture_output=True, text=True, env=env, check=False
    )


def preflight(root: Path, *, release: bool) -> None:
    """Refuse a tree the update must not touch, before anything is fetched."""
    status = _git(root, "status", "--porcelain")
    if status.returncode != 0:
        raise Refused(f"git could not read {root}: {status.stderr.strip() or 'unknown error'}.")
    if status.stdout.strip():
        raise Refused(
            f"{root} has uncommitted changes; commit, stash or discard them yourself, "
            "then run this again. Nothing was changed."
        )
    if release:
        return
    branch = _git(root, "symbolic-ref", "--short", "-q", "HEAD")
    name = branch.stdout.strip()
    if branch.returncode != 0 or not name:
        raise Refused(
            f"{root} is on a detached HEAD; check out main yourself, or use --release "
            "to fast-forward to the newest release tag."
        )
    if name != "main":
        raise Refused(
            f"{root} is on branch {name!r}, not main; check out main yourself, or use "
            "--release to fast-forward to the newest release tag."
        )


def steps(root: Path, *, release: bool, target: str | None = None) -> list[Step]:
    """The three steps, in order. *target* is the tag once --release has chosen it."""
    ref = target or ("the newest release tag" if release else "origin/main")
    merge_ref = target or ("<newest v* tag>" if release else "origin/main")
    return [
        Step("fetch the remote's history", ("git", "-C", str(root), "fetch", "origin")),
        Step(
            f"fast-forward to {ref} (never a merge commit, never a reset)",
            ("git", "-C", str(root), "merge", "--ff-only", merge_ref),
        ),
        Step(
            "re-run bootstrap: venv, editable install, link, then `hammunition doctor`",
            (str(root / "bootstrap.sh"),),
        ),
    ]


def fetch(root: Path) -> None:
    result = _git(root, "fetch", "origin")
    if result.returncode != 0:
        raise Refused(
            f"`git fetch origin` failed: {result.stderr.strip() or 'no output'}. "
            "Nothing was changed."
        )


def resolve(root: Path, *, release: bool) -> Resolved:
    """After the fetch: the target, what would arrive, or a refusal."""
    if release:
        tags = _git(root, "tag", "--merged", "origin/main", "--list", "v*", "--sort=-v:refname")
        listed = [t for t in tags.stdout.split() if _TAG.match(t)]
        if tags.returncode != 0 or not listed:
            raise Refused("no v* release tag is reachable from origin/main; nothing to update to.")
        target = listed[0]
    else:
        target = "origin/main"
        if _git(root, "rev-parse", "--verify", "-q", target).returncode != 0:
            raise Refused("origin/main does not exist after the fetch; nothing to update to.")
    head = _git(root, "rev-parse", "--short", "HEAD").stdout.strip()
    if _git(root, "merge-base", "--is-ancestor", target, "HEAD").returncode == 0:
        return Resolved(target, head, (), True)
    if _git(root, "merge-base", "--is-ancestor", "HEAD", target).returncode != 0:
        raise Refused(
            f"{root} has commits that {target} does not, so this is not a fast-forward. "
            "Nothing was changed; rebase or reset it yourself."
        )
    log = _git(root, "log", "--oneline", f"HEAD..{target}")
    return Resolved(target, head, tuple(log.stdout.splitlines()), False)
