# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later
"""A failed transaction keeps the units that finished. #272.

Field laptop, 2026-10-03: an eight-unit install failed at the last unit's
first step and the rerun's plan rebuilt CoMaps (a 2.3 GB fetch and a
15-minute build) although every one of its steps had succeeded. The log
recorded a unit's steps but never that the unit was done, and the only
attribution of a build waited for a verified ``transaction_end`` that a
failed run never writes.

``unit_end`` is written inside the transaction when a unit's last step
finishes. The plan still verifies the effect on disk before it believes it.
"""

from __future__ import annotations

import sys
from dataclasses import replace
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from hammunition.backends import AptBackend, BackendError, GitBackend, RecordingRunner  # noqa: E402
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
from hammunition.interface.status import _last_outcomes, installed_units  # noqa: E402
from hammunition.manifest.schema import GitInstall, PackageManifest  # noqa: E402
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
            "categories": ["sdr"],
            "install": [
                {
                    "install": {
                        "method": "git",
                        "repo": f"https://example.invalid/{name}",
                        "ref": "v1.0",
                        "build_system": "cmake",
                    }
                }
            ],
            "binaries": [{"produced": name, "install_as": name}],
            "update": {"probe": {"method": "none"}},
            "documentation": {
                "what_it_does": "Stands in for a git build.",
                "why_you_want_it": "To prove a finished unit is not redone.",
                "upstream_url": "https://example.invalid/",
            },
        }
    )


NAMES = ["u1", "u2", "u3", "u4"]


def _plan(names: list[str]) -> InstallPlan:
    packages = []
    for name in names:
        m = _manifest(name)
        packages.append(PlannedPackage(manifest=m, block=m.install[0], apt_packages=()))
    return InstallPlan(target=TARGET, packages=tuple(packages))


def _apt_manifest(name: str) -> PackageManifest:
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


def _apt_plan(*names: str) -> InstallPlan:
    return InstallPlan(
        target=TARGET,
        packages=tuple(
            PlannedPackage(
                manifest=manifest, block=manifest.install[0], apt_packages=(manifest.name,)
            )
            for manifest in map(_apt_manifest, names)
        ),
    )


def _map_plan() -> InstallPlan:
    return InstallPlan(
        target=TARGET,
        packages=tuple(
            PlannedPackage(manifest=manifest, block=manifest.install[0], apt_packages=())
            for manifest in (regions_manifest(), navit_manifest())
        ),
    )


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


def _git(tmp_path: Path) -> tuple[GitBackend, Path]:
    prefix = tmp_path / "prefix"
    (prefix / "bin").mkdir(parents=True, exist_ok=True)
    git = GitBackend(runner=RecordingRunner(), build_root=tmp_path / "build", prefix=prefix, jobs=2)
    return git, prefix


def _place(prefix: Path, name: str) -> None:
    path = prefix / "bin" / name
    path.write_text("#!/bin/sh\n")
    path.chmod(0o755)


def _steps_by_unit(failing: str | None, ran: list[str]) -> tuple[list[Action], StepOwners]:
    """Two steps per unit, in plan order; *failing*'s second step raises."""
    steps: list[Action] = []
    owners = StepOwners()
    for name in NAMES:
        for n in (1, 2):

            def perform(name: str = name, n: int = n) -> str:
                if name == failing and n == 2:
                    raise BackendError("boom")
                ran.append(f"{name}.{n}")
                return "ok"

            step = Action(kind="step", description=name, detail=f"{name} step {n}", perform=perform)
            steps.append(step)
            owners.own(step, name)
    return steps, owners


def _events(log: TransactionLog) -> list[dict[str, Any]]:
    return list(log.read())


def _run_failing_on_3(tmp_path: Path) -> TransactionLog:
    log = TransactionLog(path=tmp_path / "transactions.jsonl")
    steps, owners = _steps_by_unit("u3", [])
    report = execute(steps, RecordingRunner(), log=log, plan=_plan(NAMES), owners=owners)
    assert not report.ok
    return log


