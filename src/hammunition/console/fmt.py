# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later
"""Text from outside (an engine message, a log line, a unit summary) is data, not
terminal commands: clean() removes every escape sequence and control character so
nothing embedded in it reaches the terminal as a sequence."""

from __future__ import annotations

import re

# Whole sequences first, so a stripped ESC does not leave "[31m" behind as text.
_STRING = (
    r"(?:\x1b[\]PX^_]|[\x90\x98\x9d\x9e\x9f]).*?(?:\x07|\x1b\\|\x9c|\Z)"  # OSC, DCS, SOS, PM, APC
)
_CSI = r"(?:\x1b\[|\x9b)[0-?]*[ -/]*[@-~]?"
_ESCAPE = r"\x1b[ -/]*[0-~]?"  # two-byte and nF escapes, and a lone trailing ESC
_SEQUENCE = re.compile(f"{_STRING}|{_CSI}|{_ESCAPE}", re.DOTALL)
_CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f-\x9f]")


def clean(text: object) -> str:
    stripped = _SEQUENCE.sub("", str(text).replace("\t", "    "))
    return _CONTROL.sub("", stripped)


def human_size(n: int) -> str:
    value = float(n)
    for unit in ("B", "KiB", "MiB", "GiB"):
        if value < 1024 or unit == "GiB":
            return f"{int(value)} B" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    raise AssertionError("unreachable")


def mask(value: str | None) -> str:
    return "not set" if value is None else "********"


def first_line(text: str, limit: int = 120) -> str:
    line = text.strip().splitlines()[0] if text.strip() else ""
    return clean(line)[:limit]
