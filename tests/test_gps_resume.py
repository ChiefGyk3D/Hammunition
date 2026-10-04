# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""The resume step's plan, install, verify and removal (issue #177).

Every path is under the test's tmp_path (`resume_files`); `systemctl enable`
and `disable` are simulated by making and removing the ``.wants`` links, which
is what they do to disk.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from hammunition.backends.base import Command
from hammunition.hardware import gps_resume as gr


def _install(commands: list[Command]) -> None:
    """Do to disk what each command would, as the CLI's fake runners do."""
    for command in commands:
        argv = command.argv
        if argv[0] == "install":
            src, dest = Path(argv[-2]), Path(argv[-1])
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(src.read_bytes())
            os.chmod(dest, int(argv[argv.index("-m") + 1], 8))
        elif argv[:2] == ("systemctl", "enable"):
            for link in gr.wants_links():
                Path(link).parent.mkdir(parents=True, exist_ok=True)
                if not Path(link).is_symlink():
                    Path(link).symlink_to(gr.unit_path())
        elif argv[:2] == ("systemctl", "disable"):
            for link in gr.wants_links():
                Path(link).unlink(missing_ok=True)
        elif argv[:2] == ("rm", "-f"):
            for path in argv[2:]:
                Path(path).unlink(missing_ok=True)


def _applied(tmp_path: Path) -> None:
    step = gr.plan_gps_resume()
    staging = tmp_path / "staging"
    staging.mkdir(exist_ok=True)
    gr.stage(step, staging)
    _install(gr.install_commands(step, str(staging)))


def test_the_unit_runs_after_and_is_wanted_by_every_sleep_target() -> None:
    unit = gr.unit_content()
    targets = "suspend.target hibernate.target hybrid-sleep.target suspend-then-hibernate.target"
    assert f"After={targets}\n" in unit
    assert f"WantedBy={targets}\n" in unit
    assert "Type=oneshot\n" in unit
    assert f"ExecStart={gr.SCRIPT}\n" in unit
    assert unit.startswith(gr.UNIT_HEADER)


def test_the_script_is_the_module_source_under_a_shebang_and_our_header() -> None:
    text = gr.script_content()
    lines = text.splitlines()
    assert lines[0] == "#!/usr/bin/python3 -I"
    assert lines[1].startswith(gr.UNIT_HEADER)
    source = (Path(gr.__file__).parent / "gps_resume_script.py").read_text()
    assert text.endswith(source)


def test_a_fresh_machine_with_gpsd_plans_all_three_files_and_the_enable(resume_files: Path) -> None:
    step = gr.plan_gps_resume()
    assert step.gpsd and not step.is_noop
    argv = [c.argv for c in gr.install_commands(step, "<staging>")]
    assert argv == [
        ("install", "-D", "-m", "0755", "<staging>/hammunition-gps-resume", gr.SCRIPT),
        (
            "install",
            "-D",
            "-m",
            "0644",
            "<staging>/tmpfiles-hammunition-gps-resume.conf",
            gr.TMPFILES,
        ),
        ("systemd-tmpfiles", "--create", gr.TMPFILES),
        ("install", "-D", "-m", "0644", "<staging>/hammunition-gps-resume.service", gr.unit_path()),
        ("systemctl", "daemon-reload"),
        ("systemctl", "enable", "hammunition-gps-resume.service"),
    ]
    assert all(c.requires_root for c in gr.install_commands(step, "<staging>"))


def test_without_gpsd_nothing_is_planned_and_the_plan_says_why(resume_files: Path) -> None:
    Path(gr.GPSD).unlink()
    step = gr.plan_gps_resume()
    assert step.is_noop
    assert gr.install_commands(step, "<staging>") == []
    assert "gpsd is not installed" in "\n".join(gr.disclose(step))


def test_the_disclosure_prints_both_files_whole_and_how_to_inspect_and_reverse(
    resume_files: Path,
) -> None:
    text = "\n".join(gr.disclose(gr.plan_gps_resume()))
    for line in gr.unit_content().splitlines():
        assert line in text
    for line in gr.script_content().splitlines():
        assert line in text
    assert "systemctl status hammunition-gps-resume.service" in text
    assert "journalctl -u hammunition-gps-resume.service" in text
    assert "hammunition hardware unapply" in text
    assert "--no-gps-resume" in text
    assert "parked receiver is never woken" in text
    assert "power-cycle it once" in text
    assert "`authorized` switch" in text
    assert "loses its warm start" in text and "74 s" in text


def test_applied_and_verified_then_a_noop(resume_files: Path, tmp_path: Path) -> None:
    _applied(tmp_path)
    step = gr.plan_gps_resume()
    assert step.is_noop
    assert gr.disclose(step) == []
    assert gr.verify(step) == []
    assert gr.status() == "installed"
    assert os.stat(gr.SCRIPT).st_mode & 0o777 == 0o755


def test_verify_names_a_missing_link_and_a_wrong_mode(resume_files: Path, tmp_path: Path) -> None:
    _applied(tmp_path)
    Path(gr.wants_links()[1]).unlink()
    os.chmod(gr.SCRIPT, 0o644)
    problems = gr.verify(gr.plan_gps_resume())
    assert any("not enabled" in p and "hibernate.target.wants" in p for p in problems)
    assert any("0755" in p for p in problems)
    assert gr.status() == "stale"


def test_an_unenabled_unit_plans_only_the_enable(resume_files: Path, tmp_path: Path) -> None:
    _applied(tmp_path)
    for link in gr.wants_links():
        Path(link).unlink()
    argv = [c.argv for c in gr.install_commands(gr.plan_gps_resume(), "<staging>")]
    assert argv == [("systemctl", "enable", "hammunition-gps-resume.service")]


