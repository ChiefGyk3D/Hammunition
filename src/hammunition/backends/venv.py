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
from hammunition.backends.source import SourceLayout, extract, tree_install_commands
from hammunition.fetch import Fetcher
from hammunition.manifest.schema import PackageManifest, RemoteArtifact, VenvInstall

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
    """Plans venv installs. Steps only — the runner executes them.

    ``fetcher``/``build_root``/``prefix`` exist for the payload half of the
    hybrid (source-build-gaps #9): a verified archive extracted and
    tree-installed beside the venv that runs it. A backend built without
    them refuses a payload manifest by name rather than planning half an
    install.
    """

    def __init__(
        self,
        *,
        venv_root: Path,
        bin_dir: Path,
        fetcher: Fetcher | None = None,
        build_root: Path | None = None,
        prefix: Path = Path("/usr/local"),
    ) -> None:
        self.venv_root = venv_root
        self.bin_dir = bin_dir
        self.fetcher = fetcher
        self.build_root = build_root
        self.prefix = prefix

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
        if block.payload is not None:
            steps.extend(self._payload_steps(manifest, block))
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

    def _payload_steps(
        self, manifest: PackageManifest, block: VenvInstall
    ) -> list[Action | Command]:
        from hammunition.backends.base import BackendError

        payload = block.payload
        assert payload is not None
        if self.fetcher is None or self.build_root is None:
            raise BackendError(
                f"{manifest.name} declares a venv payload and this backend was "
                f"built without a fetcher/build root. Skipping it would install "
                f"a venv that runs nothing."
            )
        layout = SourceLayout(root=self.build_root / f"{manifest.name}-{payload.sha256[:8]}")
        fetcher = self.fetcher
        steps: list[Action | Command] = [
            Action(
                kind="fetch",
                description=f"Download and verify {manifest.name}'s payload tree",
                detail=f"{payload.url} -> {fetcher.path_for(payload)} (sha256 verified)",
                perform=partial(_fetch_payload, fetcher, payload),
            ),
            Action(
                kind="extract",
                description=f"Unpack the {manifest.name} payload",
                detail=f"{fetcher.path_for(payload)} -> {layout.src}",
                perform=partial(_extract_payload, fetcher, payload, layout.src),
            ),
        ]
        if block.payload_build_script:
            # Run from the script's own directory: upstream build scripts
            # address their tree relative to themselves (auto_rx/build.sh
            # invokes `python3 -m autorx.version`, which only resolves from
            # auto_rx/ — measured on the first Debian run, 2026-08-30).
            script = Path(block.payload_build_script)
            steps.append(
                Command(
                    argv=("sh", script.name),
                    description=f"Run {manifest.name}'s payload build ({block.payload_build_script})",
                    cwd=layout.src / script.parent,
                )
            )
        steps.extend(
            tree_install_commands(name=manifest.name, source_tree=layout.src, prefix=self.prefix)
        )
        return steps


def _fetch_payload(fetcher: Fetcher, payload: RemoteArtifact) -> str:
    result = fetcher.fetch(payload)
    where = "cached" if result.from_cache else "downloaded"
    return f"{where} {result.path.name}, sha256 verified"


def _extract_payload(fetcher: Fetcher, payload: RemoteArtifact, dest: Path) -> str:
    return extract(fetcher.path_for(payload), dest)
