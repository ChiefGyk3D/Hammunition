# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""User services without a rig: plain entries, several units, headers.  D-073, amended."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from hammunition.backends import Action
from hammunition.execute import user_service_removal_steps
from hammunition.manifest.schema import ManifestError, PackageManifest
from hammunition.station import Station
from hammunition.userservice import (
    HEADER,
    header_for,
    is_ours,
    plan_user_services,
    render_unit_file,
)

_DOC: dict[str, object] = {
    "what_it_does": "Serves a position on loopback for the maps and the browser.",
    "why_you_want_it": "So the position is one service, not a window someone leaves open.",
    "upstream_url": "https://example.invalid/tether",
}

_PLAIN: dict[str, Any] = {
    "name": "hammunition-gps-tether",
    "description": "GPS position on 127.0.0.1",
    "exec": ["/usr/local/bin/hammunition-gps-tether"],
    "listens": [
        {"protocol": "tcp", "address": "127.0.0.1", "port": 10110},
        {"protocol": "tcp", "address": "127.0.0.1", "port": 10111},
    ],
}

_RIG: dict[str, Any] = {
    "name": "hammunition-rigctld",
    "description": "hamlib rigctld",
    "when_station": {"rig_kind": "cat"},
    "exec": [
        "/usr/bin/rigctld",
        "-m",
        "{station.rig_hamlib_model}",
        "-T",
        "127.0.0.1",
        "-t",
        "4632",
    ],
    "binds_to_device": "{station.rig_device}",
    "listens": [{"protocol": "tcp", "address": "127.0.0.1", "port": 4632}],
}


def _manifest(name: str, services: list[dict[str, Any]]) -> PackageManifest:
    return PackageManifest.model_validate(
        {
            "name": name,
            "version": "1.0",
            "summary": "A user service",
            "categories": ["navigation-maps"],
            "install": [{"install": {"method": "apt", "packages": ["gpsd"]}}],
            "update": {"probe": {"method": "apt_policy"}, "strategy": "apt_upgrade"},
            "documentation": _DOC,
            "user_services": services,
        }
    )


# -- schema: restart and restart_sec ---------------------------------------


def test_restart_defaults_keep_a_unit_as_it_was() -> None:
    (svc,) = _manifest("gps-tether", [_PLAIN]).user_services
    assert svc.restart == "on-failure"
    assert svc.restart_sec == 5


def test_restart_and_restart_sec_are_settable_within_bounds() -> None:
    (svc,) = _manifest(
        "gps-tether", [{**_PLAIN, "restart": "always", "restart_sec": 30}]
    ).user_services
    assert (svc.restart, svc.restart_sec) == ("always", 30)


@pytest.mark.parametrize(
    "extra",
    [
        {"restart": "sometimes"},
        {"restart_sec": 0},
        {"restart_sec": 301},
        {"restart": "on-failure; x"},
    ],
)
def test_restart_values_outside_the_fixed_set_are_refused(extra: dict[str, Any]) -> None:
    with pytest.raises((ValidationError, ManifestError)):
        _manifest("gps-tether", [{**_PLAIN, **extra}])


# -- rendering --------------------------------------------------------------


def test_the_rig_unit_renders_byte_for_byte_as_before() -> None:
    body = render_unit_file(
        "hammunition-rigctld",
        "hamlib rigctld for the station's rig",
        ("/usr/bin/rigctld", "-m", "1035"),
        "dev-x.device",
    )
    assert body == (
        "# Written by Hammunition (catalog unit `rig-service`, D-073).\n"
        "# Changed by `hammunition station set` then `hammunition install rig-service`;\n"
        "# removed by `hammunition uninstall rig-service`. Do not edit: a reinstall\n"
        "# replaces this file whole.\n"
        "[Unit]\nDescription=hamlib rigctld for the station's rig\n"
        "BindsTo=dev-x.device\nAfter=dev-x.device\n"
        "StartLimitIntervalSec=30\nStartLimitBurst=5\n\n"
        "[Service]\nExecStart=/usr/bin/rigctld -m 1035\nRestart=on-failure\nRestartSec=5\n"
        "NoNewPrivileges=yes\n\n[Install]\nWantedBy=default.target\nWantedBy=dev-x.device\n"
    )
    assert body.startswith(HEADER)


def test_a_plain_unit_names_itself_and_carries_its_restart_fields() -> None:
    body = render_unit_file(
        "hammunition-gps-tether",
        "GPS position",
        ("/usr/local/bin/hammunition-gps-tether",),
        None,
        unit="gps-tether",
        restart="always",
        restart_sec=9,
        station_fed=False,
    )
    lines = body.splitlines()
    assert lines[0] == "# Written by Hammunition (catalog unit `gps-tether`, D-073)."
    assert "station set" not in body and "rig-service" not in body
    assert "`hammunition install gps-tether`" in body
    assert "Restart=always" in lines and "RestartSec=9" in lines
    assert "BindsTo" not in body


