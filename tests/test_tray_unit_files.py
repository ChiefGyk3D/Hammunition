# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""The tray units install the helper's wrapper and polkit action.  D-056 amended 2026-10-02.

The helper lives in hammunition-tray now, so the catalog units that install the
tray also write the two root files that make it reachable: a fixed-path wrapper
(the path polkit names) and the polkit action. Both are `config_files`, so the
plan discloses them like any other root file.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from hammunition.hardware.polkit import ACTION_ID, HELPER_PATH, POLICY_PATH, policy_xml
from hammunition.manifest.load import load_catalog
from hammunition.manifest.schema import ConfigFile, PackageManifest

CATALOG = Path(__file__).resolve().parent.parent / "catalog"
UNITS = ("hammunition-tray", "hammunition-tray-qt")


@pytest.fixture(scope="module")
def packages() -> dict[str, PackageManifest]:
    return load_catalog(CATALOG / "packages")


def _files(packages: dict[str, PackageManifest], unit: str) -> dict[str, ConfigFile]:
    return {c.path: c for c in packages[unit].config_files}


@pytest.mark.parametrize("unit", UNITS)
def test_each_tray_unit_writes_the_wrapper_and_the_action(
    packages: dict[str, PackageManifest], unit: str
) -> None:
    files = _files(packages, unit)
    assert set(files) == {HELPER_PATH, POLICY_PATH}
    assert files[HELPER_PATH].mode == "0755"
    assert files[POLICY_PATH].mode == "0644"


@pytest.mark.parametrize("unit", UNITS)
def test_the_action_is_the_one_the_engine_writes(
    packages: dict[str, PackageManifest], unit: str
) -> None:
    """One polkit action, one file: the unit's copy and the engine's own may never drift."""
    template = _files(packages, unit)[POLICY_PATH].template
    assert template == policy_xml()
    assert ACTION_ID in template
    assert f'key="org.freedesktop.policykit.exec.path">{HELPER_PATH}<' in template


@pytest.mark.parametrize("unit", UNITS)
def test_the_wrapper_runs_the_trays_script_isolated_and_from_root(
    packages: dict[str, PackageManifest], unit: str
) -> None:
    text = _files(packages, unit)[HELPER_PATH].template
    lines = [line.strip() for line in text.splitlines()]
    assert lines[0] == "#!/bin/sh"
    assert "cd /" in lines
    # -I is load-bearing (the engine's wrapper says why): no cwd, no PYTHONPATH, no user site.
    assert 'exec /usr/bin/python3 -I /usr/bin/hammunition-devctl "$@"' in lines
    assert " -m " not in text  # never `python -m <module>`: that puts the cwd on sys.path
    assert "hammunition.cli.devctl" not in text  # the engine's module is not what this runs


@pytest.mark.parametrize("unit", UNITS)
def test_a_missing_script_is_reported_not_exec_d_blind(
    packages: dict[str, PackageManifest], unit: str
) -> None:
    text = _files(packages, unit)[HELPER_PATH].template
    assert "[ -x /usr/bin/hammunition-devctl ]" in text
    assert "exit 2" in text


@pytest.mark.parametrize("unit", UNITS)
def test_neither_file_takes_a_station_value(
    packages: dict[str, PackageManifest], unit: str
) -> None:
    for config in _files(packages, unit).values():
        assert "{station." not in config.template


def test_the_two_units_write_identical_files(packages: dict[str, PackageManifest]) -> None:
    """Both can be installed on one machine; a second identical write is a no-op."""
    first, second = (_files(packages, u) for u in UNITS)
    for path in first:
        assert first[path].template == second[path].template
        assert first[path].mode == second[path].mode
