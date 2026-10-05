# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later
"""Secrets entered for this session only (issue #321, D-081).

A value lives in this object, in this process's memory, and is handed to the
engine subprocesses the console starts (a read, or a pane) through their
environment and nowhere else: never a file, never argv, never a log, never
this process's own `os.environ`. `clear()` runs when the console exits.
"""

from __future__ import annotations

import re
from collections.abc import Mapping

from hammunition.console import guard

_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class SessionRefused(ValueError):
    """The name or the value cannot be a session secret; the message never carries the value."""


class SessionSecrets:
    def __init__(self) -> None:
        self._values: dict[str, str] = {}

    def set(self, name: str, value: str) -> None:
        if not _NAME.match(name) or guard.is_consent_variable(name):
            raise SessionRefused(f"{name!r} is not a name the console will set")
        if not value or any(ord(c) < 32 or ord(c) == 127 for c in value):
            raise SessionRefused("a secret is one non-empty line with no control characters")
        self._values[name] = value

    def forget(self, name: str) -> None:
        self._values.pop(name, None)

    def clear(self) -> None:
        self._values.clear()

    def names(self) -> frozenset[str]:
        return frozenset(self._values)

    def overlay(self, environ: Mapping[str, str]) -> dict[str, str]:
        """*environ* with the session's values added: the environment of one child."""
        return {**environ, **self._values}

    def __repr__(self) -> str:  # never the values, even in a traceback or a debugger
        return f"SessionSecrets({sorted(self._values)})"
