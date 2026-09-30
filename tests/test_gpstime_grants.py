# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""What `hardware apply` installs for GPS time, and how `unapply` takes it back.  D-058."""

from __future__ import annotations

from pathlib import Path

import pytest

from hammunition.backends.base import CommandResult, RecordingRunner
from hammunition.gpstime import files
from hammunition.gpstime.grants import (
    APPARMOR_BLOCK,
    DROPIN_CONTENT,
    TimeGrants,
    disclose,
    grant_commands,
    package_installed,
    plan_time_grants,
    plan_time_removal,
    removal_commands,
    stage_grants,
    stage_removal,
    verify_removal,
    with_block,
    without_block,
)
from hammunition.gpstime.mode import TimeError, render_mode_file, render_ntp_d
from hammunition.gpstime.ntpconf import transform

HELPER = "/usr/local/libexec/hammunition-devctl"


def _never_installed(name: str) -> bool:
    return False


def _apparmor(local: str = "") -> None:
    Path(files.APPARMOR_PROFILE).parent.mkdir(parents=True, exist_ok=True)
    Path(files.APPARMOR_PROFILE).write_text("profile ntpd {}\n")
    Path(files.APPARMOR_LOCAL).parent.mkdir(parents=True, exist_ok=True)
    Path(files.APPARMOR_LOCAL).write_text(local)


def _applied(debian_ntp_conf: str) -> None:
    """The machine as a finished apply plus `time mode gps-only` leave it."""
    _apparmor("# a site rule\n" + APPARMOR_BLOCK)
    Path(files.DROPIN).parent.mkdir(parents=True)
    Path(files.DROPIN).write_text(DROPIN_CONTENT)
    Path(files.NTP_D_FILE).parent.mkdir(parents=True)
    Path(files.NTP_D_FILE).write_text(render_ntp_d("gps-only"))
    Path(files.TIME_CONFIG).parent.mkdir(parents=True)
    Path(files.TIME_CONFIG).write_text(render_mode_file("gps-only"))
    Path(files.NTP_CONF).write_text(transform(debian_ntp_conf, "gps-only"))


def test_the_dropin_grants_exactly_one_capability() -> None:
    live = [ln for ln in DROPIN_CONTENT.splitlines() if ln and not ln.startswith("#")]
    assert live == ["[Service]", "AmbientCapabilities=CAP_IPC_OWNER"]


def test_the_apparmor_block_round_trips_and_is_added_once() -> None:
    assert without_block(with_block("# a site rule\n")) == "# a site rule\n"
    assert with_block(with_block("")) == APPARMOR_BLOCK
    assert without_block("# untouched\n") == "# untouched\n"
    assert APPARMOR_BLOCK.splitlines()[-1] == "capability ipc_owner,"


def test_a_fresh_ntpsec_machine_needs_everything(time_files: Path) -> None:
    _apparmor()
    tg = plan_time_grants(installed=_never_installed)
    assert tg.ntpsec and not tg.dropin_current and not tg.apparmor_current
    assert not tg.ntp_d_dir and not tg.mode_applied and tg.mode == "auto"
    assert not tg.offer_fake_hwclock, "rtc0 exists"
    assert not tg.is_noop


def test_the_commands_for_a_fresh_machine_in_order(time_files: Path) -> None:
    _apparmor()
    tg = plan_time_grants(installed=_never_installed)
    argvs = [c.argv for c in grant_commands(tg, "/stage", HELPER)]
    assert argvs == [
        ("install", "-D", "-m", "0644", "/stage/ntpsec-hammunition-gps.conf", files.DROPIN),
        ("systemctl", "daemon-reload"),
        ("install", "-D", "-m", "0644", "/stage/usr.sbin.ntpd.local", files.APPARMOR_LOCAL),
        ("apparmor_parser", "-r", files.APPARMOR_PROFILE),
        ("install", "-d", "-m", "0755", files.NTP_D_DIR),
        (HELPER, "time", "mode", "auto"),
    ]
    assert all(c.requires_root for c in grant_commands(tg, "/stage", HELPER))


def test_no_apparmor_profile_means_no_apparmor_step(time_files: Path) -> None:
    tg = plan_time_grants(installed=_never_installed)
    assert tg.apparmor_local is None and tg.apparmor_current
    assert not any(c.argv[0] == "apparmor_parser" for c in grant_commands(tg, "/s", HELPER))


def test_new_grants_on_an_applied_mode_restart_instead_of_resetting_it(
    time_files: Path, debian_ntp_conf: str
) -> None:
    _applied(debian_ntp_conf)
    Path(files.DROPIN).unlink()
    tg = plan_time_grants(installed=_never_installed)
    assert tg.mode == "gps-only" and tg.mode_applied
    argvs = [c.argv for c in grant_commands(tg, "/s", HELPER)]
    assert argvs[-1] == ("systemctl", "restart", "ntpsec")
    assert (HELPER, "time", "mode", "gps-only") not in argvs


def test_everything_in_place_is_a_noop(time_files: Path, debian_ntp_conf: str) -> None:
    _applied(debian_ntp_conf)
    tg = plan_time_grants(installed=_never_installed)
    assert tg.is_noop and grant_commands(tg, "/s", HELPER) == []


def test_fake_hwclock_is_offered_only_with_no_rtc(time_files: Path) -> None:
    (Path(files.RTC_CLASS) / "rtc0").rmdir()
    assert plan_time_grants(installed=_never_installed).offer_fake_hwclock
    assert not plan_time_grants(installed=lambda name: True).offer_fake_hwclock
    (Path(files.RTC_CLASS) / "rtc0").mkdir()
    asked: list[str] = []

    def asking(name: str) -> bool:
        asked.append(name)
        return False

    assert not plan_time_grants(installed=asking).offer_fake_hwclock
    assert asked == [], "dpkg is not even asked where a real clock exists"


