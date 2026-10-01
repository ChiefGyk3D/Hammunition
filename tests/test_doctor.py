# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""The health check is a pure function, so it is tested as one.

Each test fixes one input and asserts the verdict and severity for it, because
the severity distinction (fail blocks, warn limits, info states) is the whole
value of the command.
"""

from __future__ import annotations

import os
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from hammunition.doctor import Check, run_checks, summarize, writable_or_creatable
from hammunition.gpstime.state import TimeState

HEALTHY: dict[str, object] = {
    "target_describe": "Parrot Security 7.3",
    "is_debian_family": True,
    "catalog_counts": (242, 15),
    "has_venv_module": True,
    "path_has_local_bin": True,
    "tools": {"cc": True, "git": True},
    "groups_now": frozenset({"plugdev", "dialout"}),
    "needed_groups": ["dialout", "plugdev"],
    "station_set": True,
    "rules_applied": True,
    "attached_recognised": 1,
    "log_dir_writable": True,
    "engine_on_path": "/home/op/Hammunition/.venv/bin/hammunition",
    "engine_expected": "/home/op/Hammunition/.venv/bin/hammunition",
    "engine_found": "/home/op/.local/bin/hammunition",
    "engine_found_in_local_bin": True,
    "engine_found_link": "/home/op/Hammunition/.venv/bin/hammunition",
}


def _by_name(checks: list[Check]) -> dict[str, Check]:
    return {c.name: c for c in checks}


def test_a_healthy_machine_has_no_fails_or_warns() -> None:
    checks = run_checks(**HEALTHY)  # type: ignore[arg-type]
    fails, warns, healthy = summarize(checks)
    assert fails == 0 and warns == 0
    assert healthy == len(checks)


def test_a_non_debian_system_is_a_blocking_fail() -> None:
    checks = run_checks(**{**HEALTHY, "is_debian_family": False, "target_describe": "Fedora 42"})  # type: ignore[arg-type]
    system = _by_name(checks)["system"]
    assert system.status == "fail"
    assert summarize(checks)[0] == 1


def test_no_catalog_is_a_blocking_fail() -> None:
    checks = run_checks(**{**HEALTHY, "catalog_counts": None})  # type: ignore[arg-type]
    assert _by_name(checks)["catalog"].status == "fail"


def test_missing_venv_is_a_warn_with_the_apt_fix() -> None:
    checks = run_checks(**{**HEALTHY, "has_venv_module": False})  # type: ignore[arg-type]
    venv = _by_name(checks)["python venv"]
    assert venv.status == "warn"
    assert venv.fix is not None and "python3-venv" in venv.fix


def test_unset_station_is_a_warn_not_a_fail() -> None:
    checks = run_checks(**{**HEALTHY, "station_set": False})  # type: ignore[arg-type]
    assert _by_name(checks)["station"].status == "warn"
    assert summarize(checks)[0] == 0  # the engine still works


def test_missing_groups_are_named() -> None:
    checks = run_checks(**{**HEALTHY, "groups_now": frozenset({"plugdev"})})  # type: ignore[arg-type]
    groups = _by_name(checks)["device groups"]
    assert groups.status == "warn"
    assert "dialout" in groups.detail and "plugdev" not in groups.detail


def test_unapplied_udev_is_info_not_warn() -> None:
    checks = run_checks(**{**HEALTHY, "rules_applied": False})  # type: ignore[arg-type]
    assert _by_name(checks)["udev rules"].status == "info"
    # info never contributes to the blocking or warning counts
    assert summarize(checks)[:2] == (0, 0)


def test_a_readonly_state_dir_warns() -> None:
    checks = run_checks(**{**HEALTHY, "log_dir_writable": False})  # type: ignore[arg-type]
    assert _by_name(checks)["state dir"].status == "warn"


def test_a_state_dir_whose_ancestors_do_not_exist_yet_is_creatable(tmp_path: Path) -> None:
    # A fresh account: ~/.local does not exist, let alone ~/.local/state/hammunition.
    assert writable_or_creatable(tmp_path / ".local" / "state" / "hammunition")


@pytest.mark.skipif(
    os.geteuid() == 0,
    reason="root writes through a 0o500 directory; the CI containers run the suite as root",
)
def test_a_state_dir_under_a_readonly_ancestor_is_not(tmp_path: Path) -> None:
    locked = tmp_path / "locked"
    locked.mkdir()
    locked.chmod(0o500)
    try:
        assert not writable_or_creatable(locked / "state" / "hammunition")
    finally:
        locked.chmod(0o700)


def test_doctor_reports_kept_devices_as_info() -> None:
    checks = run_checks(**HEALTHY, kept_attached=("gps-receiver@3-5.1",))  # type: ignore[arg-type]
    kept = [c for c in checks if c.name == "kept off"]
    assert kept and kept[0].status == "info"
    assert "gps-receiver@3-5.1" in kept[0].detail


def test_doctor_warns_about_a_kept_entry_with_nothing_attached() -> None:
    checks = run_checks(**HEALTHY, kept_absent=("gps-receiver@3-6",))  # type: ignore[arg-type]
    kept = [c for c in checks if c.name == "kept off"]
    assert kept and kept[0].status == "warn"
    assert "hammunition hardware wake gps-receiver@3-6" in (kept[0].fix or "")


def test_doctor_says_nothing_about_kept_when_none_is_kept() -> None:
    assert not [c for c in run_checks(**HEALTHY) if c.name == "kept off"]  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Desktops (D-060): what the session files offer, and the session's own
# ---------------------------------------------------------------------------


def _with(**extra: object) -> list[Check]:
    return run_checks(**{**HEALTHY, **extra})  # type: ignore[arg-type]


def test_desktops_are_reported_from_session_files_and_the_session() -> None:
    from hammunition.desktop import Desktop

    checks = _with(
        desktops_installed=frozenset({Desktop.kde, Desktop.xfce}), desktop_current=Desktop.kde
    )
    desktops = _by_name(checks)["desktops"]
    assert desktops.status == "info"
    assert desktops.detail == "session files offer KDE Plasma, Xfce; this session is KDE Plasma"


def test_an_unknown_session_says_why_it_is_unknown() -> None:
    """Under sudo XDG_CURRENT_DESKTOP is usually gone; say so rather than guess."""
    from hammunition.desktop import Desktop

    checks = _with(desktops_installed=frozenset({Desktop.xfce}), desktop_current=None)
    detail = _by_name(checks)["desktops"].detail
    assert detail.startswith("session files offer Xfce; this session's desktop is not known")
    assert "XDG_CURRENT_DESKTOP" in detail and "sudo" in detail


def test_no_session_files_is_information_naming_what_it_defers() -> None:
    checks = _with(desktops_installed=frozenset(), desktop_current=None)
    desktops = _by_name(checks)["desktops"]
    assert desktops.status == "info"
    assert "no desktop session files" in desktops.detail
    assert "deferred from a profile and refused by name" in desktops.detail


def test_session_files_naming_no_known_desktop_are_not_a_server() -> None:
    """A COSMIC or Sway machine is graphical. ASSUMPTION, not measured: COSMIC's
    session file is `cosmic.desktop` with `DesktopNames=COSMIC`."""
    checks = _with(
        desktops_installed=frozenset(),
        sessions_unrecognised=("cosmic.desktop",),
        desktop_current=None,
    )
    detail = _by_name(checks)["desktops"].detail
    assert "server" not in detail and "container" not in detail
    assert "none of the desktops the catalog knows (read: cosmic.desktop)" in detail


def test_unrecognised_files_beside_known_desktops_are_named() -> None:
    from hammunition.desktop import Desktop

    checks = _with(
        desktops_installed=frozenset({Desktop.xfce}),
        sessions_unrecognised=("sway.desktop",),
        desktop_current=Desktop.xfce,
    )
    assert _by_name(checks)["desktops"].detail == (
        "session files offer Xfce; also sway.desktop, which names no desktop the catalog "
        "knows; this session is Xfce"
    )


def test_desktops_not_read_add_no_check() -> None:
    assert "desktops" not in _by_name(run_checks(**HEALTHY))  # type: ignore[arg-type]


def test_hammunition_missing_from_path_is_a_warn_naming_bootstrap() -> None:
    checks = run_checks(**{**HEALTHY, "engine_on_path": None})  # type: ignore[arg-type]
    check = _by_name(checks)["hammunition"]
    assert check.status == "warn"
    assert check.fix is not None and "bootstrap.sh" in check.fix


def test_our_link_with_local_bin_off_path_says_log_in_again_not_bootstrap() -> None:
    """Final review I2: a fresh account gets the link from bootstrap before
    ~/.local/bin reaches PATH. Re-running bootstrap changes nothing then."""
    checks = run_checks(
        **{  # type: ignore[arg-type]
            **HEALTHY,
            "engine_on_path": None,
            "engine_found": None,
            "engine_found_link": None,
            "engine_found_in_local_bin": False,
            "path_has_local_bin": False,
            "engine_linked_in_local_bin": True,
        }
    )
    check = _by_name(checks)["hammunition"]
    assert check.status == "warn"
    assert check.fix is not None
    assert "log out and back in" in check.fix
    assert 'export PATH="$HOME/.local/bin:$PATH"' in check.fix
    assert "bootstrap" not in check.fix


def test_hammunition_from_another_checkout_is_a_warn_with_the_quoted_switch() -> None:
    # Plan-mandated test, amended in review (I1): the switch is offered only for
    # our own link, and both paths are shell-quoted so a space pastes correctly.
    other = "/home/op/Hammunition old/.venv/bin/hammunition"
    expected = "/home/op/My Radio/Hammunition/.venv/bin/hammunition"
    local = "/home/op/.local/bin/hammunition"
    checks = run_checks(
        **{  # type: ignore[arg-type]
            **HEALTHY,
            "engine_on_path": other,
            "engine_expected": expected,
            "engine_found_link": other,
        }
    )
    check = _by_name(checks)["hammunition"]
    assert check.status == "warn" and other in check.detail
    assert check.fix == f"ln -sfn '{expected}' {local}"


def test_a_foreign_file_in_local_bin_is_named_never_replaced() -> None:
    """A pipx install or a wrapper at ~/.local/bin/hammunition: no command that clobbers it."""
    local = "/home/op/.local/bin/hammunition"
    checks = run_checks(
        **{  # type: ignore[arg-type]
            **HEALTHY,
            "engine_on_path": local,
            "engine_found_link": None,
        }
    )
    check = _by_name(checks)["hammunition"]
    assert check.status == "warn" and local in check.detail
    assert check.fix is not None
    assert "ln " not in check.fix and "rm " not in check.fix and "mv " not in check.fix
    assert f"ls -l {local}" in check.fix


def test_a_foreign_symlink_in_local_bin_is_named_never_replaced() -> None:
    local = "/home/op/.local/bin/hammunition"
    checks = run_checks(
        **{  # type: ignore[arg-type]
            **HEALTHY,
            "engine_on_path": "/home/op/.local/share/pipx/venvs/x/bin/hammunition",
            "engine_found_link": "/home/op/.local/share/pipx/venvs/x/bin/hammunition",
        }
    )
    check = _by_name(checks)["hammunition"]
    assert check.status == "warn" and local in check.detail
    assert check.fix is not None and "ln " not in check.fix


def test_a_hammunition_earlier_on_path_is_named_and_relinking_is_not_offered() -> None:
    earlier = "/usr/local/bin/hammunition"
    checks = run_checks(
        **{  # type: ignore[arg-type]
            **HEALTHY,
            "engine_on_path": earlier,
            "engine_found": earlier,
            "engine_found_in_local_bin": False,
            "engine_found_link": None,
        }
    )
    check = _by_name(checks)["hammunition"]
    assert check.status == "warn"
    assert earlier in check.detail and "before ~/.local/bin" in check.detail
    assert check.fix is not None and "ln " not in check.fix and "bootstrap" not in check.fix


def test_hammunition_resolving_to_this_checkout_is_ok() -> None:
    assert _by_name(run_checks(**HEALTHY))["hammunition"].status == "ok"  # type: ignore[arg-type]


def test_qmapshack_without_routino_translations_warns_with_the_fix() -> None:
    """D-061: QMapShack stops at startup without routino-common's file."""
    checks = run_checks(**HEALTHY, qmapshack_without_translations=True)  # type: ignore[arg-type]
    (check,) = [c for c in checks if c.name == "qmapshack"]
    assert check.status == "warn"
    assert "/usr/share/routino/translations.xml" in check.detail
    assert check.fix == "sudo apt-get install --reinstall routino-common"
    assert not [c for c in run_checks(**HEALTHY) if c.name == "qmapshack"]  # type: ignore[arg-type]