def test_a_failure_on_unit_three_leaves_units_one_and_two_recorded(tmp_path: Path) -> None:
    log = _run_failing_on_3(tmp_path)
    ends = [e for e in _events(log) if e["event"] == "unit_end"]
    assert [e["unit"] for e in ends] == ["u1", "u2"]
    assert all(e["ok"] is True for e in ends)
    begin = next(e for e in _events(log) if e["event"] == "transaction_begin")
    assert all(e["run"] == begin["timestamp"] for e in ends)
    assert _events(log)[-1]["event"] == "transaction_failed"


def test_finished_units_are_recorded_before_the_transaction_failure(tmp_path: Path) -> None:
    log = _run_failing_on_3(tmp_path)
    kinds = [
        (e["event"], e.get("unit") or e.get("detail"))
        for e in _events(log)
        if e["event"] in ("unit_end", "action_end")
    ]
    assert kinds.index(("unit_end", "u1")) > kinds.index(("action_end", "u1 step 2"))
    events = _events(log)
    assert next(i for i, event in enumerate(events) if event["event"] == "unit_end") < next(
        i for i, event in enumerate(events) if event["event"] == "transaction_failed"
    )


def test_status_reads_completed_units_as_installed_and_names_the_failed_run(
    tmp_path: Path,
) -> None:
    entries = _events(_run_failing_on_3(tmp_path))
    outcomes = _last_outcomes(entries)
    assert outcomes["u1"][1] == "completed" and outcomes["u2"][1] == "completed"
    assert outcomes["u3"][1] == "failed" and outcomes["u4"][1] == "failed"
    assert installed_units(entries) == frozenset({"u1", "u2"})
    when = outcomes["u1"][0]
    assert when == next(e for e in entries if e["event"] == "transaction_begin")["timestamp"]


def test_a_killed_run_keeps_its_finished_units_and_the_partial_one_stays_interrupted() -> None:
    entries: list[dict[str, Any]] = [
        {"event": "transaction_begin", "timestamp": "T", "packages": ["a", "b"]},
        {"event": "unit_end", "unit": "a", "ok": True, "run": "T"},
        {"event": "action_begin", "kind": "step", "detail": "b step 1"},
    ]
    outcomes = _last_outcomes(entries)
    assert outcomes["a"][1] == "completed"
    assert outcomes["b"][1] == "interrupted"


def test_a_completed_run_is_unchanged_by_unit_end() -> None:
    entries: list[dict[str, Any]] = [
        {"event": "transaction_begin", "timestamp": "T", "packages": ["a"]},
        {"event": "unit_end", "unit": "a", "ok": True, "run": "T"},
        {"event": "transaction_end", "completed": 2},
    ]
    assert _last_outcomes(entries)["a"] == ("T", "completed")


def test_a_log_with_no_unit_end_reads_as_before() -> None:
    entries: list[dict[str, Any]] = [
        {"event": "transaction_begin", "timestamp": "T", "packages": ["a", "b"]},
        {"event": "transaction_failed", "completed": 1},
    ]
    assert _last_outcomes(entries) == {"a": ("T", "failed"), "b": ("T", "failed")}


def test_the_rerun_plans_only_the_failing_unit_and_those_after_it(tmp_path: Path) -> None:
    git, prefix = _git(tmp_path)
    plan = _plan(NAMES)
    # What the failed run really built: only the first two units' binaries.
    # Their unit_end names the build directory the plan computes.
    log = TransactionLog(path=tmp_path / "again.jsonl")
    for planned in plan.packages[:2]:
        _place(prefix, planned.name)
        src = git.layout(planned.manifest, planned.block.install).src  # type: ignore[arg-type]
        log.append({"event": "unit_end", "unit": planned.name, "ok": True, "pin": str(src)})
    built = already_built(plan, log=log, prefix=prefix, git=git)
    assert built == frozenset({"u1", "u2"})
    steps = commands_for(plan, AptBackend(RecordingRunner()), git=git, skip_builds=built)
    text = " ".join(s.display() if isinstance(s, Action) else " ".join(s.argv) for s in steps)
    assert "u3" in text and "u4" in text
    assert "/u1" not in text and "/u2" not in text


