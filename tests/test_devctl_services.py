# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""The tray's allow-list of user services, written when a user_services unit is
installed and trimmed when it is uninstalled.  D-073, amended 2026-10-02.

Contract v1 of hammunition-tray's helper: `~/.config/hammunition/devctl-services.yaml`,
`version: 1` and `services: [{name, unit, scope: user, description}]`, 0600.
"""

from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest
import yaml

from hammunition.backends import Action
from hammunition.devctl_services import (
    FILE_NAME,
    HEADER,
    Row,
    remove_row,
    row_for,
    service_name,
    update_file,
)
from hammunition.execute import user_service_removal_steps, user_service_steps
from hammunition.userservice import PlannedUserService


def _svc(name: str, unit: str, description: str = "d") -> PlannedUserService:
    return PlannedUserService(
        name=name,
        description=description,
        exec_argv=("/p",),
        unit_body="x\n",
        device_path=None,
        filled_from=(),
        listens=(),
        unit=unit,
        plain=True,
    )


def test_the_row_name_is_the_catalog_unit_without_a_service_suffix() -> None:
    assert service_name("gps-tether") == "gps-tether"
    assert service_name("rig-service") == "rig"


def test_a_row_is_the_first_service_of_its_unit_in_the_contracts_shape() -> None:
    row = row_for(
        [
            _svc("hammunition-rigctld", "rig-service", "rigctld for this operator"),
            _svc("hammunition-rig-proxy", "rig-service"),
        ]
    )
    assert row == Row("rig", "hammunition-rigctld.service", "rigctld for this operator")


def test_a_description_is_cut_and_cleaned_to_the_contracts_rules() -> None:
    row = row_for([_svc("hammunition-x", "x", "a\x07b" + "z" * 300)])
    assert len(row.description) <= 200 and "\x07" not in row.description


def test_the_file_is_created_0600_with_the_header_and_atomically(tmp_path: Path) -> None:
    path = tmp_path / "hammunition" / FILE_NAME
    update_file(path, add=Row("gps-tether", "hammunition-gps-tether.service", "GPS: position"))
    text = path.read_text()
    assert text.splitlines()[0] == HEADER
    assert HEADER == "# Written by `hammunition install` (D-073, amended 2026-10-02)."
    assert yaml.safe_load(text) == {
        "version": 1,
        "services": [
            {
                "name": "gps-tether",
                "unit": "hammunition-gps-tether.service",
                "scope": "user",
                "description": "GPS: position",
            }
        ],
    }
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert [p.name for p in path.parent.iterdir()] == [FILE_NAME], "no temp file left behind"


def test_a_second_unit_is_appended_and_a_reinstall_replaces_its_own_row(tmp_path: Path) -> None:
    path = tmp_path / FILE_NAME
    update_file(path, add=Row("gps-tether", "a.service", "one"))
    update_file(path, add=Row("rig", "hammunition-rigctld.service", "two"))
    update_file(path, add=Row("gps-tether", "a.service", "one, again"))
    rows = yaml.safe_load(path.read_text())["services"]
    assert [(r["name"], r["description"]) for r in rows] == [
        ("rig", "two"),
        ("gps-tether", "one, again"),
    ] or [(r["name"], r["description"]) for r in rows] == [
        ("gps-tether", "one, again"),
        ("rig", "two"),
    ]
    assert len(rows) == 2


def test_removing_a_row_keeps_the_others_and_the_last_removal_deletes_the_file(
    tmp_path: Path,
) -> None:
    path = tmp_path / FILE_NAME
    update_file(path, add=Row("gps-tether", "a.service", "one"))
    update_file(path, add=Row("rig", "b.service", "two"))
    update_file(path, remove_name="gps-tether")
    assert [r["name"] for r in yaml.safe_load(path.read_text())["services"]] == ["rig"]
    update_file(path, remove_name="rig")
    assert not path.exists()


def test_removal_from_a_missing_file_creates_nothing(tmp_path: Path) -> None:
    path = tmp_path / "hammunition" / FILE_NAME
    update_file(path, remove_name="rig")
    assert not path.parent.exists()


def test_a_file_that_is_not_parseable_is_left_alone_and_said_so(tmp_path: Path) -> None:
    path = tmp_path / FILE_NAME
    path.write_text("services: [unclosed\n")
    outcome = update_file(path, add=Row("rig", "b.service", "two"))
    assert path.read_text() == "services: [unclosed\n"
    assert "left" in outcome and "not" in outcome


def test_a_symlink_is_never_followed(tmp_path: Path) -> None:
    target = tmp_path / "victim"
    target.write_text("keep\n")
    path = tmp_path / FILE_NAME
    os.symlink(target, path)
    update_file(path, add=Row("rig", "b.service", "two"))
    assert target.read_text() == "keep\n"


def test_remove_row_is_pure() -> None:
    rows = [Row("a", "a.service", "x"), Row("b", "b.service", "y")]
    assert remove_row(rows, "a") == [Row("b", "b.service", "y")]


def test_install_steps_write_the_row_after_the_unit_files(tmp_path: Path) -> None:
    from dataclasses import dataclass

    @dataclass
    class _Plan:
        user_services: tuple[PlannedUserService, ...]

    plan = _Plan((_svc("hammunition-gps-tether", "gps-tether", "GPS position"),))
    steps = user_service_steps(plan, home=tmp_path)  # type: ignore[arg-type]
    rows = [s for s in steps if isinstance(s, Action) and s.kind == "devctl_row"]
    assert len(rows) == 1
    assert str(tmp_path / "hammunition" / FILE_NAME) in rows[0].detail
    rows[0].perform()
    data = yaml.safe_load((tmp_path / "hammunition" / FILE_NAME).read_text())
    assert data["services"][0]["name"] == "gps-tether"


def test_uninstall_steps_remove_the_units_row_even_without_a_unit_file(tmp_path: Path) -> None:
    update_file(tmp_path / "hammunition" / FILE_NAME, add=Row("gps-tether", "u.service", "one"))
    steps = user_service_removal_steps(
        ["hammunition-gps-tether"], home=tmp_path, units=["gps-tether"]
    )
    for step in steps:
        if isinstance(step, Action) and step.kind == "devctl_row":
            step.perform()
    assert not (tmp_path / "hammunition" / FILE_NAME).exists()


def test_a_rig_install_lists_the_rig_row(tmp_path: Path) -> None:
    from dataclasses import dataclass

    @dataclass
    class _Plan:
        user_services: tuple[PlannedUserService, ...]

    plan = _Plan(
        (_svc("hammunition-rigctld", "rig-service"), _svc("hammunition-rig-proxy", "rig-service"))
    )
    steps = user_service_steps(plan, home=tmp_path)  # type: ignore[arg-type]
    assert len([s for s in steps if isinstance(s, Action) and s.kind == "devctl_row"]) == 1
    pytest.importorskip("yaml")
