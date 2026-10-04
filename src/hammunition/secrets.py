# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""Operator secrets for downloads that need a key.  D-081.

One helper, so every keyed fetch resolves a secret the same way and none of
them invents its own. The order is fixed:

1. the environment variable *name*, when set and not empty;
2. Doppler, when the station config names a project and a config
   (``station set --doppler-project P --doppler-config C``): the one
   command ``doppler secrets get NAME --plain --project P --config C``;
3. otherwise :class:`SecretUnavailable`, which says both ways.

A secret is never read from the repository, the station file, argv or a
log. The value is handed to the caller and to the run log's scrubber
(:meth:`hammunition.runlog.RunLog.add_scrub`) and is printed nowhere here.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from collections.abc import Mapping

from . import runlog
from .station import Station

__all__ = ["SecretUnavailable", "resolve_secret"]

#: An environment variable name: it becomes a Doppler secret name and an
#: argv element, so it can never look like an option.
_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class SecretUnavailable(Exception):
    """The secret could not be obtained; the message says how to supply it."""


def _first_line(text: str) -> str:
    for line in text.splitlines():
        if line.strip():
            return line.strip()
    return "no message"


def resolve_secret(name: str, *, env: Mapping[str, str], station: Station | None) -> str:
    """The secret called *name*: the environment first, then Doppler.

    Raises :class:`ValueError` for a *name* that is not an identifier (a
    programming error) and :class:`SecretUnavailable` when no source gives a
    value. The value is registered with the active run log's scrubber before
    it is returned."""
    if not _NAME.match(name):
        raise ValueError(f"{name!r} is not a secret name (letters, digits and _ only)")
    value = env.get(name, "")
    if value:
        return _registered(value)
    project = station.secrets_doppler_project if station else None
    config = station.secrets_doppler_config if station else None
    if not (project and config):
        raise SecretUnavailable(
            f"{name} is not set. Either `export {name}=...` for this shell, or keep it in "
            f"Doppler and tell Hammunition where: `hammunition station set "
            f"--doppler-project PROJECT --doppler-config CONFIG` (names only; never a token)."
        )
    if shutil.which("doppler", path=os.environ.get("PATH", os.defpath)) is None:
        raise SecretUnavailable(
            f"{name} is not set, and the station names a Doppler project, but `doppler` "
            f"is not on PATH. Install the Doppler CLI, or `export {name}=...` for this shell."
        )
    argv = ["doppler", "secrets", "get", name, "--plain", "--project", project, "--config", config]
    done = subprocess.run(argv, capture_output=True, text=True, check=False)
    if done.returncode != 0:
        # stderr's first line only, never stdout: stdout is where a secret goes.
        raise SecretUnavailable(
            f"`doppler secrets get {name}` failed (exit {done.returncode}): "
            f"{_first_line(done.stderr)}"
        )
    value = done.stdout.strip()
    if not value:
        raise SecretUnavailable(
            f"Doppler answered with an empty value for {name} (project {project}, config {config})."
        )
    return _registered(value)


def _registered(value: str) -> str:
    run = runlog.current()
    if run is not None:
        run.add_scrub([value])
    return value
