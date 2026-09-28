# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""The health check is a pure function, so it is tested as one.

Each test fixes one input and asserts the verdict and severity for it, because
the severity distinction (fail blocks, warn limits, info states) is the whole
value of the command.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from hammunition.doctor import Check, run_checks, summarize, writable_or_creatable

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


def test_hammunition_from_another_checkout_is_a_warn_with_the_switch() -> None:
    other = "/home/op/Hammunition-old/.venv/bin/hammunition"
    checks = run_checks(**{**HEALTHY, "engine_on_path": other})  # type: ignore[arg-type]
    check = _by_name(checks)["hammunition"]
    assert check.status == "warn" and other in check.detail
    assert check.fix == f"ln -sfn {HEALTHY['engine_expected']} ~/.local/bin/hammunition"


def test_hammunition_resolving_to_this_checkout_is_ok() -> None:
    assert _by_name(run_checks(**HEALTHY))["hammunition"].status == "ok"  # type: ignore[arg-type]