def test_is_ours_recognises_any_unit_header_and_nothing_else() -> None:
    assert is_ours(header_for("gps-tether") + "\n[Unit]\n")
    assert is_ours(HEADER + "\n")
    assert not is_ours("[Unit]\nDescription=mine\n")
    assert not is_ours("# Written by Hammunition (catalog unit `gps-tether`")  # no closing
    assert not is_ours("# Written by someone else (catalog unit `x`, D-073).\n")


# -- planning ---------------------------------------------------------------


def test_a_plain_service_plans_with_no_station_and_no_hardware_catalog() -> None:
    manifest = _manifest("gps-tether", [_PLAIN])
    planned, deferrals, notes = plan_user_services(manifest, Station(), None)
    assert not deferrals and not notes
    (svc,) = planned
    assert svc.unit == "gps-tether"
    assert svc.exec_argv == ("/usr/local/bin/hammunition-gps-tether",)
    assert svc.device_path is None
    assert svc.filled_from == ()
    assert svc.listens == (("127.0.0.1", 10110), ("127.0.0.1", 10111))
    assert svc.unit_body.startswith(header_for("gps-tether"))
    assert "BindsTo" not in svc.unit_body


def test_several_plain_services_all_plan() -> None:
    second = {**_PLAIN, "name": "hammunition-other", "listens": []}
    manifest = _manifest("pair", [_PLAIN, second])
    planned, deferrals, _ = plan_user_services(manifest, Station(), None)
    assert not deferrals
    assert [p.name for p in planned] == ["hammunition-gps-tether", "hammunition-other"]
    assert {p.unit for p in planned} == {"pair"}


def test_a_mixed_manifest_plans_the_plain_entry_and_defers_the_rig_one() -> None:
    manifest = _manifest("mixed", [_PLAIN, _RIG])
    planned, deferrals, _ = plan_user_services(manifest, Station(), None)
    assert [p.name for p in planned] == ["hammunition-gps-tether"]
    (deferral,) = deferrals
    assert deferral.what == "will not run hammunition-rigctld"
    assert "rig" in deferral.why


def test_an_empty_when_station_means_always_for_a_rig_entry() -> None:
    from hammunition.manifest.load import load_hardware

    _classes, devices = load_hardware(
        Path(__file__).resolve().parent.parent / "catalog" / "hardware"
    )
    entry = {
        "name": "hammunition-anyrig",
        "description": "anyrig",
        "exec": ["/usr/bin/rigctld", "-r", "{station.rig_device}", "-T", "127.0.0.1", "-t", "4632"],
        "binds_to_device": "{station.rig_device}",
        "listens": [{"protocol": "tcp", "address": "127.0.0.1", "port": 4632}],
    }
    station = Station(rig="yaesu-ft-991a", rig_device="/dev/ttyUSB7", rig_baud=38400)
    planned, deferrals, _ = plan_user_services(_manifest("anyrig", [entry]), station, devices)
    assert not deferrals
    assert [p.name for p in planned] == ["hammunition-anyrig"]


def test_a_rig_entry_without_the_hardware_catalog_defers_by_name() -> None:
    planned, deferrals, _ = plan_user_services(_manifest("m", [_RIG]), Station(rig="x"), None)
    assert not planned
    (deferral,) = deferrals
    assert "hardware catalog" in deferral.why


# -- removal ----------------------------------------------------------------


def test_removal_takes_a_non_rig_unit_whose_header_names_it(tmp_path: Path) -> None:
    unit_dir = tmp_path / "systemd" / "user"
    unit_dir.mkdir(parents=True)
    path = unit_dir / "hammunition-gps-tether.service"
    path.write_text(header_for("gps-tether") + "\n[Service]\n")
    steps = user_service_removal_steps(["hammunition-gps-tether"], home=tmp_path)
    for step in steps:
        if isinstance(step, Action):
            step.perform()
    assert not path.exists()


def test_removal_leaves_a_unit_the_operator_rewrote(tmp_path: Path) -> None:
    unit_dir = tmp_path / "systemd" / "user"
    unit_dir.mkdir(parents=True)
    path = unit_dir / "hammunition-gps-tether.service"
    path.write_text("[Service]\nExecStart=/bin/true\n")
    for step in user_service_removal_steps(["hammunition-gps-tether"], home=tmp_path):
        if isinstance(step, Action):
            step.perform()
    assert path.exists()


# -- the plan view ----------------------------------------------------------


def _view_text(*services: Any) -> tuple[Any, str]:
    import dataclasses

    from hammunition.interface.envelope import target_view
    from hammunition.interface.plan import build_install_view, render_plan_view
    from test_json_plan import rich_plan

    plan, _commands = rich_plan()
    plan = dataclasses.replace(plan, user_services=tuple(services))
    view = build_install_view(plan, [], euid=1000)
    return view, "\n".join(render_plan_view(view, target=target_view(plan.target)))


