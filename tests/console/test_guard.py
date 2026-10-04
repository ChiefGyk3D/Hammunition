# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later
import pytest

from hammunition.console import guard
from hammunition.console.guard import Refused

APT = "sudo env DEBIAN_FRONTEND=noninteractive apt-get install --yes --only-upgrade --no-remove -- a b"


@pytest.mark.parametrize(
    "bad",
    [
        ["hammunition", "install", "x", "--yes"],
        ["hammunition", "install", "-y"],
        ["hammunition", "install", "--yes=1"],
    ],
)
def test_assume_yes_in_any_spelling_is_refused(bad: list[str]) -> None:
    with pytest.raises(Refused, match="never passes"):
        guard.checked_argv(bad)


@pytest.mark.parametrize(
    "ok",
    [
        ["hammunition", "install", "station"],
        ["hammunition", "uninstall", "station"],
        ["hammunition", "station", "set", "--callsign=N0CALL"],
        ["hammunition", "hardware", "apply"],
        ["/usr/bin/hammunition", "install", "station"],
    ],
)
def test_the_commands_the_console_runs_pass(ok: list[str]) -> None:
    assert guard.checked_argv(ok) == ok


@pytest.mark.parametrize(
    "bad",
    [
        [],
        ["rm", "-rf", "/"],
        ["hammunition"],
        ["hammunition", "doctor"],
        ["hammunition", "services", "start", "gpsd"],
        ["sudo", "rm", "x"],
        ["sudo", "apt-get", "remove", "x"],
        ["bash", "-c", "hammunition install x"],
    ],
)
def test_anything_else_is_refused(bad: list[str]) -> None:
    with pytest.raises(Refused):
        guard.checked_argv(bad)


def test_a_value_that_merely_contains_the_word_is_not_the_flag() -> None:
    argv = ["hammunition", "station", "set", "--callsign=--yes"]
    assert guard.checked_argv(argv) == argv


def test_the_environment_is_scrubbed_of_every_consent_variable() -> None:
    env = {
        "PATH": "/bin",
        "HAMMUNITION_ACCEPT_RF_RESEARCH": "1",
        "HAMMUNITION_ACCEPT_APT_REPO_KISMET_TRIXIE": "AB",
        "MY_CONSENT": "1",
        "HAMMUNITION_CATALOG": "/c",
        "HOME": "/h",
    }
    assert guard.scrubbed_environ(env) == {
        "PATH": "/bin",
        "HAMMUNITION_CATALOG": "/c",
        "HOME": "/h",
    }


def test_apt_upgrade_command_is_reduced_to_a_pane_argv_without_the_assume_yes() -> None:
    argv = guard.apt_upgrade_argv(APT)
    assert argv == ["sudo", "apt-get", "install", "--only-upgrade", "--no-remove", "--", "a", "b"]
    assert argv is not None and guard.checked_argv(argv) == argv


@pytest.mark.parametrize(
    "bad",
    [
        None,
        "",
        "sudo apt-get install -- a",
        "sudo env DEBIAN_FRONTEND=noninteractive apt-get install --yes --only-upgrade --no-remove --",
        APT + " ; rm -rf /",
        APT + " $(id)",
        APT + " --purge",
        "hammunition install a",
    ],
)
def test_an_unexpected_apt_command_shape_is_not_runnable(bad: str | None) -> None:
    assert guard.apt_upgrade_argv(bad) is None


def test_reads_refuse_a_forbidden_word() -> None:
    with pytest.raises(Refused):
        guard.assert_clean_read(["install", "x", "--dry-run", "-y"])
    guard.assert_clean_read(["install", "x", "--dry-run"])
