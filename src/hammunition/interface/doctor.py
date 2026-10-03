# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""``doctor`` as data.  D-059.

The checks themselves are :func:`hammunition.doctor.run_checks`, a pure
function; this is the document and the text, both read from its result.
Like the text, the document says whether a station is set, never its values.
"""

from __future__ import annotations

import shlex
from collections.abc import Sequence
from dataclasses import dataclass
from typing import ClassVar

from hammunition.doctor import Check, summarize
from hammunition.interface.envelope import Strict, described

__all__ = ["DoctorDocument", "build_doctor", "render_doctor"]

GLYPH = {"ok": "✓", "warn": "!", "fail": "✗", "info": "·"}


@dataclass(frozen=True)
class CheckView(Strict):
    """One thing looked at, its verdict, and how to fix it."""

    name: str = described("the check")
    status: str = described("`ok`, `info`, `warn` (limits what installs) or `fail` (blocking)")
    detail: str = described("what was found")
    fix: str | None = described("the one command or step that fixes it")
    fix_argv: list[str] | None = described(
        "argv for a single command fix; null when the fix is advice rather than a command"
    )


@dataclass(frozen=True)
class DoctorDocument(Strict):
    """The read-only health check: is this machine ready? Exit 1 when blocking."""

    KIND: ClassVar[str] = "doctor"

    checks: tuple[CheckView, ...] = described("in the order a person should read them")
    fails: int = described("blocking")
    warns: int = described("to look at")
    healthy: int = described("ok or info")


def build_doctor(checks: Sequence[Check]) -> DoctorDocument:
    fails, warns, healthy = summarize(list(checks))
    return DoctorDocument(
        checks=tuple(
            CheckView(
                name=c.name,
                status=c.status,
                detail=c.detail,
                fix=c.fix,
                fix_argv=c.fix_argv,
            )
            for c in checks
        ),
        fails=fails,
        warns=warns,
        healthy=healthy,
    )


def render_doctor(doc: DoctorDocument) -> list[str]:
    """``doctor`` as the terminal shows it."""
    lines = ["Hammunition health check", ""]
    for check in doc.checks:
        lines.append(f"  [{GLYPH[check.status]}] {check.name:14} {check.detail}")
        if check.fix_argv is not None:
            command = shlex.join(check.fix_argv)
            fix = check.fix or command
            formatted_fix = (
                fix.replace(command, "`" + command + "`", 1)
                if command in fix
                else f"`{command}` ({fix})"
            )
            lines.append(f"      → {formatted_fix}")
        elif check.fix and check.status in ("fail", "warn"):
            lines.append(f"      → {check.fix}")
    lines += ["", f"{doc.healthy} ok, {doc.warns} to look at, {doc.fails} blocking."]
    if doc.fails:
        lines.append("Fix the blocking items above before installing.")
    elif doc.warns:
        lines.append("The engine works; the items marked ! limit what you can install until fixed.")
    else:
        lines.append("Ready.")
    return lines
