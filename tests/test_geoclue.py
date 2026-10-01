# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""GeoClue fed by the GPS tether: the two root files `hardware apply` writes.  D-069.

Every path is under the test's tmp_path (the `geoclue_files` fixture); no test
reads the real /etc/geoclue or /run, and none starts a GeoClue.
"""

from __future__ import annotations

import grp
import os
import pwd
import stat
from pathlib import Path

import pytest

from hammunition import geoclue
from hammunition.backends.base import Command, CommandResult
from hammunition.geoclue import (
    DISCLOSURES,
    GeoClueError,
    GeoClueRemoval,
    agent_running,
    configured,
    disclose,
    dropin_content,
    grant_commands,
    plan_geoclue,
    plan_geoclue_removal,
    read_state,
    removal_commands,
    stage_grants,
    tmpfiles_content,
    verify_grants,
    verify_removal,
)

ME = pwd.getpwuid(os.getuid()).pw_name
MY_GROUP = grp.getgrgid(os.getgid()).gr_name


def _argv(commands: list[Command]) -> list[str]:
    return [" ".join(c.argv) for c in commands]


def _make_dir(mode: int = 0o2750) -> Path:
    directory = Path(geoclue.SOCKET_DIR)
    directory.mkdir(parents=True)
    directory.chmod(mode)
    return directory


def _install_both(operator: str = ME) -> None:
    for path, text in (
        (geoclue.DROPIN, dropin_content()),
        (geoclue.TMPFILES, tmpfiles_content(operator)),
    ):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(text)


# ------------------------------------------------------------------ the text


def test_the_dropin_is_the_spikes_three_lines_under_our_header() -> None:
    text = dropin_content(geoclue.PATHS["SOCKET"])
    body = [line for line in text.splitlines() if line and not line.startswith("#")]
    assert body == [
        "[network-nmea]",
        "enable=true",
        "nmea-socket=/run/hammunition-gps/nmea.sock",
    ]
    assert text.startswith(geoclue.HEADER)
    assert "[app." not in text, "a native CoMaps is a system app and needs no app entry"


def test_the_real_paths_are_the_spikes() -> None:
    assert geoclue.PATHS == {
        "DAEMON": "/usr/libexec/geoclue",
        "DROPIN": "/etc/geoclue/conf.d/90-hammunition-gps.conf",
        "TMPFILES": "/etc/tmpfiles.d/hammunition-gps.conf",
        "SOCKET_DIR": "/run/hammunition-gps",
        "SOCKET": "/run/hammunition-gps/nmea.sock",
    }


def test_the_tmpfiles_line_is_setgid_operator_and_geoclue() -> None:
    text = tmpfiles_content("op", directory="/run/hammunition-gps", group="geoclue")
    lines = [line for line in text.splitlines() if line and not line.startswith("#")]
    assert lines == ["d /run/hammunition-gps 2750 op geoclue -"]
    assert text.startswith(geoclue.HEADER)


@pytest.mark.parametrize("name", ["", "a b", "root\nd /etc 0777", "-x", "x/y", "é"])
def test_an_operator_name_that_is_not_one_is_refused(name: str) -> None:
    with pytest.raises(GeoClueError, match="operator"):
        tmpfiles_content(name)


# ------------------------------------------------------------------ planning


def test_without_geoclue_installed_nothing_is_planned() -> None:
    plan = plan_geoclue(ME)
    assert not plan.installed and plan.is_noop
    assert grant_commands(plan, "<staging>") == []
    assert any("not installed" in line for line in disclose(plan))


def test_without_the_geoclue_group_nothing_is_planned(
    geoclue_files: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(geoclue, "GROUP", "no-such-group-hammunition-test")
    plan = plan_geoclue(ME)
    assert not plan.installed and plan.is_noop
    assert any("no-such-group-hammunition-test" in line for line in disclose(plan))


def test_a_fresh_machine_plans_both_files_the_directory_and_a_restart(
    geoclue_files: Path,
) -> None:
    plan = plan_geoclue(ME)
    assert plan.installed and not plan.is_noop
    assert _argv(grant_commands(plan, "/stage")) == [
        f"install -D -m 0644 /stage/geoclue-90-hammunition-gps.conf {geoclue.DROPIN}",
        f"install -D -m 0644 /stage/tmpfiles-hammunition-gps.conf {geoclue.TMPFILES}",
        f"systemd-tmpfiles --create {geoclue.TMPFILES}",
        "systemctl try-restart geoclue",
    ]
    assert all(c.requires_root for c in grant_commands(plan, "/stage"))


def test_everything_in_place_is_a_noop(geoclue_files: Path) -> None:
    _install_both()
    _make_dir()
    plan = plan_geoclue(ME)
    assert plan.is_noop
    assert grant_commands(plan, "/stage") == []


def test_a_directory_with_the_wrong_mode_is_put_right_by_tmpfiles_alone(
    geoclue_files: Path,
) -> None:
    _install_both()
    _make_dir(0o755)
    plan = plan_geoclue(ME)
    assert _argv(grant_commands(plan, "/stage")) == [
        f"systemd-tmpfiles --create {geoclue.TMPFILES}"
    ]


def test_another_operator_rewrites_our_tmpfiles_line(geoclue_files: Path) -> None:
    _install_both(operator="someone-else")
    _make_dir()
    plan = plan_geoclue(ME)
    assert not plan.tmpfiles_current
    assert f"systemd-tmpfiles --create {geoclue.TMPFILES}" in _argv(grant_commands(plan, "/s"))


@pytest.mark.parametrize("which", ["DROPIN", "TMPFILES"])
def test_a_file_hammunition_did_not_write_is_refused_never_overwritten(
    geoclue_files: Path, which: str
) -> None:
    path = Path(getattr(geoclue, which))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("[network-nmea]\nenable=false\n")
    with pytest.raises(GeoClueError, match="--no-geoclue"):
        plan_geoclue(ME)


def test_a_symlink_in_place_of_the_directory_is_refused(
    geoclue_files: Path, tmp_path: Path
) -> None:
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    Path(geoclue.SOCKET_DIR).parent.mkdir(parents=True)
    Path(geoclue.SOCKET_DIR).symlink_to(elsewhere)
    with pytest.raises(GeoClueError, match="not a directory"):
        plan_geoclue(ME)


def test_an_unknown_operator_is_refused(geoclue_files: Path) -> None:
    with pytest.raises(GeoClueError, match="no account"):
        plan_geoclue("no-such-user-hammunition-test")


# ------------------------------------------------------------------ disclosure


def test_the_disclosure_prints_both_files_inspect_and_reverse_steps(
    geoclue_files: Path,
) -> None:
    text = " ".join(" ".join(disclose(plan_geoclue(ME))).split())
    assert geoclue.DROPIN in text and geoclue.TMPFILES in text
    assert "nmea-socket=" in text and f"2750 {ME} {MY_GROUP}" in text
    for step in (
        f"cat {geoclue.DROPIN} {geoclue.TMPFILES}",
        f"ls -ld {geoclue.SOCKET_DIR}",
        "journalctl -u geoclue | grep -i nmea",
        f"rmdir {geoclue.SOCKET_DIR}",
        "systemctl try-restart geoclue",
        "--no-geoclue",
        "hardware unapply",
    ):
        assert step in text, step


def test_the_disclosure_carries_every_sentence_the_spike_names(geoclue_files: Path) -> None:
    text = " ".join(" ".join(disclose(plan_geoclue(ME))).split())
    assert len(DISCLOSURES) == 4
    for sentence in DISCLOSURES:
        assert sentence in text, sentence
    joined = " ".join(DISCLOSURES)
    for words in (
        "60 s",
        "try-restart",
        "Flatpak",
        "does not prompt",
        "beacondb",
        "GeoIP",
        "[static-source]",
        "qtposition-geoclue2",
    ):
        assert words in joined, words


# ------------------------------------------------------------------ staging, verifying


def test_staging_writes_the_two_files_apply_installs(geoclue_files: Path, tmp_path: Path) -> None:
    stage = tmp_path / "stage"
    stage.mkdir()
    plan = plan_geoclue(ME)
    stage_grants(plan, stage)
    assert (stage / "geoclue-90-hammunition-gps.conf").read_text() == dropin_content()
    assert (stage / "tmpfiles-hammunition-gps.conf").read_text() == tmpfiles_content(ME)
    assert stat.S_IMODE((stage / "tmpfiles-hammunition-gps.conf").stat().st_mode) == 0o644


def test_verify_names_each_thing_that_did_not_land(geoclue_files: Path) -> None:
    plan = plan_geoclue(ME)
    problems = verify_grants(plan)
    assert any(geoclue.DROPIN in p for p in problems)
    assert any(geoclue.TMPFILES in p for p in problems)
    assert any(geoclue.SOCKET_DIR in p for p in problems)
    _install_both()
    _make_dir()
    assert verify_grants(plan) == []


def test_verify_says_what_is_wrong_with_the_directory(geoclue_files: Path) -> None:
    _install_both()
    _make_dir(0o750)
    problems = verify_grants(plan_geoclue(ME))
    assert problems and "2750" in problems[0] and "0750" in problems[0]


# ------------------------------------------------------------------ the marker


def test_the_tether_marker_is_our_dropin_and_nothing_else(geoclue_files: Path) -> None:
    assert not configured()
    Path(geoclue.DROPIN).parent.mkdir(parents=True)
    Path(geoclue.DROPIN).write_text("[network-nmea]\nnmea-socket=/elsewhere\n")
    assert not configured(), "a drop-in we did not write is not our marker"
    Path(geoclue.DROPIN).write_text(dropin_content())
    assert configured()


# ------------------------------------------------------------------ removal


def test_removal_takes_back_both_files_the_socket_and_the_directory(
    geoclue_files: Path, tmp_path: Path
) -> None:
    import socket

    _install_both()
    _make_dir()
    # A short real socket path: AF_UNIX allows 107 bytes, tmp_path is longer.
    sock = socket.socket(socket.AF_UNIX)
    short = Path(os.path.realpath("/tmp")) / f"hg-{os.getpid()}.sock"
    sock.bind(str(short))
    try:
        os.link(short, geoclue.SOCKET)  # the same socket inode, at the long path
        removal = plan_geoclue_removal()
        assert removal == GeoClueRemoval(
            dropin_ours=True, tmpfiles_ours=True, socket_present=True, directory_present=True
        )
        assert _argv(removal_commands(removal)) == [
            f"rm -f {geoclue.DROPIN}",
            f"rm -f {geoclue.TMPFILES}",
            f"rm -f {geoclue.SOCKET}",
            f"rmdir {geoclue.SOCKET_DIR}",
            "systemctl try-restart geoclue",
        ]
        assert verify_removal(removal) != []
    finally:
        sock.close()
        short.unlink(missing_ok=True)


def test_removal_leaves_a_file_someone_else_wrote(geoclue_files: Path) -> None:
    for path in (geoclue.DROPIN, geoclue.TMPFILES):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text("# theirs\n")
    removal = plan_geoclue_removal()
    assert removal.is_empty
    assert removal_commands(removal) == []


def test_removal_never_removes_a_regular_file_at_the_socket_path(geoclue_files: Path) -> None:
    _install_both()
    _make_dir()
    Path(geoclue.SOCKET).write_text("not a socket")
    removal = plan_geoclue_removal()
    assert not removal.socket_present
    assert f"rm -f {geoclue.SOCKET}" not in _argv(removal_commands(removal))


def test_nothing_installed_is_nothing_to_remove() -> None:
    assert plan_geoclue_removal().is_empty


def test_verify_removal_is_clean_once_everything_is_gone(geoclue_files: Path) -> None:
    _install_both()
    _make_dir()
    removal = plan_geoclue_removal()
    Path(geoclue.DROPIN).unlink()
    Path(geoclue.TMPFILES).unlink()
    Path(geoclue.SOCKET_DIR).rmdir()
    assert verify_removal(removal) == []


# ------------------------------------------------------------------ doctor's reading


class _Busctl:
    def __init__(self, stdout: str, returncode: int = 0) -> None:
        self.stdout = stdout
        self.returncode = returncode
        self.ran: list[Command] = []

    def run(self, command: Command) -> CommandResult:
        self.ran.append(command)
        return CommandResult(
            argv=tuple(command.argv), returncode=self.returncode, stdout=self.stdout, stderr=""
        )


DEMO_LINE = "org.freedesktop.GeoClue2.DemoAgent 2345 agent chiefgyk3d :1.84 user@1000.service - -\n"


def test_the_agent_is_read_from_busctl_user_list_and_nothing_else() -> None:
    runner = _Busctl(":1.1 1 systemd root :1.1 init.scope - -\n" + DEMO_LINE)
    assert agent_running(runner) is True
    assert [c.argv for c in runner.ran] == [("busctl", "--user", "list", "--no-pager")]
    assert not runner.ran[0].requires_root
    assert agent_running(_Busctl(":1.1 1 systemd\n")) is False
    assert agent_running(_Busctl("", returncode=1)) is None


def test_the_state_is_none_without_geoclue() -> None:
    assert read_state(ME, runner=_Busctl(DEMO_LINE)) is None


def test_the_state_reads_files_directory_and_agent(geoclue_files: Path) -> None:
    state = read_state(ME, runner=_Busctl(DEMO_LINE))
    assert state is not None
    assert not state.dropin_ours and not state.tmpfiles_ours
    assert state.directory == "absent" and state.agent is True
    _install_both()
    _make_dir()
    state = read_state(ME, runner=_Busctl(""))
    assert state is not None
    assert state.dropin_ours and state.tmpfiles_ours and state.directory == "current"
    assert state.agent is False
