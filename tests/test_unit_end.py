# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later
"""Completion records keep finished units resumable after a failed install."""

from __future__ import annotations

import sys
from dataclasses import replace
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from hammunition.backends import AptBackend, BackendError, RecordingRunner  # noqa: E402
from hammunition.backends.base import Action  # noqa: E402
from hammunition.backends.derived import CONVERTER, DerivedBackend  # noqa: E402
from hammunition.backends.regions import MapLedger, RegionsBackend, data_root  # noqa: E402
from hammunition.distro import Target  # noqa: E402
from hammunition.execute import (  # noqa: E402
    StepOwners,
    already_built,
    commands_for,
    completion_on_disk,
    completion_states,
    execute,
)
from hammunition.manifest.schema import PackageManifest  # noqa: E402
from hammunition.plan import InstallPlan, PlannedPackage  # noqa: E402
from hammunition.state.log import TransactionLog  # noqa: E402
from test_regions_backend import (  # noqa: E402
    FIXTURE,
    NH,
    VT,
    FakeFetcher,
    navit_manifest,
    regions_manifest,
)

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
            PlannedPackage(
                manifest=manifest, block=manifest.install[0], apt_packages=(manifest.name,)
            )
            for manifest in map(_manifest, names)
        ),
    )


def _events(log: TransactionLog) -> list[dict[str, Any]]:
    return list(log.read())


def _map_plan() -> InstallPlan:
    packages = []
    for manifest in (regions_manifest(), navit_manifest()):
        packages.append(
            PlannedPackage(manifest=manifest, block=manifest.install[0], apt_packages=())
        )
    return InstallPlan(target=TARGET, packages=tuple(packages))


def _map_backends(tmp_path: Path, *, region: Any = VT) -> tuple[RegionsBackend, DerivedBackend]:
    ledger = MapLedger()
    regions = RegionsBackend(
        fetcher=FakeFetcher(tmp_path / "cache"),
        prefix=tmp_path,
        files=[region],
        ledger=ledger,
    )
    derived = DerivedBackend(
        prefix=tmp_path,
        files=[region],
        staging=tmp_path / "staging",
        ledger=ledger,
        stock=FIXTURE,
    )
    return regions, derived


def _install_navit_output(tmp_path: Path, *, region: Any = VT) -> Path:
    output = data_root(tmp_path) / "osm-navit" / f"{region.slug}.bin"
    output.parent.mkdir(parents=True)
    output.write_bytes(b"map")
    output.with_name(output.name + ".source").write_text(
        f"{region.snapshot}\nconverter: {CONVERTER}\n"
    )
    return output


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

    report = execute(
        [first, second], RecordingRunner(), log=log, plan=_plan("first", "second"), owners=owners
    )

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
    from test_cli import _FakeProber, _installed

    log = TransactionLog(tmp_path / "transactions.jsonl")
    owners = StepOwners()
    step = Action(kind="convert", description="unit", detail="unit", perform=lambda: "ok")
    owners.own(step, "unit")

    report = execute(
        [step],
        RecordingRunner(),
        log=log,
        plan=_plan("unit"),
        prober=_FakeProber({"unit": _installed("unit")}),
        owners=owners,
    )

    assert report.ok
    events = _events(log)
    assert [entry["event"] for entry in events][-2:] == ["unit_end", "transaction_end"]
    assert events[-1]["verified"] is True


