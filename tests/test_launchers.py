# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""Launcher generation: endpoints resolved, workdirs honoured, menus fed."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from hammunition.launchers import desktop_entry, launcher_steps, wrapper_body
from hammunition.manifest.schema import PackageManifest


def manifest(**overrides: Any) -> PackageManifest:
    base: dict[str, Any] = {
        "name": "launchable",
        "version": "1.0",
        "summary": "Fixture with a launcher",
        "categories": ["sdr", "tracking"],
        "install": [{"install": {"method": "apt", "packages": ["launchable"]}}],
        "launchers": [{"name": "launchable", "exec": "launchable --serve"}],
        "update": {"probe": {"method": "none"}, "strategy": "manual"},
        "documentation": {
            "what_it_does": "Exists so launcher generation has a unit to plan.",
            "why_you_want_it": "You do not; the suite does.",
            "upstream_url": "https://example.invalid/",
        },
    }
    base.update(overrides)
    return PackageManifest.model_validate(base)


def test_endpoint_references_resolve_to_the_catalog_url() -> None:
    m = manifest(
        launchers=[{"name": "l", "exec": "prog --backend {endpoint:backend}"}],
        service_endpoints=[
            {
                "name": "backend",
                "default_url": "https://ohb.works",
                "description": "The repointable data backend for this fixture.",
            }
        ],
    )
    assert "prog --backend https://ohb.works" in wrapper_body(m, m.launchers[0])


def test_a_working_directory_becomes_a_guarded_cd() -> None:
    m = manifest(launchers=[{"name": "l", "exec": "./RUN", "working_directory": "/opt/x"}])
    body = wrapper_body(m, m.launchers[0])
    assert "cd '/opt/x' || exit 1" in body
    assert body.splitlines()[-1] == "./RUN"


def test_desktop_entry_carries_mapped_categories_and_the_marker(tmp_path: Path) -> None:
    m = manifest()
    entry = desktop_entry(m, m.launchers[0], tmp_path / "bin" / "launchable")
    assert "Categories=" in entry
    for category in ("HamRadio", "AudioVideo", "Geography"):
        assert category in entry, entry
    assert "X-Hammunition-Package=launchable" in entry
    assert "Terminal=false" in entry


def test_steps_write_both_artifacts_and_they_are_real(tmp_path: Path) -> None:
    m = manifest()
    steps = launcher_steps(m, bin_dir=tmp_path / "bin", applications_dir=tmp_path / "apps")
    assert [s.kind for s in steps] == ["wrapper", "desktop-entry"]
    for step in steps:
        step.perform()
    wrapper = tmp_path / "bin" / "launchable"
    assert os.access(wrapper, os.X_OK)
    entry = (tmp_path / "apps" / "hammunition-launchable.desktop").read_text()
    assert f"Exec={wrapper}" in entry


def test_a_manifest_with_no_launchers_plans_nothing() -> None:
    m = manifest(launchers=[])
    assert launcher_steps(m, bin_dir=Path("/x"), applications_dir=Path("/y")) == []


def test_campaign_report_buckets_and_names_every_unit() -> None:
    """The campaign renderer: every unit gets a row, failures carry their
    evidence text, refusals are not counted as failures."""
    import importlib.util
    from pathlib import Path as P

    spec = importlib.util.spec_from_file_location(
        "vm_campaign", P(__file__).resolve().parent.parent / "scripts" / "vm_campaign.py"
    )
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    import sys as _sys

    _sys.modules["vm_campaign"] = mod
    spec.loader.exec_module(mod)

    results = [
        mod.UnitResult("good", 0, 12.0, "Done. 2 command(s) completed and confirmed."),
        mod.UnitResult("gap", 2, 1.0, "resolves to the pipx backend"),
        mod.UnitResult("broken", 1, 300.0, "make: *** Error 1"),
    ]
    report = mod.render_report(
        target_line="Testville 1.0", engine_commit="abc1234", results=results
    )
    assert "3 — 1 installed+confirmed, 1 refused at plan time, 1 failed" in report
    for unit in ("good", "gap", "broken"):
        assert f"| `{unit}` |" in report
    assert "## Failures" in report and "make: *** Error 1" in report
    assert "## Plan-time refusals" in report and "pipx backend" in report


def test_campaign_files_a_budget_stop_as_stopped_not_failed() -> None:
    """The per-unit budget is enforced on the VM by ``timeout``, whose exit
    124 must be filed as a stop, in its own bucket, and never read as the
    engine's own failure. A local timeout used to leave the remote build
    running and file it failed; qlog on Ubuntu 26.04 then completed 132 s
    after being written off."""
    import importlib.util
    from pathlib import Path as P

    spec = importlib.util.spec_from_file_location(
        "vm_campaign", P(__file__).resolve().parent.parent / "scripts" / "vm_campaign.py"
    )
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    stopped = mod.classify("qlog", "  $ make -j 1\n__EXIT=124\n", seconds=900.4, timeout=900)
    assert stopped.exit_code == 124
    assert stopped.outcome == "STOPPED (budget)"
    assert "900s budget" in stopped.tail
    done = mod.classify(
        "qlog", "Done. 11 command(s) completed.\n__EXIT=0\n", seconds=5, timeout=900
    )
    assert done.exit_code == 0 and "Done." in done.tail
    report = mod.render_report(target_line="T", engine_commit="abc", results=[stopped, done])
    assert "1 installed+confirmed, 0 refused at plan time, 0 failed, 1 stopped" in report
    assert "STOPPED (budget)" in report and "## Stopped by the budget" in report
    assert "## Failures" not in report
