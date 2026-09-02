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
