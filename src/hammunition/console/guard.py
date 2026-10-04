# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later
"""The consent guard: the one module that may name the engine's assume-yes flag
and its scripted-consent variables, and only to refuse them.

D-021: a gate a convenience flag or an exported variable walks through is not a
gate. The console therefore (1) refuses any argv carrying the flag, (2) strips
every scripted-consent variable from the environment of every child, and (3)
only ever runs the few commands listed here. Lines naming a forbidden token end
with the tag below; tests/test_consent_guard.py fails on any other mention in
the package.
"""

from __future__ import annotations

import os
import re
import shlex
from collections.abc import Mapping, Sequence

from hammunition.console.launch import engine_argv

CONSENT_PREFIX = "HAMMUNITION_ACCEPT_"  # consent-guard
CONSENT_SUFFIX = "_CONSENT"  # consent-guard
FORBIDDEN_ARGS = frozenset({"--yes", "-y"})  # consent-guard
# apt's own assume-yes, which the engine's `update` report prints in its upgrade
# command. The console drops it, so apt asks the operator in the pane.
_APT_REPORT_PREFIX = [
    "sudo",
    "env",
    "DEBIAN_FRONTEND=noninteractive",
    "apt-get",
    "install",
    "--yes",  # consent-guard
    "--only-upgrade",
    "--no-remove",
    "--",
]
_APT_RUN_PREFIX = ["sudo", "apt-get", "install", "--only-upgrade", "--no-remove", "--"]
_APT_PACKAGE = re.compile(r"^[a-z0-9][a-z0-9+.:_-]*$")
# The engine verbs the console runs in a pane; everything else is refused.
WRITE_VERBS: frozenset[tuple[str, ...]] = frozenset(
    {
        ("install",),
        ("uninstall",),
        ("station", "set"),
        ("hardware", "apply"),
        ("self-update",),
    }
)


class Refused(Exception):
    """A command or read the console will not run."""


def is_consent_variable(name: str) -> bool:
    return name.startswith(CONSENT_PREFIX) or name.endswith(CONSENT_SUFFIX)


def scrubbed_environ(environ: Mapping[str, str]) -> dict[str, str]:
    """A copy of the environment with every scripted-consent variable removed."""
    return {k: v for k, v in environ.items() if not is_consent_variable(k)}


def _forbidden(word: str) -> bool:
    return word in FORBIDDEN_ARGS or word.startswith("--yes=")  # consent-guard


def assert_clean_read(words: Sequence[str]) -> None:
    for word in words:
        if _forbidden(word):
            raise Refused(f"the console never passes {word!r}; a read must not carry it")


def checked_argv(argv: Sequence[str]) -> list[str]:
    """The argv to run in a pane, or Refused. Never contains the assume-yes flag."""
    out = list(argv)
    if not out:
        raise Refused("empty command")
    for word in out:
        if _forbidden(word):
            raise Refused(
                f"the console never passes {word!r}: a consent gate is answered by a person, "
                "typing into the real prompt (D-021)"
            )
    head = os.path.basename(out[0])
    prefix = engine_argv()
    # This installation's engine (`<python> -m hammunition`), or a `hammunition` on PATH.
    skip = len(prefix) if out[: len(prefix)] == prefix else 1 if head == "hammunition" else 0
    if skip:
        rest = out[skip:]
        verb = next(
            (v for v in sorted(WRITE_VERBS, key=len, reverse=True) if tuple(rest[: len(v)]) == v),
            None,
        )
        if verb is None:
            raise Refused(f"the console does not run `hammunition {' '.join(rest[:2])}` in a pane")
        return out
    packages = out[len(_APT_RUN_PREFIX) :]
    if (
        head == "sudo"
        and out[: len(_APT_RUN_PREFIX)] == _APT_RUN_PREFIX
        and packages
        and all(_APT_PACKAGE.match(p) for p in packages)
    ):
        return out
    raise Refused(f"the console does not run {out[0]!r} in a pane")


def apt_upgrade_argv(command: str | None) -> list[str] | None:
    """The pane argv for the engine's apt upgrade command, or None when it is not exactly that shape.

    The report prints `sudo env DEBIAN_FRONTEND=noninteractive apt-get install
    <apt's assume-yes> --only-upgrade --no-remove -- PKG...`. The console runs the same
    command with the frontend left interactive and without apt's assume-yes, so apt
    shows what it will change and asks.
    """
    if not command:
        return None
    try:
        words = shlex.split(command)
    except ValueError:
        return None
    n = len(_APT_REPORT_PREFIX)
    packages = words[n:]
    if words[:n] != _APT_REPORT_PREFIX or not packages:
        return None
    if not all(_APT_PACKAGE.match(p) for p in packages):
        return None
    return [*_APT_RUN_PREFIX, *packages]