TIME = TimeState(
    mode="auto",
    mode_set=False,
    daemon="ntpsec",
    gps="awake",
    following="network",
    offset_ms=-4.4,
    last_sync=datetime(2026, 9, 28, 14, 44, tzinfo=UTC),
    last_source="network",
    holdover_seconds=None,
    rtc=True,
    grants=True,
    dhcp_config=False,
    problems=(),
)


def _time_checks(**over: Any) -> list[Check]:
    checks = run_checks(**HEALTHY, time_state=replace(TIME, **over))  # type: ignore[arg-type]
    return [c for c in checks if c.name in ("time", "hardware clock")]


def test_the_followed_source_is_ok() -> None:
    [check] = _time_checks()
    assert check.status == "ok" and "the network" in check.detail and "-4.4 ms" in check.detail


def test_a_machine_without_an_rtc_is_warned_with_the_fix() -> None:
    clock = [c for c in _time_checks(rtc=False) if c.name == "hardware clock"]
    assert clock and clock[0].status == "warn"
    assert clock[0].fix is not None and "RTC" in clock[0].fix and "fake-hwclock" in clock[0].fix


def test_holdover_under_a_day_is_stated() -> None:
    [check] = _time_checks(following="none", holdover_seconds=7200)
    assert check.status == "info" and "2 h 0 min" in check.detail