def test_fake_hwclock_without_ntpsec_is_the_only_command(time_files: Path) -> None:
    Path(files.NTP_CONF).unlink()
    (Path(files.RTC_CLASS) / "rtc0").rmdir()
    tg = plan_time_grants(installed=_never_installed)
    commands = grant_commands(tg, "/s", HELPER)
    assert [c.argv for c in commands] == [
        ("apt-get", "install", "-y", "--no-install-recommends", "fake-hwclock")
    ]
    assert commands[0].env == {"DEBIAN_FRONTEND": "noninteractive"}


def test_the_disclosure_says_what_the_capability_allows(time_files: Path) -> None:
    _apparmor()
    text = "\n".join(disclose(plan_time_grants(installed=_never_installed)))
    assert "CAP_IPC_OWNER bypasses" in text and "System V IPC" in text
    assert files.DROPIN in text and files.APPARMOR_LOCAL in text
    assert "hardware unapply" in text


def test_staging_writes_the_two_files_apply_installs(time_files: Path, tmp_path: Path) -> None:
    _apparmor("# a site rule\n")
    stage = tmp_path / "stage"
    stage.mkdir()
    stage_grants(plan_time_grants(installed=_never_installed), stage)
    assert (stage / "ntpsec-hammunition-gps.conf").read_text() == DROPIN_CONTENT
    assert (stage / "usr.sbin.ntpd.local").read_text() == "# a site rule\n" + APPARMOR_BLOCK


def test_package_installed_asks_dpkg_through_the_runner() -> None:
    key = "dpkg-query -W '-f=${Status}' fake-hwclock"
    runner = RecordingRunner(
        {key: CommandResult(argv=(), returncode=0, stdout="install ok installed", stderr="")}
    )
    assert package_installed("fake-hwclock", runner)
    assert runner.commands[0].argv == ("dpkg-query", "-W", "-f=${Status}", "fake-hwclock")


def test_removal_takes_back_exactly_what_apply_and_the_helper_wrote(
    time_files: Path, debian_ntp_conf: str, tmp_path: Path
) -> None:
    _applied(debian_ntp_conf)
    removal = plan_time_removal()
    assert removal.conf_restored == debian_ntp_conf
    assert removal.ntp_d_ours and removal.time_config_ours and removal.dropin_ours
    assert removal.apparmor_restored == "# a site rule\n"
    argvs = [c.argv for c in removal_commands(removal, "/stage")]
    assert argvs == [
        ("install", "-m", "0644", "/stage/ntp.conf", files.NTP_CONF),
        ("rm", "-f", files.NTP_D_FILE),
        ("rm", "-f", files.TIME_CONFIG),
        ("rm", "-f", files.DROPIN),
        ("install", "-m", "0644", "/stage/usr.sbin.ntpd.local", files.APPARMOR_LOCAL),
        ("apparmor_parser", "-r", files.APPARMOR_PROFILE),
        ("systemctl", "daemon-reload"),
        ("systemctl", "restart", "ntpsec"),
    ]
    stage = tmp_path / "stage"
    stage.mkdir()
    stage_removal(removal, stage)
    assert (stage / "ntp.conf").read_text() == debian_ntp_conf
    # Simulate the commands, then check the verification sees them.
    Path(files.NTP_CONF).write_text((stage / "ntp.conf").read_text())
    for path in (files.NTP_D_FILE, files.TIME_CONFIG, files.DROPIN):
        Path(path).unlink()
    Path(files.APPARMOR_LOCAL).write_text((stage / "usr.sbin.ntpd.local").read_text())
    assert verify_removal(removal) == []


def test_a_file_hammunition_did_not_write_is_not_removed(time_files: Path) -> None:
    Path(files.NTP_D_FILE).parent.mkdir(parents=True)
    Path(files.NTP_D_FILE).write_text("refclock shm unit 2\n")
    removal = plan_time_removal()
    assert not removal.ntp_d_ours
    assert removal.is_empty


def test_a_hand_edited_conffile_refuses_removal(time_files: Path, debian_ntp_conf: str) -> None:
    applied = transform(debian_ntp_conf, "auto")
    Path(files.NTP_CONF).write_text(applied.replace("iburst prefer", "prefer", 1))
    with pytest.raises(TimeError, match="edited by hand"):
        plan_time_removal()


def test_verify_removal_names_what_survived(time_files: Path, debian_ntp_conf: str) -> None:
    _applied(debian_ntp_conf)
    removal = plan_time_removal()
    problems = verify_removal(removal)
    assert any(files.DROPIN in p for p in problems)
    assert any(files.NTP_CONF in p for p in problems)


def test_plan_time_grants_tolerates_an_unreadable_mode_file(time_files: Path) -> None:
    Path(files.TIME_CONFIG).parent.mkdir(parents=True)
    Path(files.TIME_CONFIG).write_text("mode: sometimes\n")
    assert plan_time_grants(installed=_never_installed).mode == "auto"


def test_timegrants_is_hashable_and_frozen() -> None:
    tg = TimeGrants(
        ntpsec=True,
        dropin_current=True,
        apparmor_local=None,
        ntp_d_dir=True,
        mode_applied=True,
        mode="auto",
        offer_fake_hwclock=False,
    )
    assert tg.is_noop
    with pytest.raises(AttributeError):
        tg.ntpsec = False  # type: ignore[misc]
