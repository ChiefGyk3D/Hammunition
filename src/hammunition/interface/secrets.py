# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""``secrets status`` as data.  D-081, D-059.

Where each secret the engine knows would come from, and never what it is: no
value, no prefix of one, no length. Doppler is not asked; the status says
whether the station names a project and a config and whether the CLI is on
PATH, which is what decides whether a command's own lookup could work.
"""

from __future__ import annotations

import os
import shutil
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import ClassVar

from hammunition import secrets as registry
from hammunition.interface.envelope import Strict, described
from hammunition.station import Station

__all__ = ["DopplerView", "SecretView", "SecretsDocument", "build_secrets", "render_secrets"]


@dataclass(frozen=True)
class DopplerView(Strict):
    """Whether Doppler could answer: names set in the station and the CLI present."""

    project: str | None = described("the station's Doppler project name; null when not set")
    config: str | None = described("the station's Doppler config name; null when not set")
    configured: bool = described("both names are set in the station")
    cli_on_path: bool = described("the `doppler` command is on PATH")


@dataclass(frozen=True)
class SecretView(Strict):
    """One secret: its state now, how it would be answered and how to provide it."""

    name: str = described("the environment variable and the Doppler secret name")
    purpose: str = described("what the secret is for, in a sentence")
    available: bool = described(
        "a source would answer: the variable is set, or Doppler is named and its CLI is present"
    )
    source: str = described(
        "`environment`, `doppler` (named and installed; not asked here) or `none`"
    )
    detail: str = described("one sentence on why `source` is what it is")
    unit: str | None = described("the catalog unit that must be installed to use it, if any")
    command: str = described("the first command the secret unlocks")
    get_url: str = described("where to get one")
    get_how: str = described("what to ask for there")
    doc: str = described("the repository page that explains it")
    ways: tuple[str, ...] = described("the exact ways to provide it, as commands to run")


@dataclass(frozen=True)
class SecretsDocument(Strict):
    """The secrets the engine knows and whether each is available now. Never a
    value, a prefix of one or its length."""

    KIND: ClassVar[str] = "secrets"

    doppler: DopplerView = described("the Doppler side of the answer")
    secrets: tuple[SecretView, ...] = described("one entry per secret in the engine's registry")


def _view(
    known: registry.KnownSecret, env_set: bool, station: Station | None, cli: bool
) -> SecretView:
    project = station.secrets_doppler_project if station else None
    config = station.secrets_doppler_config if station else None
    named = bool(project and config)
    if env_set:
        source, detail = "environment", f"{known.name} is set in this environment."
    elif named and cli:
        source = "doppler"
        detail = (
            f"{known.name} is not set; Doppler project {project}, config {config} is named and "
            "`doppler` is on PATH. Doppler is not asked here: the command that needs the secret asks."
        )
    elif named:
        source = "none"
        detail = f"{known.name} is not set, and Doppler is named in the station but `doppler` is not on PATH."
    else:
        source, detail = (
            "none",
            f"{known.name} is not set and the station names no Doppler project.",
        )
    return SecretView(
        name=known.name,
        purpose=known.purpose,
        available=source != "none",
        source=source,
        detail=detail,
        unit=known.unit,
        command=known.command,
        get_url=known.get_url,
        get_how=known.get_how,
        doc=known.doc,
        ways=(
            f"export {known.name}=...    (this shell only)",
            "hammunition station set --doppler-project PROJECT --doppler-config CONFIG",
        ),
    )


def build_secrets(
    *,
    env: Mapping[str, str] | None = None,
    station: Station | None,
    which: Callable[[str], str | None] | None = None,
) -> SecretsDocument:
    environ = os.environ if env is None else env
    find = which if which is not None else shutil.which
    cli = find("doppler") is not None
    project = station.secrets_doppler_project if station else None
    config = station.secrets_doppler_config if station else None
    return SecretsDocument(
        doppler=DopplerView(
            project=project, config=config, configured=bool(project and config), cli_on_path=cli
        ),
        secrets=tuple(_view(k, bool(environ.get(k.name)), station, cli) for k in registry.REGISTRY),
    )


def render_secrets(doc: SecretsDocument) -> list[str]:
    """``secrets status`` as the terminal shows it."""
    d = doc.doppler
    lines = [
        "Secrets: never printed; this says only where each would come from.",
        "",
        "Doppler: "
        + (f"project {d.project}, config {d.config}" if d.configured else "not configured")
        + ("; `doppler` on PATH" if d.cli_on_path else "; `doppler` not on PATH"),
        "",
    ]
    for s in doc.secrets:
        lines += [
            f"{s.name}: {'available' if s.available else 'not available'} (source: {s.source})",
            f"  {s.purpose}",
            f"  {s.detail}",
            f"  get one: {s.get_url} ({s.get_how})",
        ]
        if s.unit:
            lines.append(f"  needs the unit: hammunition install {s.unit}")
        lines.append(f"  first command: {s.command}")
        if not s.available:
            lines.append("  provide it:")
            lines += [f"    {w}" for w in s.ways]
        lines.append("")
    return lines[:-1]