def _unit_end(pin: str, unit: str = "u1") -> list[dict[str, Any]]:
    return [
        {"event": "transaction_begin", "timestamp": "T", "packages": [unit]},
        {"event": "unit_end", "unit": unit, "ok": True, "pin": pin, "run": "T"},
        {"event": "transaction_failed", "completed": 3},
    ]


def _pinned_log(tmp_path: Path, git: GitBackend, ref: str = "v1.0") -> TransactionLog:
    m = _manifest("u1")
    block = m.install[0].install
    assert isinstance(block, GitInstall)
    log = TransactionLog(path=tmp_path / "t.jsonl")
    for entry in _unit_end(str(git.layout(m, block).src)):
        log.append(entry)
    return log


def test_a_completed_build_whose_tree_marker_or_binary_is_missing_is_planned_again(
    tmp_path: Path,
) -> None:
    git, prefix = _git(tmp_path)
    log = _pinned_log(tmp_path, git)  # recorded, but u1 is not on disk
    assert already_built(_plan(["u1"]), log=log, prefix=prefix, git=git) == frozenset()
    _place(prefix, "u1")
    assert already_built(_plan(["u1"]), log=log, prefix=prefix, git=git) == frozenset({"u1"})


def test_a_unit_end_at_another_pin_is_not_trusted(tmp_path: Path) -> None:
    git, prefix = _git(tmp_path)
    _place(prefix, "u1")
    log = TransactionLog(path=tmp_path / "t.jsonl")
    for entry in _unit_end("/somewhere/else/u1-old-pin"):
        log.append(entry)
    assert already_built(_plan(["u1"]), log=log, prefix=prefix, git=git) == frozenset()


def test_an_uninstall_after_the_unit_end_voids_it(tmp_path: Path) -> None:
    git, prefix = _git(tmp_path)
    _place(prefix, "u1")
    log = _pinned_log(tmp_path, git)
    log.append({"event": "uninstall_begin", "packages": ["u1"]})
    log.append({"event": "uninstall_end"})
    assert already_built(_plan(["u1"]), log=log, prefix=prefix, git=git) == frozenset()


def test_the_unit_end_survives_rotation(tmp_path: Path) -> None:
    git, prefix = _git(tmp_path)
    _place(prefix, "u1")
    log = _pinned_log(tmp_path, git)
    for i in range(3):
        log.append({"event": "transaction_begin", "timestamp": f"L{i}", "packages": ["zz"]})
        log.append({"event": "transaction_end"})
    assert log.rotate(threshold=0, keep=2) is not None
    assert log.archives(), "the first transaction moved into an archive"
    assert any(e["event"] == "unit_end" for e in TransactionLog(path=log.path).read())
    assert already_built(_plan(["u1"]), log=log, prefix=prefix, git=git) == frozenset({"u1"})


def test_commands_for_attributes_each_unit_its_own_steps(tmp_path: Path) -> None:
    git, _ = _git(tmp_path)
    owners = StepOwners()
    steps = commands_for(_plan(["u1", "u2"]), AptBackend(RecordingRunner()), git=git, owners=owners)
    owned = {name: [s for s in steps if name in owners.units_of(s)] for name in ("u1", "u2")}
    assert owned["u1"] and owned["u2"]
    assert not set(map(id, owned["u1"])) & set(map(id, owned["u2"]))
    assert "u1" in owners.pins and "u2" in owners.pins


def test_a_successful_run_records_unit_end_only_after_effect_verification(
    tmp_path: Path,
) -> None:
    from test_cli import _FakeProber, _installed

    log = TransactionLog(path=tmp_path / "transactions.jsonl")
    owners = StepOwners()
    step = Action(kind="convert", description="unit", detail="unit", perform=lambda: "ok")
    owners.own(step, "unit")
    report = execute(
        [step],
        RecordingRunner(),
        log=log,
        plan=_apt_plan("unit"),
        prober=_FakeProber({"unit": _installed("unit")}),
        owners=owners,
    )

    assert report.ok and report.verified
    events = _events(log)
    assert [entry["event"] for entry in events][-2:] == ["unit_end", "transaction_end"]
    assert events[-1]["verified"] is True