def test_holdover_past_a_day_warns() -> None:
    [check] = _time_checks(following="none", holdover_seconds=187_200)
    assert check.status == "warn" and "2 d 4 h" in check.detail


def test_gps_only_with_the_receiver_parked_warns() -> None:
    [check] = _time_checks(mode="gps-only", gps="parked", following="none", holdover_seconds=60)
    assert check.status == "warn" and "parked" in check.detail
    assert check.fix is not None and "time mode auto" in check.fix


def test_never_synchronised_warns() -> None:
    [check] = _time_checks(following="none", last_sync=None, holdover_seconds=None)
    assert check.status == "warn"


def test_missing_grants_warn_with_hardware_apply() -> None:
    checks = _time_checks(grants=False)
    assert any(c.status == "warn" and c.fix == "hammunition hardware apply" for c in checks)


def test_a_target_without_ntpsec_is_stated_not_failed() -> None:
    [check] = _time_checks(daemon=None, following="unknown")
    assert check.status == "info" and "D-058" in check.detail


def test_no_time_state_adds_no_time_checks() -> None:
    assert [c for c in run_checks(**HEALTHY) if c.name == "time"] == []  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Issue #145: every generated launcher that runs the engine can reach it
# ---------------------------------------------------------------------------


def test_launchers_whose_engine_runs_are_ok() -> None:
    checks = _with(launchers_ok=("/home/op/.local/bin/qmapshack-offline",))
    check = _by_name(checks)["launchers"]
    assert check.status == "ok" and "1 launcher" in check.detail