def test_the_plan_names_each_services_own_unit_and_says_only_what_is_true() -> None:
    manifest = _manifest("gps-tether", [_PLAIN])
    (svc,) = plan_user_services(manifest, Station(), None)[0]
    view, text = _view_text(svc)
    (line,) = view.user_services
    assert line.unit == "gps-tether" and line.name == "hammunition-gps-tether"
    assert line.listen == "127.0.0.1:10110, 127.0.0.1:10111"
    assert line.starts_now is False
    assert "gps-tether: hammunition-gps-tether" in text
    assert "reverse  hammunition uninstall gps-tether" in text
    # What is true of the tether, not of a rig.
    assert "transmitter" not in text
    assert "rigctld" not in text
    assert "starts at your next login" in text
    assert "port appears" not in text


def test_a_rig_service_still_carries_the_transmitter_warning() -> None:
    from hammunition.manifest.load import load_catalog, load_hardware

    root = Path(__file__).resolve().parent.parent
    _classes, devices = load_hardware(root / "catalog" / "hardware")
    station = Station(rig="yaesu-ft-991a", rig_device="/dev/ttyUSB7", rig_baud=38400)
    planned, _d, _n = plan_user_services(
        load_catalog(root / "catalog" / "packages")["rig-service"], station, devices
    )
    _view, text = _view_text(*planned)
    assert "can key the transmitter" in text
    assert "rig-service: hammunition-rigctld" in text


# -- {user_bin}: the operator's ~/.local/bin, where a venv's wrapper lands --


def test_user_bin_fills_the_operators_bin_directory() -> None:
    entry = {**_PLAIN, "exec": ["{user_bin}/hammunition-gps-tether"]}
    manifest = _manifest("gps-tether", [entry])
    (svc,) = manifest.user_services
    assert svc.is_plain  # a placeholder for a directory is not a station value
    planned, deferrals, _ = plan_user_services(
        manifest, Station(), None, user_bin=Path("/home/op/.local/bin")
    )
    assert not deferrals
    assert planned[0].exec_argv == ("/home/op/.local/bin/hammunition-gps-tether",)
    assert "ExecStart=/home/op/.local/bin/hammunition-gps-tether\n" in planned[0].unit_body


def test_user_bin_is_allowed_only_at_the_start_of_the_program_word() -> None:
    entry = {**_PLAIN, "exec": ["/usr/bin/env", "{user_bin}/x"]}
    # as an argument it is allowed (it is one safe word), as exec[0] it is the program
    _manifest("gps-tether", [entry])
    with pytest.raises((ValidationError, ManifestError)):
        _manifest("gps-tether", [{**_PLAIN, "exec": ["x{user_bin}/y"]}])


# -- review fixes ------------------------------------------------------------


def test_a_plain_service_is_try_restarted_so_an_upgrade_reaches_a_running_one(
    tmp_path: Path,
) -> None:
    from dataclasses import dataclass

    from hammunition.backends import Command
    from hammunition.execute import user_service_steps

    @dataclass
    class _Plan:
        user_services: tuple[Any, ...]

    manifest = _manifest("gps-tether", [_PLAIN])
    planned, _d, _n = plan_user_services(manifest, Station(), None, user_bin=tmp_path)
    steps = user_service_steps(_Plan(tuple(planned)), home=tmp_path)  # type: ignore[arg-type]
    argvs = [s.argv for s in steps if isinstance(s, Command)]
    assert ("systemctl", "--user", "try-restart", "hammunition-gps-tether.service") in argvs
    # never a plain restart: a stopped service stays stopped until login
    assert ("systemctl", "--user", "restart", "hammunition-gps-tether.service") not in argvs


def test_the_rigs_proxy_is_still_never_restarted_without_its_device(tmp_path: Path) -> None:
    """The rig group's behaviour is unchanged: no device path, no restart step."""
    from dataclasses import dataclass

    from hammunition.backends import Command
    from hammunition.execute import user_service_steps
    from hammunition.userservice import PlannedUserService

    @dataclass
    class _Plan:
        user_services: tuple[Any, ...]

    svc = PlannedUserService(
        name="hammunition-rig-proxy",
        description="d",
        exec_argv=("/p",),
        unit_body=HEADER + "\n",
        device_path=None,
        filled_from=("rig",),
        listens=(),
    )
    argvs = [
        s.argv
        for s in user_service_steps(_Plan((svc,)), home=tmp_path)
        if isinstance(s, Command)  # type: ignore[arg-type]
    ]
    assert not any("restart" in a or "try-restart" in a for a in argvs)


def test_a_home_the_unit_file_cannot_carry_defers_the_service_instead_of_crashing() -> None:
    entry = {**_PLAIN, "exec": ["{user_bin}/hammunition-gps-tether"]}
    planned, deferrals, _ = plan_user_services(
        _manifest("gps-tether", [entry]), Station(), None, user_bin=Path("/home/a b/.local/bin")
    )
    assert not planned
    (deferral,) = deferrals
    assert deferral.subject == "gps-tether"
    assert deferral.what == "will not run hammunition-gps-tether"
    assert "whitespace" in deferral.why or "shell character" in deferral.why
