# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""Launcher generation: endpoints resolved, workdirs honoured, menus fed."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any

import pytest

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


def _unreset(mod: object, commit: str) -> object:
    """A campaign that reset nothing and read no apt lists: the header says so."""
    return mod.Provenance(  # type: ignore[attr-defined]
        engine_commit=commit,
        dirty_files=0,
        domain=None,
        snapshot=None,
        snapshot_created=None,
        apt_lists=(),
        prepared_at=None,
    )


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
        target_line="Testville 1.0", provenance=_unreset(mod, "abc1234"), results=results
    )
    assert (
        "3 — 1 installed+confirmed (1 by no effect check), 1 refused at plan time, 1 failed"
        in report
    )
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
    report = mod.render_report(
        target_line="T", provenance=_unreset(mod, "abc"), results=[stopped, done]
    )
    assert (
        "1 installed+confirmed (1 by no effect check), 0 refused at plan time, 0 failed, 1 stopped"
        in report
    )
    assert "STOPPED (budget)" in report and "## Stopped by the budget" in report
    assert "## Failures" not in report


def test_campaign_files_a_declined_consent_gate_as_neither_failure_nor_refusal() -> None:
    """A gated profile on a non-interactive stdin stops at its gate — exit 3
    — because the campaign never affirms one (D-021). The Debian 13
    whole-profile report counted `rf-research` as its one failure and printed
    the gate's question under *Failures*, which reads as a defect it is not."""
    import importlib.util
    from pathlib import Path as P

    spec = importlib.util.spec_from_file_location(
        "vm_campaign", P(__file__).resolve().parent.parent / "scripts" / "vm_campaign.py"
    )
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    gated = mod.UnitResult("rf-research", 3, 4.0, "Do you affirm that you have the authorization")
    done = mod.UnitResult("sdr", 0, 162.0, "Done.")
    report = mod.render_report(
        target_line="T", provenance=_unreset(mod, "abc"), results=[gated, done]
    )
    assert (
        "1 installed+confirmed (1 by no effect check), 0 refused at plan time, 0 failed, "
        "1 stopped at a consent gate" in report
    )
    assert "| `rf-research` | consent declined |" in report
    assert "## Failures" not in report
    assert "## Consent gates presented" in report and "Do you affirm" in report


def test_campaign_prepare_refreshes_apt_lists_and_keeps_its_failure_text(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Two things the Parrot and Kali campaigns of 2026-09-03 proved. Parrot:
    a clean-baseline four days old still named glib2.0 2.84.4-3~deb13u3 and
    the pool had moved on, so six of fifteen profiles failed at the first
    fetch with a 404 — the prepare must refresh the lists, before the venv
    (so a guest whose sudo is not passwordless fails prepare, not unit 1).
    Kali: prepare failed at profile 5 with a bare CalledProcessError and
    nothing captured, so a PyPI hiccup and a broken guest were the same
    verdict — the failure text is printed and the transient kind is retried."""
    import importlib.util
    from pathlib import Path as P

    spec = importlib.util.spec_from_file_location(
        "vm_campaign", P(__file__).resolve().parent.parent / "scripts" / "vm_campaign.py"
    )
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    remote = mod.PREPARE_REMOTE
    assert "sudo -n apt-get update" in remote
    assert remote.index("apt-get update") < remote.index("python3 -m venv")
    # Pop!_OS 24.04 runs its own apt-get at boot and held the lists lock
    # against the first prepare (2026-09-04). DPkg::Lock::Timeout does not
    # cover that lock (measured: 0 s wait, apt 3.0.3), so the update is
    # retried in a bounded loop instead.
    assert "until sudo -n apt-get update" in remote and "-ge 30" in remote

    calls: list[list[str]] = []
    outcomes = iter(
        [
            subprocess.CompletedProcess(
                [], 1, stdout="", stderr="ERROR: Could not fetch URL https://pypi.org/simple/"
            ),
            subprocess.CompletedProcess([], 0, stdout="hammunition 0.7.0\n", stderr=""),
        ]
    )

    def fake_run(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        return next(outcomes)

    monkeypatch.setattr(mod.subprocess, "run", fake_run)
    mod.prepare(["ssh"], "user@guest")
    assert len(calls) == 2 and calls[0][-1] == remote
    out = capsys.readouterr().out
    assert "prepare attempt 1/2 failed (exit 1)" in out
    assert "Could not fetch URL https://pypi.org/simple/" in out

    always = subprocess.CompletedProcess([], 1, stdout="", stderr="venv: command not found")
    monkeypatch.setattr(mod.subprocess, "run", lambda argv, **kw: always)
    with pytest.raises(SystemExit, match="could not be prepared after 2 attempts"):
        mod.prepare(["ssh"], "user@guest")
    assert "venv: command not found" in capsys.readouterr().out
