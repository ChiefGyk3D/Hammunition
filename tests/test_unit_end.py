# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later
"""Completion records keep finished units resumable after a failed install."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from hammunition.backends import BackendError, RecordingRunner  # noqa: E402
from hammunition.backends.base import Action  # noqa: E402
from hammunition.distro import Target  # noqa: E402
from hammunition.execute import StepOwners, execute  # noqa: E402
from hammunition.manifest.schema import PackageManifest  # noqa: E402
from hammunition.plan import InstallPlan, PlannedPackage  # noqa: E402
from hammunition.state.log import TransactionLog  # noqa: E402

TARGET = Target(distro="debian", version="13", arch="x86_64")


def _manifest(name: str) -> PackageManifest:
    return PackageManifest.model_validate(
        {
            "name": name,
            "version": "1.0",
            "summary": "Fixture",
            "categories": ["navigation-maps"],
            "install": [{"install": {"method": "apt", "packages": [name]}}],
            "update": {"probe": {"method": "none"}},
            "documentation": {
                "what_it_does": "A unit used only to test completion recording.",
                "why_you_want_it": "To exercise completion recording.",
                "upstream_url": "https://example.invalid/",
            },
        }
    )


def _plan(*names: str) -> InstallPlan:
    return InstallPlan(
        target=TARGET,
        packages=tuple(
            PlannedPackage(manifest=manifest, block=manifest.install[0], apt_packages=(manifest.name,))
            for manifest in map(_manifest, names)
        ),
    )


def _events(log: TransactionLog) -> list[dict[str, Any]]:
    return list(log.read())


def test_completed_unit_is_recorded_before_a_later_failure(tmp_path: Path) -> None:
    log = TransactionLog(tmp_path / "transactions.jsonl")
    owners = StepOwners()
    first = Action(kind="convert", description="first", detail="first", perform=lambda: "ok")
    second = Action(
        kind="convert",
        description="second",
        detail="second",
        perform=lambda: (_ for _ in ()).throw(BackendError("failed")),
    )
    owners.own(first, "first")
    owners.own(second, "second")

    report = execute([first, second], RecordingRunner(), log=log, plan=_plan("first", "second"), owners=owners)

    assert not report.ok
    events = _events(log)
    assert [entry["unit"] for entry in events if entry["event"] == "unit_end"] == ["first"]
    assert events[-1]["event"] == "transaction_failed"


def test_a_successful_run_records_completion_after_effect_verification(tmp_path: Path) -> None:
    from test_cli import _FakeProber

    log = TransactionLog(tmp_path / "transactions.jsonl")
    owners = StepOwners()
    step = Action(kind="convert", description="unit", detail="unit", perform=lambda: "ok")
    owners.own(step, "unit")
    plan = _plan("unit")

    report = execute(
        [step],
        RecordingRunner(),
        log=log,
        plan=plan,
        prober=_FakeProber({}),
        owners=owners,
    )

    assert not report.verified
    assert not any(entry["event"] == "unit_end" for entry in _events(log))


def test_the_last_unit_end_follows_the_successful_verification(tmp_path: Path) -> None:
    log = TransactionLog(tmp_path / "transactions.jsonl")
    owners = StepOwners()
    step = Action(kind="convert", description="unit", detail="unit", perform=lambda: "ok")
    owners.own(step, "unit")

    report = execute(
        [step],
        RecordingRunner(),
        log=log,
        plan=_plan("unit"),
        owners=owners,
    )

    assert report.ok
    events = _events(log)
    assert [entry["event"] for entry in events][-2:] == ["unit_end", "transaction_end"]
