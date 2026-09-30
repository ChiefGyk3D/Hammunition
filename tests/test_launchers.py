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
from hammunition.manifest.schema import ManifestError, PackageManifest


def manifest(**overrides: Any) -> PackageManifest:
    base: dict[str, Any] = {
        "name": "launchable",
        "version": "1.0",
        "summary": "Fixture with a launcher",
        "categories": ["sdr-receivers", "aprs"],
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


def test_desktop_entry_name_is_the_title_when_one_is_given(tmp_path: Path) -> None:
    # yagiuda's interactive program is called `input`; a menu entry called
    # "input" tells nobody what it is. The title is what the menu shows and
    # the name stays the wrapper's filename, so `type input` still finds it.
    m = manifest(
        launchers=[
            {"name": "input", "exec": "input", "terminal": True, "title": "Yagi-Uda design (input)"}
        ]
    )
    entry = desktop_entry(m, m.launchers[0], tmp_path / "bin" / "input")
    assert "Name=Yagi-Uda design (input)\n" in entry
    assert "Exec=" + str(tmp_path / "bin" / "input") in entry


def test_desktop_entry_name_falls_back_to_the_launcher_name(tmp_path: Path) -> None:
    m = manifest()
    entry = desktop_entry(m, m.launchers[0], tmp_path / "bin" / "launchable")
    assert "Name=launchable\n" in entry


def test_a_blank_title_is_refused_rather_than_rendering_an_unnamed_entry() -> None:
    from pydantic import ValidationError

    with pytest.raises((ValidationError, ManifestError), match="title"):
        manifest(launchers=[{"name": "l", "exec": "l", "title": "  "}])


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
            subprocess.CompletedProcess([], 0, stdout="hammunition 0.9.0\n", stderr=""),
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


# ---------------------------------------------------------------------------
# D-050 follow-up (2026-09-12): a terminal launcher holds its window open.
# A menu entry that runs `hackrf_info` in a terminal and closes the window
# the instant it exits shows the operator nothing; Parrot's own tool menu
# keeps the window. The wrapper does the holding, so the desktop entry and
# the manifest stay plain.
# ---------------------------------------------------------------------------


def test_a_terminal_launcher_waits_for_enter_after_the_command_exits() -> None:
    m = manifest(launchers=[{"name": "l", "exec": "hackrf_info", "terminal": True}])
    body = wrapper_body(m, m.launchers[0])
    lines = body.splitlines()
    assert "hackrf_info" in lines
    assert any("read" in line for line in lines[lines.index("hackrf_info") :]), body
    assert "exit" in body.lower() and "Enter" in body
    # The hold must not replace the tool's exit status with its own. Run
    # without a keyboard (the headless GUI smoke lane, 2026-09-12), `read`
    # hits end-of-input and fails, and a wrapper that ends there exits 1
    # whatever the tool did: st-info printed "[exit 0]" and the lane
    # recorded rc=1.
    assert lines[-1] == 'exit "$status"', body


@pytest.mark.parametrize("command, expected", [("true", 0), ("sh -c 'exit 3'", 3)])
def test_a_terminal_wrapper_run_without_a_keyboard_exits_with_the_tools_status(
    tmp_path: Path, command: str, expected: int
) -> None:
    import subprocess

    m = manifest(launchers=[{"name": "l", "exec": command, "terminal": True}])
    wrapper = tmp_path / "l"
    wrapper.write_text(wrapper_body(m, m.launchers[0]))
    wrapper.chmod(0o755)
    run = subprocess.run(
        [str(wrapper)], stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=10
    )
    assert run.returncode == expected, (run.returncode, run.stdout, run.stderr)


def test_a_gui_launcher_does_not_hold() -> None:
    m = manifest(launchers=[{"name": "l", "exec": "exec gqrx"}])
    body = wrapper_body(m, m.launchers[0])
    assert body.splitlines()[-1] == "exec gqrx"


def test_a_terminal_launcher_may_not_exec_away_the_shell_that_would_hold() -> None:
    from pydantic import ValidationError

    from hammunition.manifest.schema import ManifestError

    with pytest.raises((ValidationError, ManifestError), match="terminal"):
        manifest(launchers=[{"name": "l", "exec": "exec hackrf_info", "terminal": True}])


# ---------------------------------------------------------------------------
# A wrapper named like its tool must run the tool, not itself.
# ---------------------------------------------------------------------------


def _user_task_count() -> int:
    """What RLIMIT_NPROC is compared against: every thread of every process
    of this user, not the process count /proc's directory listing gives."""
    uid = os.getuid()
    count = 0
    for entry in os.listdir("/proc"):
        if not entry.isdigit():
            continue
        try:
            if os.stat(f"/proc/{entry}").st_uid != uid:
                continue
            status = Path(f"/proc/{entry}/status").read_text()
        except OSError:
            continue
        for line in status.splitlines():
            if line.startswith("Threads:"):
                count += int(line.split()[1])
                break
    return count


def test_a_wrapper_named_like_its_tool_runs_the_tool_and_not_itself(tmp_path: Path) -> None:
    """The wrapper lands in ``~/.local/bin`` under the tool's own name, and
    Debian's ``.profile`` puts that directory first on PATH. Measured on the
    field laptop: ``~/.local/bin/ubertooth-util`` ran ``ubertooth-util -v``,
    which resolved to the wrapper again, forever. The wrapper must take its
    own directory out of PATH before the command line."""
    import resource

    m = manifest(launchers=[{"name": "tool", "exec": "tool -v", "terminal": True}])
    bin_dir = tmp_path / "bin"
    real_dir = tmp_path / "real"
    bin_dir.mkdir()
    real_dir.mkdir()
    (bin_dir / "tool").write_text(wrapper_body(m, m.launchers[0]))
    (bin_dir / "tool").chmod(0o755)
    (real_dir / "tool").write_text('#!/bin/sh\necho "real tool ran $*"\n')
    (real_dir / "tool").chmod(0o755)

    # The unfixed wrapper forks itself without bound. A process-count ceiling
    # a little above what this user already runs makes that fail fast inside
    # this subtree only; the process group is killed on timeout regardless.
    ceiling = _user_task_count() + 40

    def limit() -> None:
        resource.setrlimit(resource.RLIMIT_NPROC, (ceiling, ceiling))

    proc = subprocess.Popen(
        ["/bin/sh", str(bin_dir / "tool")],
        env={"PATH": f"{bin_dir}:{real_dir}"},
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        start_new_session=True,
        preexec_fn=limit,
    )
    try:
        out, _ = proc.communicate(timeout=20)
    except subprocess.TimeoutExpired:
        os.killpg(proc.pid, 9)
        proc.wait()
        pytest.fail("the wrapper did not finish: it is calling itself")
    assert "real tool ran -v" in out, out
    assert "[exit 0]" in out, out
    assert out.count("real tool ran") == 1, out


# ---------------------------------------------------------------------------
# Issue #145: a launcher runs the engine by absolute path.
#
# Plasma starts a menu entry as a systemd user service, whose PATH has no
# ~/.local/bin. `qmapshack-offline` was the three lines `hammunition maps
# qmapshack` and died with "hammunition: not found", status 127, on the dev
# desktop 2026-09-29. The launcher now names the hammunition that wrote it.
# ---------------------------------------------------------------------------


def _engine_manifest(terminal: bool = False) -> PackageManifest:
    return manifest(
        name="qmapshack",
        launchers=[
            {
                "name": "qmapshack-offline",
                "exec": "hammunition maps qmapshack",
                "terminal": terminal,
            }
        ],
    )


def _fake_engine(where: Path) -> Path:
    where.parent.mkdir(parents=True, exist_ok=True)
    where.write_text('#!/bin/sh\necho "engine ran $*"\n')
    where.chmod(0o755)
    return where


def _only_argv0(monkeypatch: pytest.MonkeyPatch, argv0: str, tmp_path: Path) -> None:
    """The running engine is argv[0] and nothing else can be found."""
    import sys

    monkeypatch.setattr(sys, "argv", [argv0, "install", "navigation"])
    monkeypatch.setattr(sys, "executable", str(tmp_path / "no-venv" / "bin" / "python3"))
    monkeypatch.setattr("hammunition.launchers.shutil.which", lambda _name: None)


def test_a_launcher_calling_the_engine_names_it_by_absolute_path() -> None:
    m = _engine_manifest()
    engine = Path("/home/op/Hammunition/.venv/bin/hammunition")
    body = wrapper_body(m, m.launchers[0], engine=engine)
    assert body.splitlines()[-1] == f"{engine} maps qmapshack", body
    assert "\nhammunition " not in body


def test_an_engine_path_with_a_space_is_quoted_for_the_shell() -> None:
    m = _engine_manifest()
    body = wrapper_body(m, m.launchers[0], engine=Path("/home/op/my checkout/hammunition"))
    assert body.splitlines()[-1] == "'/home/op/my checkout/hammunition' maps qmapshack", body


def test_a_launcher_calling_the_engine_refuses_without_one() -> None:
    from hammunition.backends.base import BackendError

    m = _engine_manifest()
    with pytest.raises(BackendError, match="hammunition"):
        wrapper_body(m, m.launchers[0])


def test_a_launcher_not_calling_the_engine_is_unchanged() -> None:
    m = manifest(launchers=[{"name": "l", "exec": "hammunition-tray --x"}])
    assert wrapper_body(m, m.launchers[0]).splitlines()[-1] == "hammunition-tray --x"


def test_the_engine_is_the_running_argv0_made_absolute(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from hammunition.launchers import engine_path

    engine = _fake_engine(tmp_path / "checkout" / ".venv" / "bin" / "hammunition")
    monkeypatch.chdir(tmp_path / "checkout")
    _only_argv0(monkeypatch, ".venv/bin/hammunition", tmp_path)
    assert engine_path(tmp_path / "home" / ".local" / "bin") == engine


def test_the_local_bin_link_is_preferred_when_it_runs_this_engine(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """So a venv that moves is fixed by re-running bootstrap, which relinks,
    rather than by regenerating every launcher."""
    from hammunition.launchers import engine_path

    engine = _fake_engine(tmp_path / "checkout" / ".venv" / "bin" / "hammunition")
    bin_dir = tmp_path / "home" / ".local" / "bin"
    bin_dir.mkdir(parents=True)
    (bin_dir / "hammunition").symlink_to(engine)
    _only_argv0(monkeypatch, str(engine), tmp_path)
    assert engine_path(bin_dir) == bin_dir / "hammunition"


def test_a_local_bin_link_to_another_checkout_is_not_used(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from hammunition.launchers import engine_path

    engine = _fake_engine(tmp_path / "this" / ".venv" / "bin" / "hammunition")
    other = _fake_engine(tmp_path / "other" / ".venv" / "bin" / "hammunition")
    bin_dir = tmp_path / "home" / ".local" / "bin"
    bin_dir.mkdir(parents=True)
    (bin_dir / "hammunition").symlink_to(other)
    _only_argv0(monkeypatch, str(engine), tmp_path)
    assert engine_path(bin_dir) == engine


def test_run_as_a_module_the_engine_is_the_venvs_entry_point(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`python -m hammunition` has __main__.py as argv[0]; the entry point
    sits beside the interpreter in the venv."""
    import sys

    from hammunition.launchers import engine_path

    engine = _fake_engine(tmp_path / "venv" / "bin" / "hammunition")
    monkeypatch.setattr(sys, "argv", [str(tmp_path / "src" / "hammunition" / "__main__.py")])
    monkeypatch.setattr(sys, "executable", str(tmp_path / "venv" / "bin" / "python3"))
    monkeypatch.setattr("hammunition.launchers.shutil.which", lambda _name: None)
    assert engine_path(tmp_path / "bin") == engine


def test_no_findable_engine_is_a_refusal_naming_bootstrap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from hammunition.backends.base import BackendError
    from hammunition.launchers import engine_path

    _only_argv0(monkeypatch, str(tmp_path / "pytest"), tmp_path)
    with pytest.raises(BackendError, match="bootstrap"):
        engine_path(tmp_path / "bin")


def test_launcher_steps_write_the_absolute_engine_and_the_plan_names_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine = _fake_engine(tmp_path / "checkout" / ".venv" / "bin" / "hammunition")
    _only_argv0(monkeypatch, str(engine), tmp_path)
    m = _engine_manifest()
    steps = launcher_steps(m, bin_dir=tmp_path / "bin", applications_dir=tmp_path / "apps")
    wrapper_step = steps[0]
    assert str(engine) in wrapper_step.detail, "the dry run shows which engine the launcher runs"
    for step in steps:
        step.perform()
    body = (tmp_path / "bin" / "qmapshack-offline").read_text()
    assert f"{engine} maps qmapshack" in body
    assert body.splitlines()[1] == "# generated by hammunition for qmapshack", (
        "uninstall finds its wrappers by this marker"
    )


def test_the_launcher_runs_with_a_service_path_that_lacks_local_bin(tmp_path: Path) -> None:
    """The property #145 is about: run with the PATH a systemd user service
    gets, which has no ~/.local/bin, the launcher still reaches the engine."""
    engine = _fake_engine(tmp_path / "home" / "Hammunition" / ".venv" / "bin" / "hammunition")
    m = _engine_manifest()
    wrapper = tmp_path / "home" / ".local" / "bin" / "qmapshack-offline"
    wrapper.parent.mkdir(parents=True)
    wrapper.write_text(wrapper_body(m, m.launchers[0], engine=engine))
    wrapper.chmod(0o755)
    run = subprocess.run(
        [str(wrapper)],
        env={"PATH": "/usr/local/bin:/usr/bin:/bin"},
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert run.returncode == 0, (run.returncode, run.stderr)
    assert run.stdout.strip() == "engine ran maps qmapshack"


def test_engine_call_reads_back_what_the_launcher_runs() -> None:
    from hammunition.launchers import engine_call

    m = _engine_manifest(terminal=True)
    absolute = wrapper_body(m, m.launchers[0], engine=Path("/opt/x y/hammunition"))
    assert engine_call(absolute) == "/opt/x y/hammunition"
    legacy = "#!/bin/sh\n# generated by hammunition for qmapshack\nhammunition maps qmapshack\n"
    assert engine_call(legacy) == "hammunition"
    plain = wrapper_body(manifest(), manifest().launchers[0])
    assert engine_call(plain) is None


def test_survey_sorts_launchers_by_whether_their_engine_runs(tmp_path: Path) -> None:
    from hammunition.launchers import survey_engine_launchers

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    engine = _fake_engine(tmp_path / "venv" / "hammunition")
    m = _engine_manifest()
    (bin_dir / "good").write_text(wrapper_body(m, m.launchers[0], engine=engine))
    (bin_dir / "gone").write_text(
        wrapper_body(m, m.launchers[0], engine=tmp_path / "moved" / "hammunition")
    )
    (bin_dir / "bare").write_text(
        "#!/bin/sh\n# generated by hammunition for qmapshack\nhammunition maps qmapshack\n"
    )
    (bin_dir / "unrelated").write_text("#!/bin/sh\nhammunition maps qmapshack\n")
    (bin_dir / "plain").write_text(wrapper_body(manifest(), manifest().launchers[0]))
    (bin_dir / "hammunition").symlink_to(engine)
    survey = survey_engine_launchers(bin_dir)
    assert survey.ok == (str(bin_dir / "good"),)
    assert survey.bare == (str(bin_dir / "bare"),)
    assert survey.broken == ((str(bin_dir / "gone"), str(tmp_path / "moved" / "hammunition")),)


def test_survey_of_a_missing_bin_dir_is_empty(tmp_path: Path) -> None:
    from hammunition.launchers import survey_engine_launchers

    survey = survey_engine_launchers(tmp_path / "absent")
    assert survey.ok == () and survey.bare == () and survey.broken == ()