def test_a_launcher_whose_engine_is_gone_warns_naming_it_and_the_fix() -> None:
    checks = _with(
        launchers_ok=("/home/op/.local/bin/gps-tether",),
        launchers_broken=(
            ("/home/op/.local/bin/qmapshack-offline", "/home/op/old/.venv/bin/hammunition"),
        ),
    )
    check = _by_name(checks)["launchers"]
    assert check.status == "warn"
    assert "/home/op/.local/bin/qmapshack-offline" in check.detail
    assert "/home/op/old/.venv/bin/hammunition" in check.detail
    assert check.fix is not None
    assert "./bootstrap.sh" in check.fix and "hammunition menus apply" in check.fix


def test_a_launcher_calling_the_engine_by_bare_name_warns_with_menus_apply() -> None:
    checks = _with(launchers_bare=("/home/op/.local/bin/gps-tether",))
    check = _by_name(checks)["launchers"]
    assert check.status == "warn"
    assert "/home/op/.local/bin/gps-tether" in check.detail and "not found" in check.detail
    assert check.fix is not None and "hammunition menus apply" in check.fix


def test_a_launcher_shadowing_a_path_binary_warns_naming_both_and_the_fix() -> None:
    """Issue #174: ``~/.local/bin/rigctl`` ran ahead of hamlib's ``/usr/bin/rigctl``."""
    checks = _with(
        launchers_ok=("/home/op/.local/bin/qmapshack-offline",),
        launchers_shadowing=(("/home/op/.local/bin/rigctl", "/usr/bin/rigctl"),),
    )
    check = _by_name(checks)["launchers"]
    assert check.status == "warn"
    assert "/home/op/.local/bin/rigctl" in check.detail and "/usr/bin/rigctl" in check.detail
    assert check.fix is not None and "hammunition menus apply" in check.fix


