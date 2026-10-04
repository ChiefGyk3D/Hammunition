# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""``self-update --dry-run`` as data.  #303, D-059.

The plan for updating the engine's own checkout: the three steps, the commits
that would arrive, and the versions before. A real run is never driven through
JSON (the fast-forward and bootstrap are the terminal's to show).
"""

from __future__ import annotations

import shlex
from dataclasses import dataclass
from typing import ClassVar

from hammunition.interface.envelope import Strict, described

__all__ = ["SelfUpdateDocument", "StepView", "render_self_update"]


@dataclass(frozen=True)
class StepView(Strict):
    """One command the update would run."""

    description: str = described("what the step does, in words")
    argv: tuple[str, ...] = described("the command, argv form")


@dataclass(frozen=True)
class SelfUpdateDocument(Strict):
    """What `self-update --dry-run` would do to the engine's own checkout."""

    KIND: ClassVar[str] = "self-update"

    checkout: str = described("the git work tree the running engine was imported from")
    release: bool = described("whether `--release` chose the newest v* tag over origin/main")
    target: str = described("the ref the checkout would fast-forward to")
    up_to_date: bool = described(
        "the checkout already has the target; bootstrap still re-runs, which is what "
        "repairs a venv whose installed version lags"
    )
    checkout_version: str | None = described("the version `pyproject.toml` declares now")
    installed_version: str | None = described("the version the venv's metadata reports now")
    arriving: tuple[str, ...] = described(
        "`git log --oneline HEAD..<target>`, newest first, after the fetch; empty when up to date"
    )
    steps: tuple[StepView, ...] = described("the commands, in the order they run")
    dry_run: bool = described("always true: a real run is never driven through JSON")


def render_self_update(doc: SelfUpdateDocument) -> list[str]:
    lines = [
        f"Engine checkout: {doc.checkout}",
        f"Version now: {doc.checkout_version or '?'} (checkout), "
        f"{doc.installed_version or 'not installed'} (installed)",
        "",
        "Steps:",
    ]
    for number, step in enumerate(doc.steps, 1):
        lines.append(f"  {number}. {step.description}")
        lines.append(f"       $ {shlex.join(step.argv)}")
    lines.append("")
    if doc.up_to_date:
        lines.append(f"The checkout already has {doc.target}; only bootstrap would run.")
    else:
        lines.append(f"{len(doc.arriving)} commit(s) would arrive from {doc.target}:")
        lines += [f"  {entry}" for entry in doc.arriving]
    return lines
