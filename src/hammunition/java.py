# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""Which Java the machine has, read with ``java -version`` (D-037, amended).

``default-jre-headless`` is a metapackage: its own version says nothing about
the Java major it pulls in, and Ubuntu 22.04 and Pop!_OS 22.04 resolve it to
Java 11 while GraphHopper's classes are major 61 (Java 17). So a unit that
needs a floor is checked against what ``java`` itself reports, once per plan.

The probe is lazy and cached: a plan with no unit that declares
``requires_java`` never runs ``java``, and one that does runs it once.
Nothing here fetches or installs anything; the plan names the archive
package that would provide a newer Java and stops there.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Final

#: Where Debian-family systems put the alternatives-managed JRE when PATH has
#: none (a minimal PATH under sudo, a container).
DEFAULT_JAVA: Final = "/usr/lib/jvm/default-java/bin/java"

#: The archive's concrete JRE packages the plan asks apt about so a refusal
#: can name one. Newest last; the smallest that meets the floor is named.
JRE_CANDIDATES: Final = (11, 17, 21, 25)

_QUOTED = re.compile(r'version\s+"([^"]+)"')


def jre_package(major: int) -> str:
    return f"openjdk-{major}-jre-headless"


def parse_java_major(output: str) -> int | None:
    """The Java major from the first line of ``java -version``.

    ``openjdk version "17.0.12" 2024-07-16`` -> 17; ``"21"`` -> 21;
    ``"1.8.0_392"`` -> 8 (Java 8 and earlier said ``1.N``); an early-access
    ``"25-ea"`` -> 25. Anything unrecognised is ``None``, never a guess.
    """
    lines = output.strip().splitlines()
    if not lines:
        return None
    match = _QUOTED.search(lines[0])
    if match is None:
        return None
    parts = re.split(r"[._+-]", match.group(1))
    try:
        first = int(parts[0])
        if first == 1 and len(parts) > 1:
            return int(parts[1])
        return first
    except ValueError:
        return None


Runner = Callable[[list[str]], str]


def _run_java(argv: list[str]) -> str:
    # `java -version` writes to stderr. A bounded wait: a broken wrapper must
    # not hang a plan.
    proc = subprocess.run(argv, capture_output=True, text=True, timeout=30, check=False)
    return proc.stderr or proc.stdout


@dataclass
class JavaProbe:
    """The machine's Java, measured once. ``major`` is ``None`` when there is
    no ``java`` or its output is not a version line, and ``reason`` says which."""

    path_lookup: Callable[[str], str | None] = shutil.which
    default_path: str = DEFAULT_JAVA
    run: Runner = _run_java
    _measured: bool = field(default=False, init=False, repr=False)
    _major: int | None = field(default=None, init=False, repr=False)
    _line: str = field(default="", init=False, repr=False)
    _reason: str = field(default="no java was found on PATH or at " + DEFAULT_JAVA, init=False)

    @classmethod
    def detect(cls) -> JavaProbe:
        return cls()

    def _measure(self) -> None:
        if self._measured:
            return
        self._measured = True
        exe = self.path_lookup("java")
        if exe is None:
            import os

            if os.access(self.default_path, os.X_OK):
                exe = self.default_path
        if exe is None:
            self._reason = f"no java was found on PATH or at {self.default_path}"
            return
        try:
            out = self.run([exe, "-version"])
        except (OSError, subprocess.SubprocessError) as exc:
            self._reason = f"`{exe} -version` failed: {exc}"
            return
        self._line = out.strip().splitlines()[0] if out.strip() else ""
        self._major = parse_java_major(out)
        if self._major is None:
            self._reason = f"`{exe} -version` printed no version line ({self._line!r})"

    @property
    def major(self) -> int | None:
        self._measure()
        return self._major

    @property
    def version_line(self) -> str:
        self._measure()
        return self._line

    @property
    def reason(self) -> str:
        self._measure()
        return self._reason
