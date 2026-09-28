# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""Stand-ins for the converters' programs, on a PATH the test controls.

Each fake is a small shell script that appends its argv and working
directory to ``calls.log`` beside it, then does what its body says. The
converters run the real subprocess path -- ``env -C <dir> <program>`` -- so
the argv, the working directory and the effect check are all exercised
without mkgmap, planetsplitter or GDAL on the machine.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest


def install_fakes(monkeypatch: pytest.MonkeyPatch, bin_dir: Path, tools: dict[str, str]) -> Path:
    """Write each ``name: body`` in *tools* as an executable in *bin_dir* and
    put *bin_dir* first on PATH. Returns the call log's path."""
    bin_dir.mkdir(parents=True, exist_ok=True)
    log = bin_dir / "calls.log"
    for name, body in tools.items():
        script = bin_dir / name
        script.write_text(
            f'#!/bin/sh\nprintf "%s\\t%s\\n" "$(pwd)" "{name} $*" >> "{log}"\n{body}\n'
        )
        script.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}")
    return log


def calls(log: Path) -> list[tuple[str, str]]:
    """(working directory, "program args...") for every fake run, in order."""
    out: list[tuple[str, str]] = []
    if log.exists():
        for line in log.read_text().splitlines():
            where, command = line.split("\t", 1)
            out.append((where, command))
    return out


def arg(argv: str, flag: str) -> str:
    """The value of ``--flag=value`` in a logged command line."""
    for word in argv.split():
        if word.startswith(f"{flag}="):
            return word.split("=", 1)[1]
    raise AssertionError(f"{flag} not in {argv!r}")