def test_an_unverified_success_does_not_claim_unit_completion(tmp_path: Path) -> None:
    from test_cli import _FakeProber

    log = TransactionLog(path=tmp_path / "transactions.jsonl")
    owners = StepOwners()
    step = Action(kind="convert", description="unit", detail="unit", perform=lambda: "ok")
    owners.own(step, "unit")
    report = execute(
        [step],
        RecordingRunner(),
        log=log,
        plan=_apt_plan("unit"),
        prober=_FakeProber({}),
        owners=owners,
    )
    assert not report.verified
    assert not any(entry["event"] == "unit_end" for entry in _events(log))


def test_a_derived_unit_resumes_only_for_matching_inputs_and_regions(tmp_path: Path) -> None:
    plan = _map_plan()
    regions, derived = _map_backends(tmp_path)
    source = data_root(tmp_path) / "osm-regions" / f"{VT.slug}.osm.pbf"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"p" * VT.size)
    source.with_name(source.name + ".source").write_text(f"{VT.snapshot}\n")
    _install_navit_output(tmp_path)

    states = completion_states(plan, regions=regions, derived=derived)
    log = TransactionLog(path=tmp_path / "transactions.jsonl")
    log.append({"event": "transaction_begin", "packages": ["osm-navit"]})
    log.append({"event": "unit_end", "unit": "osm-navit", "ok": True, "state": states["osm-navit"]})
    log.append({"event": "transaction_failed"})
    on_disk = completion_on_disk(plan, regions=regions, derived=derived)
    built = already_built(plan, log=log, prefix=tmp_path, states=states, on_disk=on_disk)
    assert "osm-navit" in built
    retry = commands_for(
        plan,
        AptBackend(RecordingRunner()),
        regions=regions,
        derived=derived,
        skip_builds=built,
    )
    assert not any(isinstance(step, Action) and step.kind in {"fetch", "convert"} for step in retry)

    changed_region = replace(VT, sha256="f" * 64)
    _, changed_derived = _map_backends(tmp_path, region=changed_region)
    changed_states = completion_states(plan, regions=regions, derived=changed_derived)
    assert changed_states["osm-navit"] != states["osm-navit"]
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
    assert other_states["osm-navit"] != states["osm-navit"]
    assert "osm-navit" not in already_built(
        plan,
        log=log,
        prefix=tmp_path,
        states=other_states,
        on_disk={"osm-navit": True},
    )


def test_missing_derived_output_prevents_resume(tmp_path: Path) -> None:
    plan = _map_plan()
    regions, derived = _map_backends(tmp_path)
    states = completion_states(plan, regions=regions, derived=derived)
    log = TransactionLog(path=tmp_path / "transactions.jsonl")
    log.append({"event": "unit_end", "unit": "osm-navit", "ok": True, "state": states["osm-navit"]})

    on_disk = completion_on_disk(plan, regions=regions, derived=derived)
    assert not on_disk["osm-navit"]
    assert "osm-navit" not in already_built(
        plan, log=log, prefix=tmp_path, states=states, on_disk=on_disk
    )


def test_map_ledger_completes_units_before_a_later_failure_and_retry_skips_them(
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
        plan, AptBackend(RecordingRunner()), regions=regions, derived=derived, owners=owners
    )
    later = Action(
        kind="convert",
        description="later unit",
        detail="later",
        perform=lambda: (_ for _ in ()).throw(BackendError("failed later")),
    )
    owners.own(later, "later-unit")
    log = TransactionLog(path=tmp_path / "transactions.jsonl")
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
    completed = {entry["unit"]: entry for entry in events if entry["event"] == "unit_end"}
    assert {"osm-regions", "osm-navit"} <= completed.keys()
    states = completion_states(plan, regions=regions, derived=derived)
    on_disk = completion_on_disk(plan, regions=regions, derived=derived)
    assert completed["osm-navit"]["state"] == states["osm-navit"]
    built = already_built(plan, log=log, prefix=tmp_path, states=states, on_disk=on_disk)
    assert {"osm-regions", "osm-navit"} <= built
    retry = commands_for(
        plan,
        AptBackend(RecordingRunner()),
        regions=regions,
        derived=derived,
        skip_builds=built,
    )
    assert not any(isinstance(step, Action) and step.kind in {"fetch", "convert"} for step in retry)
