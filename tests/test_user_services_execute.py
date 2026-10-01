# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""Writing and enabling the rig user service, and reversing it.  D-073 §6c, §6d."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

from hammunition.backends import Action, Command
from hammunition.execute import (
    _user_unit_path,
    user_service_removal_steps,
    user_service_steps,
)
from hammunition.userservice import HEADER, PlannedUserService

_BY_ID = "/dev/serial/by-id/usb-Silicon_Labs_CP2105_...-if00-port0"


def _service(device_path: str | None = _BY_ID) -> PlannedUserService:
    return PlannedUserService(
        name="hammunition-rigctld",
        description="hamlib rigctld for the station's rig",
        exec_argv=("/usr/bin/rigctld", "-m", "1035", "-r", _BY_ID, "-t", "4532"),
        unit_body=HEADER + "\n[Service]\nExecStart=/usr/bin/rigctld\n",
        device_path=device_path,
        filled_from=("rig", "rig_baud", "rig_device"),
        listens=(("127.0.0.1", 4532),),
    )


@dataclass
class _Plan:
    user_services: tuple[PlannedUserService, ...]


def test_steps_write_then_daemon_reload_enable_restart(tmp_path: Path) -> None:
    present = tmp_path / "ttyfake"
    present.write_text("")  # stands in for the radio's device being present now
    plan = _Plan(user_services=(_service(device_path=str(present)),))
    steps = user_service_steps(plan, home=tmp_path, staging_root=tmp_path)  # type: ignore[arg-type]
    commands = [s for s in steps if isinstance(s, Command)]
    argvs = [c.argv for c in commands]
    assert ("systemctl", "--user", "daemon-reload") in argvs
    assert ("systemctl", "--user", "enable", "hammunition-rigctld.service") in argvs
    assert ("systemctl", "--user", "restart", "hammunition-rigctld.service") in argvs
    # Never through sudo: the service is the operator's (D-062).
    assert all(not c.requires_root for c in commands)


def test_restart_is_skipped_when_the_device_is_absent(tmp_path: Path) -> None:
    plan = _Plan(user_services=(_service(device_path=None),))
    steps = user_service_steps(plan, home=tmp_path, staging_root=tmp_path)  # type: ignore[arg-type]
    argvs = [s.argv for s in steps if isinstance(s, Command)]
    assert ("systemctl", "--user", "restart", "hammunition-rigctld.service") not in argvs
    assert ("systemctl", "--user", "enable", "hammunition-rigctld.service") in argvs


def test_a_write_action_lands_the_unit_file(tmp_path: Path) -> None:
    plan = _Plan(user_services=(_service(),))
    steps = user_service_steps(plan, home=tmp_path, staging_root=tmp_path)  # type: ignore[arg-type]
    writes = [s for s in steps if isinstance(s, Action)]
    assert writes
    writes[0].perform()
    unit = tmp_path / "systemd" / "user" / "hammunition-rigctld.service"
    assert unit.exists()
    assert unit.read_text().startswith(HEADER)


def test_the_machine_form_is_used_when_root_targets_an_operator(tmp_path: Path) -> None:
    plan = _Plan(user_services=(_service(),))
    steps = user_service_steps(plan, home=tmp_path, machine="op", staging_root=tmp_path)  # type: ignore[arg-type]
    argvs = [s.argv for s in steps if isinstance(s, Command)]
    assert ("systemctl", "--user", "--machine=op@.host", "daemon-reload") in argvs


def test_removal_disables_and_removes_only_our_file(tmp_path: Path) -> None:
    unit_dir = tmp_path / "systemd" / "user"
    unit_dir.mkdir(parents=True)
    ours = unit_dir / "hammunition-rigctld.service"
    ours.write_text(HEADER + "\n[Service]\n")

    steps = user_service_removal_steps(["hammunition-rigctld"], home=tmp_path)
    cmd_argvs = [s.argv for s in steps if isinstance(s, Command)]
    assert ("systemctl", "--user", "disable", "--now", "hammunition-rigctld.service") in cmd_argvs
    # The file-removing Action runs and removes our file.
    for step in steps:
        if isinstance(step, Action):
            step.perform()
    assert not ours.exists()


def test_removal_leaves_a_file_the_operator_rewrote(tmp_path: Path) -> None:
    unit_dir = tmp_path / "systemd" / "user"
    unit_dir.mkdir(parents=True)
    theirs = unit_dir / "hammunition-rigctld.service"
    theirs.write_text("[Service]\nExecStart=/usr/bin/rigctld -m 9999\n")  # no header

    steps = user_service_removal_steps(["hammunition-rigctld"], home=tmp_path)
    for step in steps:
        if isinstance(step, Action):
            step.perform()
    assert theirs.exists()  # not ours: left in place


def test_user_config_base_is_dot_config_not_the_app_subdir(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """C2: systemd reads ~/.config/systemd/user/, so the base the install
    passes must be the XDG config dir itself, never ~/.config/hammunition."""
    from hammunition.paths import user_config_base

    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / ".config"))
    base = user_config_base(None)
    assert base == tmp_path / ".config"
    unit = _user_unit_path(base, "hammunition-rigctld")
    assert unit == tmp_path / ".config" / "systemd" / "user" / "hammunition-rigctld.service"
    assert "hammunition/systemd" not in str(unit)
