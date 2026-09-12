# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later
"""A build already installed at its pin is already installed. D-051.

Field laptop, 2026-09-12: the full-catalog install failed twice after its
builds (paracon's EACCES, then a removed worktree), and each resume rebuilt
every source unit -- 21 builds, twice -- because the engine knew "already
installed" only for apt packages and, since #67, vendor .debs. The Parrot VM
page had queued this as engine work on 2026-08-29.

The rule mirrors #67: the *effect* must be present (every declared binary at
<prefix>/bin/<install_as>, the tree marker where a tree is installed) AND the
transaction log must attribute it to this engine at the manifest's current
pin -- a verify-pin or extract action for exactly this build directory, whose
path encodes the pin, followed by a verified transaction end that confirmed
this unit's checks. Either half alone is a guess.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from hammunition.backends import GitBackend, RecordingRunner  # noqa: E402
from hammunition.distro import Target  # noqa: E402
from hammunition.execute import already_built  # noqa: E402
from hammunition.manifest.schema import GitInstall, PackageManifest  # noqa: E402
from hammunition.plan import InstallPlan, PlannedPackage  # noqa: E402
from hammunition.state.log import TransactionLog  # noqa: E402

TARGET = Target(distro="debian", version="13", arch="x86_64")


def _git_manifest(ref: str = "v1.0") -> PackageManifest:
    return PackageManifest.model_validate(
        {
            "name": "thing",
            "version": "1.0",
            "summary": "Fixture",
            "categories": ["sdr"],
            "install": [
                {
                    "install": {
                        "method": "git",
                        "repo": "https://example.invalid/thing",
                        "ref": ref,
                        "build_system": "cmake",
                    }
                }
            ],
            "binaries": [{"produced": "thing", "install_as": "thing"}],
            "update": {"probe": {"method": "none"}},
            "documentation": {
                "what_it_does": "Stands in for a git build.",
                "why_you_want_it": "To prove a finished build is not redone.",
                "upstream_url": "https://example.invalid/",
            },
        }
    )


def _git_block(manifest: PackageManifest) -> GitInstall:
    block = manifest.install[0].install
    assert isinstance(block, GitInstall)
    return block


def _plan(manifest: PackageManifest) -> InstallPlan:
    return InstallPlan(
        target=TARGET,
        packages=(PlannedPackage(manifest=manifest, block=manifest.install[0], apt_packages=()),),
    )


def _log(tmp_path: Path, entries: list[dict[str, Any]]) -> TransactionLog:
    log = TransactionLog(path=tmp_path / "transactions.jsonl")
    for entry in entries:
        log.append(entry)
    return log


def _built_entries(src: Path, unit: str = "thing") -> list[dict[str, Any]]:
    return [
        {"event": "transaction_begin", "version": 2, "packages": [unit]},
        {
            "event": "action_end",
            "kind": "verify-pin",
            "detail": f"git rev-parse HEAD in {src} must be v1.0",
            "outcome": "tag v1.0 resolved to 0123abcd",
        },
        {
            "event": "transaction_end",
            "version": 2,
            "verified": True,
            "checks": [{"kind": "binary", "subject": f"{unit}:thing", "confirmed": True}],
        },
    ]


def _setup(tmp_path: Path, *, binary_present: bool = True) -> tuple[GitBackend, Path]:
    prefix = tmp_path / "prefix"
    if binary_present:
        (prefix / "bin").mkdir(parents=True)
        (prefix / "bin" / "thing").write_text("#!/bin/sh\n")
        (prefix / "bin" / "thing").chmod(0o755)
    git = GitBackend(runner=RecordingRunner(), build_root=tmp_path / "build", prefix=prefix, jobs=2)
    return git, prefix


def test_a_build_present_on_disk_and_attributed_at_its_pin_is_already_built(
    tmp_path: Path,
) -> None:
    m = _git_manifest()
    git, prefix = _setup(tmp_path)
    src = git.layout(m, _git_block(m)).src
    log = _log(tmp_path, _built_entries(src))
    assert already_built(_plan(m), log=log, prefix=prefix, git=git) == frozenset({"thing"})


def test_a_build_whose_binary_is_gone_is_not_already_built(tmp_path: Path) -> None:
    m = _git_manifest()
    git, prefix = _setup(tmp_path, binary_present=False)
    src = git.layout(m, _git_block(m)).src
    log = _log(tmp_path, _built_entries(src))
    assert already_built(_plan(m), log=log, prefix=prefix, git=git) == frozenset()


def test_a_build_whose_transaction_never_verified_is_not_already_built(tmp_path: Path) -> None:
    """The paracon run: the build steps completed and the transaction
    failed after them. Present on disk, never confirmed -- rebuild."""
    m = _git_manifest()
    git, prefix = _setup(tmp_path)
    src = git.layout(m, _git_block(m)).src
    entries = [*_built_entries(src)[:-1], {"event": "transaction_failed"}]
    log = _log(tmp_path, entries)
    assert already_built(_plan(m), log=log, prefix=prefix, git=git) == frozenset()


def test_a_build_at_a_previous_pin_is_not_already_built(tmp_path: Path) -> None:
    """The manifest moved to v1.1; the log attributes v1.0's build directory.
    The binary on disk is the old one -- rebuild."""
    old = _git_manifest("v1.0")
    git, prefix = _setup(tmp_path)
    old_src = git.layout(old, _git_block(old)).src
    log = _log(tmp_path, _built_entries(old_src))
    new = _git_manifest("v1.1")
    assert already_built(_plan(new), log=log, prefix=prefix, git=git) == frozenset()


def test_apt_and_deb_units_are_never_decided_here(tmp_path: Path) -> None:
    """apt has its own answer (already_installed) and a .deb has #67's."""
    apt_unit = PackageManifest.model_validate(
        {
            "name": "aptish",
            "version": "1",
            "summary": "Fixture",
            "categories": ["sdr"],
            "install": [{"install": {"method": "apt", "packages": ["aptish"]}}],
            "update": {"probe": {"method": "none"}},
            "documentation": {
                "what_it_does": "Stands in for an apt package.",
                "why_you_want_it": "To prove apt units are not decided here.",
                "upstream_url": "https://example.invalid/",
            },
        }
    )
    git, prefix = _setup(tmp_path)
    log = _log(tmp_path, [])
    assert already_built(_plan(apt_unit), log=log, prefix=prefix, git=git) == frozenset()


def test_without_a_log_nothing_is_already_built(tmp_path: Path) -> None:
    m = _git_manifest()
    git, prefix = _setup(tmp_path)
    assert already_built(_plan(m), log=None, prefix=prefix, git=git) == frozenset()


def test_the_executor_plans_no_build_steps_for_an_already_built_unit(tmp_path: Path) -> None:
    from hammunition.backends import AptBackend
    from hammunition.execute import commands_for

    m = _git_manifest()
    git, _ = _setup(tmp_path)
    steps = commands_for(
        _plan(m), AptBackend(RecordingRunner()), git=git, skip_builds=frozenset({"thing"})
    )
    assert steps == []
    assert commands_for(_plan(m), AptBackend(RecordingRunner()), git=git) != []


def test_the_plan_renders_an_already_built_unit_as_already_installed() -> None:
    from hammunition.cli.main import render_plan

    m = _git_manifest()
    text = "\n".join(render_plan(_plan(m), (), euid=1000, built=frozenset({"thing"})))
    assert "already installed" in text and "will build" not in text
