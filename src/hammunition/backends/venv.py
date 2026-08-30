# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""The venv backend — per-user Python installs, hash-pinned end to end.

The last backend the 1.0 measurement requires (D-014, re-measured 2026-08-30:
pipx and CPAN fell to zero users; venv kept three — not1mm, nanovna-saver,
and the radiosonde_auto_rx REVIVE that waits on it by design).

What AHRL does for these units is a generated bash script that builds a venv
in the operator's home and pip-installs an unpinned name from PyPI. Two
things change here, both of them this project's standing rules rather than
taste:

- **Everything is pinned and hashed.** The manifest carries the full
  dependency tree as requirements lines with ``--hash=sha256:`` pins, and pip
  runs with ``--require-hashes`` — the checksum rule for non-apt sources,
  applied to PyPI. The schema refuses an unhashed line before a plan exists.
- **Nothing needs root.** The venv lives in the operator's XDG data dir, the
  wrapper in ``~/.local/bin``, and every step runs unprivileged — the
  privilege rule with zero exceptions, because nothing here touches the
  system.

The venv is *data*, not cache: launchers point into it, so it lives under
``$XDG_DATA_HOME/hammunition/venvs/<name>`` rather than the build root.
Idempotency is the cheap kind for now: ``python3 -m venv`` over an existing
venv is a no-op, and a fully-hashed ``pip install`` over a satisfied venv
verifies and exits — the run is safe to repeat, though not yet free (the
same already-installed-at-pin gap the git backend records).
"""

from __future__ import annotations

import os
from functools import partial
from pathlib import Path

from hammunition.backends.base import Action, Command
from hammunition.manifest.schema import PackageManifest, VenvInstall

__all__ = ["VenvBackend"]


def write_requirements(path: Path, lines: list[str]) -> str:
    """Stage the manifest's pinned requirements as a file pip can read."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n")
    return f"wrote {len(lines)} pinned requirement line(s) to {path}"


def write_wrapper(path: Path, target: Path) -> str:
    """A two-line exec wrapper onto the operator's PATH.

    Generated rather than symlinked: a symlink into a venv makes some
    entry-point loaders resolve ``sys.prefix`` to the link's home and miss the
    venv's packages; ``exec`` of the venv's own script never does.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f'#!/bin/sh\nexec "{target}" "$@"\n')
    os.chmod(path, 0o755)
    return f"wrote {path} -> {target}"


class VenvBackend:
    """Plans venv installs. Steps only — the runner executes them."""

    def __init__(self, *, venv_root: Path, bin_dir: Path) -> None:
        self.venv_root = venv_root
        self.bin_dir = bin_dir

    def steps(self, manifest: PackageManifest, block: VenvInstall) -> list[Action | Command]:
        venv = self.venv_root / manifest.name
        requirements = self.venv_root / f"{manifest.name}.requirements.txt"
        pip = venv / "bin" / "pip"

        steps: list[Action | Command] = [
            Action(
                kind="requirements",
                description=f"Stage {manifest.name}'s pinned requirements",
                detail=f"{len(block.requirements)} hash-pinned line(s) -> {requirements}",
                perform=partial(write_requirements, requirements, list(block.requirements)),
            ),
            Command(
                argv=("python3", "-m", "venv", str(venv)),
                description=f"Create (or reuse) {manifest.name}'s virtualenv",
                requires_root=False,
            ),
            Command(
                argv=(
                    str(pip),
                    "install",
                    "--require-hashes",
                    "--no-input",
                    "--quiet",
                    "-r",
                    str(requirements),
                ),
                description=(
                    f"Install {manifest.name} into its venv — every wheel verified "
                    f"against the manifest's sha256 pins"
                ),
                requires_root=False,
                env=dict(block.env),
            ),
        ]
        for script in block.expose:
            wrapper = self.bin_dir / script
            target = venv / "bin" / script
            steps.append(
                Action(
                    kind="wrapper",
                    description=f"Put {script} on the operator's PATH",
                    detail=f"{wrapper} execs {target}",
                    perform=partial(write_wrapper, wrapper, target),
                )
            )
        return steps