def test_an_older_script_of_ours_is_replaced(resume_files: Path, tmp_path: Path) -> None:
    _applied(tmp_path)
    Path(gr.SCRIPT).write_text(f"#!/usr/bin/python3 -I\n{gr.UNIT_HEADER} older\nprint()\n")
    step = gr.plan_gps_resume()
    assert not step.script_current
    assert [c.argv[-1] for c in gr.install_commands(step, "<staging>")] == [gr.SCRIPT]


@pytest.mark.parametrize("which", ["script", "unit", "tmpfiles"])
def test_a_file_hammunition_did_not_write_refuses_the_plan(resume_files: Path, which: str) -> None:
    path = Path({"script": gr.SCRIPT, "unit": gr.unit_path(), "tmpfiles": gr.TMPFILES}[which])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/bin/sh\n# the operator's own\n")
    with pytest.raises(gr.GpsResumeError, match="--no-gps-resume"):
        gr.plan_gps_resume()
    assert path.read_text() == "#!/bin/sh\n# the operator's own\n"


def test_removal_takes_back_both_files_and_the_links(resume_files: Path, tmp_path: Path) -> None:
    _applied(tmp_path)
    removal = gr.plan_gps_resume_removal()
    assert removal.unit_ours and removal.script_ours
    commands = gr.removal_commands(removal)
    assert [c.argv for c in commands] == [
        ("systemctl", "disable", "hammunition-gps-resume.service"),
        ("rm", "-f", gr.unit_path()),
        ("rm", "-f", gr.SCRIPT),
        ("rm", "-f", gr.TMPFILES, gr.LOG),
        ("rmdir", "--ignore-fail-on-non-empty", gr.RUN_DIR),
        ("systemctl", "daemon-reload"),
    ]
    _install(commands)
    assert gr.verify_removal(removal) == []
    assert gr.status() == "absent"
    assert gr.plan_gps_resume_removal().is_empty


def test_removal_leaves_a_file_someone_else_wrote(resume_files: Path) -> None:
    Path(gr.SCRIPT).parent.mkdir(parents=True)
    Path(gr.SCRIPT).write_text("#!/bin/sh\n")
    removal = gr.plan_gps_resume_removal()
    assert removal.is_empty
    assert gr.removal_commands(removal) == []


def test_verify_removal_names_what_survived(resume_files: Path, tmp_path: Path) -> None:
    _applied(tmp_path)
    removal = gr.plan_gps_resume_removal()
    problems = gr.verify_removal(removal)
    assert f"{gr.unit_path()} is still present" in problems
    assert f"{gr.SCRIPT} is still present" in problems
    assert any("suspend.target.wants" in p for p in problems)


def test_nothing_installed_reads_absent(resume_files: Path) -> None:
    assert gr.status() == "absent"
    assert gr.plan_gps_resume_removal().is_empty


def test_without_gpsd_a_foreign_file_does_not_block_the_plan(resume_files: Path) -> None:
    Path(gr.GPSD).unlink()
    Path(gr.SCRIPT).parent.mkdir(parents=True)
    Path(gr.SCRIPT).write_text("#!/bin/sh\n")
    assert gr.plan_gps_resume().is_noop


def test_a_binary_file_at_the_path_is_foreign_not_a_crash(resume_files: Path) -> None:
    Path(gr.SCRIPT).parent.mkdir(parents=True)
    Path(gr.SCRIPT).write_bytes(b"\x7fELF\xff\xfe")
    with pytest.raises(gr.GpsResumeError):
        gr.plan_gps_resume()
    assert gr.plan_gps_resume_removal().is_empty


def test_the_tmpfiles_line_makes_the_log_directory_world_readable_and_root_owned() -> None:
    text = gr.tmpfiles_content()
    assert text.startswith(gr.UNIT_HEADER)
    assert f"d {gr.RUN_DIR} 0755 root root -\n" in text
    assert f"{gr.RUN_DIR}/gps-resume.log" == gr.LOG


def test_an_engine_older_than_the_log_reads_stale_and_plans_only_the_tmpfiles_line(
    resume_files: Path, tmp_path: Path
) -> None:
    """A machine applied before the log existed: everything else current, the
    tmpfiles line absent. `doctor` says re-run apply, and apply adds just that."""
    _applied(tmp_path)
    Path(gr.TMPFILES).unlink()
    assert gr.status() == "stale"
    step = gr.plan_gps_resume()
    assert not step.is_noop and not step.tmpfiles_current
    assert [c.argv[0] for c in gr.install_commands(step, "<staging>")] == [
        "install",
        "systemd-tmpfiles",
    ]
    assert any(gr.TMPFILES in p for p in gr.verify(step))


def test_the_disclosure_names_the_tmpfiles_file_the_log_and_the_report(
    resume_files: Path,
) -> None:
    text = "\n".join(gr.disclose(gr.plan_gps_resume()))
    for line in gr.tmpfiles_content().splitlines():
        assert line in text
    assert gr.LOG in text
    assert "hammunition hardware gps-resume-report" in text


def test_removal_leaves_a_tmpfiles_file_someone_else_wrote(resume_files: Path) -> None:
    Path(gr.TMPFILES).parent.mkdir(parents=True)
    Path(gr.TMPFILES).write_text("d /run/hammunition 0700 root root -\n")
    assert gr.plan_gps_resume_removal().is_empty