def test_a_failed_run_resumes_a_derived_unit_only_for_its_recorded_inputs_and_regions(
    tmp_path: Path,
) -> None:
    plan = _map_plan()
    regions, derived = _map_backends(tmp_path)
    _install_navit_output(tmp_path)
    state = completion_states(plan, regions=regions, derived=derived)["osm-navit"]
    log = TransactionLog(tmp_path / "transactions.jsonl")
    log.append({"event": "transaction_begin", "packages": ["osm-navit"]})
    log.append({"event": "unit_end", "unit": "osm-navit", "ok": True, "state": state})
    log.append({"event": "transaction_failed"})

    states = completion_states(plan, regions=regions, derived=derived)
    on_disk = completion_on_disk(plan, regions=regions, derived=derived)
    completed = already_built(plan, log=log, prefix=tmp_path, states=states, on_disk=on_disk)
    assert "osm-navit" in completed
    steps = commands_for(
        plan,
        AptBackend(RecordingRunner()),
        regions=regions,
        derived=derived,
        skip_builds=completed,
    )
    assert not any(isinstance(step, Action) and step.kind == "convert" for step in steps)

    changed_region = replace(VT, sha256="f" * 64)
    _, changed_derived = _map_backends(tmp_path, region=changed_region)
    changed_states = completion_states(plan, regions=regions, derived=changed_derived)
    assert changed_states["osm-navit"] != state
    assert "osm-navit" not in already_built(
        plan,
        log=log,
        prefix=tmp_path,
        states=changed_states,
        on_disk={"osm-navit": True},
    )

    changed_regions = replace(NH, snapshot=VT.snapshot)
    _, other_derived = _map_backends(tmp_path, region=changed_regions)
    other_states = completion_states(plan, regions=regions, derived=other_derived)
    assert other_states["osm-navit"] != state
    assert "osm-navit" not in already_built(
        plan,
        log=log,
        prefix=tmp_path,
        states=other_states,
        on_disk={"osm-navit": True},
    )


def test_a_derived_completion_is_not_resumed_when_its_output_is_missing(
    tmp_path: Path,
) -> None:
    plan = _map_plan()
    regions, derived = _map_backends(tmp_path)
    state = completion_states(plan, regions=regions, derived=derived)["osm-navit"]
    log = TransactionLog(tmp_path / "transactions.jsonl")
    log.append({"event": "unit_end", "unit": "osm-navit", "ok": True, "state": state})

    assert not completion_on_disk(plan, regions=regions, derived=derived)["osm-navit"]
    assert "osm-navit" not in already_built(
        plan,
        log=log,
        prefix=tmp_path,
        states={**completion_states(plan, regions=regions, derived=derived)},
        on_disk=completion_on_disk(plan, regions=regions, derived=derived),
    )


def test_the_region_ledger_completes_map_units_before_a_later_failure(
    tmp_path: Path,
) -> None:
    plan = _map_plan()
    regions, derived = _map_backends(tmp_path)
    source = data_root(tmp_path) / "osm-regions" / f"{VT.slug}.osm.pbf"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"p" * VT.size)
    source.with_name(source.name + ".source").write_text(f"{VT.snapshot}\n")
    _install_navit_output(tmp_path)

    owners = StepOwners()
    steps = commands_for(
        plan,
        AptBackend(RecordingRunner()),
        regions=regions,
        derived=derived,
        owners=owners,
    )
    later = Action(
        kind="convert",
        description="later unit",
        detail="later",
        perform=lambda: (_ for _ in ()).throw(BackendError("failed later")),
    )
    owners.own(later, "later-unit")
    log = TransactionLog(tmp_path / "transactions.jsonl")

    report = execute(
        [*steps, later],
        RecordingRunner(),
        log=log,
        plan=plan,
        prefix=tmp_path,
        owners=owners,
    )

    assert not report.ok
    events = _events(log)
    recorded = {entry["unit"]: entry for entry in events if entry["event"] == "unit_end"}
    assert {"osm-regions", "osm-navit"} <= recorded.keys(), (
        report.stderr,
        [entry["event"] for entry in events],
        [owners.units_of(step) for step in steps],
    )
    assert all(len(recorded[name]["state"]) == 64 for name in ("osm-regions", "osm-navit"))
    assert recorded["osm-navit"]["state"] == owners.states["osm-navit"]
    assert events[-1]["event"] == "transaction_failed"

    states = completion_states(plan, regions=regions, derived=derived)
    on_disk = completion_on_disk(plan, regions=regions, derived=derived)
    resumed = already_built(plan, log=log, prefix=tmp_path, states=states, on_disk=on_disk)
    assert {"osm-regions", "osm-navit"} <= resumed
    retry_steps = commands_for(
        plan,
        AptBackend(RecordingRunner()),
        regions=regions,
        derived=derived,
        skip_builds=resumed,
    )
    assert not any(
        isinstance(step, Action) and step.kind in {"fetch", "convert"} for step in retry_steps
    )