def test_no_engine_launchers_adds_no_check() -> None:
    assert "launchers" not in _by_name(run_checks(**HEALTHY))  # type: ignore[arg-type]


# --- rig checks (D-073 §9) ---------------------------------------------------


def test_rig_checks_report_a_missing_value() -> None:
    from hammunition.doctor import RigStatus, rig_checks

    checks = rig_checks(RigStatus(configured=True, missing=("rig_device",), kind="cat"))
    assert any(c.name == "rig" and c.status == "warn" and "rig_device" in c.detail for c in checks)


def test_rig_checks_are_quiet_when_nothing_is_set() -> None:
    from hammunition.doctor import RigStatus, rig_checks

    checks = rig_checks(RigStatus(configured=False))
    assert len(checks) == 1 and checks[0].status == "info"


def test_rig_checks_healthy_when_active_and_answering() -> None:
    from hammunition.doctor import RigStatus, rig_checks

    checks = rig_checks(
        RigStatus(configured=True, kind="cat", service_state="active", answering=True)
    )
    assert any(c.status == "ok" and "active" in c.detail for c in checks)
    assert any(c.status == "ok" and "answers" in c.detail for c in checks)


def test_rig_checks_flag_an_argument_mismatch() -> None:
    from hammunition.doctor import RigStatus, rig_checks

    checks = rig_checks(
        RigStatus(configured=True, kind="cat", service_state="active", args_match=False)
    )
    assert any("do not match" in c.detail and c.status == "warn" for c in checks)


def test_rig_checks_never_key() -> None:
    # The checks describe only reads; none names a keying command.
    from hammunition.doctor import RigStatus, rig_checks

    checks = rig_checks(
        RigStatus(configured=True, kind="ptt_only", service_state="active", answering=True)
    )
    for c in checks:
        assert "set_ptt" not in (c.fix or "") and "\\set" not in (c.fix or "")


def test_rig_checks_do_not_warn_install_for_an_flrig_station() -> None:
    """Review I5: flrig runs no rigctld service, so doctor must not tell the
    operator to install one — that fix would do nothing."""
    from hammunition.doctor import RigStatus, rig_checks

    checks = rig_checks(RigStatus(configured=True, kind="cat", owner="flrig", service_state="absent"))
    assert not any(c.status == "warn" for c in checks)
    assert any("flrig" in c.detail for c in checks)


def test_rig_checks_do_not_warn_install_for_a_vox_station() -> None:
    from hammunition.doctor import RigStatus, rig_checks

    checks = rig_checks(
        RigStatus(configured=True, kind="ptt_only", vox=True, service_state="absent")
    )
    assert not any(c.status == "warn" for c in checks)
    assert any("VOX" in c.detail for c in checks)


def test_rig_checks_flag_a_missing_proxy() -> None:
    from hammunition.doctor import RigStatus, rig_checks

    checks = rig_checks(
        RigStatus(configured=True, kind="cat", service_state="active", proxy_state="absent")
    )
    assert any("filter" in c.detail and c.status == "warn" for c in checks)


def test_rig_checks_fail_when_4532_is_not_loopback_only() -> None:
    from hammunition.doctor import RigStatus, rig_checks

    checks = rig_checks(
        RigStatus(configured=True, kind="cat", service_state="active", loopback_only=False)
    )
    assert any(c.status == "fail" for c in checks)
