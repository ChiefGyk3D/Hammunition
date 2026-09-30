# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""What ``hardware apply`` installs so ntpd can read gpsd's time, and how
``hardware unapply`` takes all of GPS time back.  D-058.

gpsd writes the first receiver's time to System V shared-memory units 0 and 1,
root-owned 0600; ntpd drops to ``ntpsec:ntpsec`` with three capabilities and
cannot attach them (measured, spec §4b). Two grants, both disclosed, both
reversed, both installed here and never by the helper:

- a systemd drop-in, ``AmbientCapabilities=CAP_IPC_OWNER`` for ntpsec.service.
  **CAP_IPC_OWNER bypasses permission checks on all System V IPC**, and ntpd
  faces the network; the plan says so in those words;
- ``capability ipc_owner,`` in ntpd's AppArmor local file, the file Debian
  reserves for local additions, added as a marked block and removed as one.
  The file itself is created by ntpsec's maintainer script and not owned by
  dpkg, and the profile's ``#include`` needs it to exist, so it is never deleted.

Removal is by content, not by the log: a file is removed only when it starts
with the header Hammunition writes, ntp.conf's marked lines are restored
exactly, and only the marked block leaves the AppArmor file.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from hammunition.backends.base import BackendError, Command, CommandRunner, SubprocessRunner
from hammunition.gpstime import files
from hammunition.gpstime.mode import DEFAULT_MODE, HELPER_HEADER, Mode, TimeError, read_mode
from hammunition.gpstime.ntpconf import mode_writes, restore
from hammunition.gpstime.state import APPARMOR_RULE, has_rtc, ntpsec_installed

__all__ = [
    "APPARMOR_BLOCK",
    "DROPIN_CONTENT",
    "DROPIN_HEADER",
    "FAKE_HWCLOCK",
    "TimeGrants",
    "TimeRemoval",
    "disclose",
    "grant_commands",
    "package_installed",
    "plan_time_grants",
    "plan_time_removal",
    "removal_commands",
    "stage_grants",
    "stage_removal",
    "verify_grants",
    "verify_removal",
    "with_block",
    "without_block",
]

DROPIN_HEADER = "# Written by `hammunition hardware apply` (D-058)."
DROPIN_CONTENT = (
    f"{DROPIN_HEADER} Lets ntpd attach the time segment\n"
    "# gpsd creates root-only (mode 0600). CAP_IPC_OWNER bypasses permission checks\n"
    "# on all System V IPC. `hammunition hardware unapply` removes this file.\n"
    "[Service]\n"
    "AmbientCapabilities=CAP_IPC_OWNER\n"
)
GPSD_DROPIN_CONTENT = (
    "# Written by Hammunition (catalog unit `chrony`, D-072).\n"
    "# Poll the receiver with no client connected, so chrony gets its time.\n"
    "[Service]\n"
    "Environment=OPTIONS=-n\n"
)
"""gpsd polls a receiver, and so publishes time to shared memory, only while a
client is connected unless it runs with ``-n`` (gpsd(8); measured on PR #162:
0 samples in SHM without it, 9 in 8 s with it). Debian's gpsd.service runs
``gpsd $GPSD_OPTIONS $OPTIONS $DEVICES`` and /etc/default/gpsd sets no OPTIONS,
so a drop-in adds the flag without touching gpsd's conffile.

**Byte for byte the text the ``chrony`` catalog unit writes at the same path**
(D-072), header included, so the two units never rewrite each other's file
and a second install is a no-op. The header names the chrony unit because
that text was written first; changing it here alone would make the two
fight over the file."""

APPARMOR_BLOCK = (
    "# Added by `hammunition hardware apply` (D-058): ntpd reads gpsd's time.\n"
    "# `hammunition hardware unapply` removes these three lines and nothing else.\n"
    f"{APPARMOR_RULE}\n"
)
FAKE_HWCLOCK = "fake-hwclock"
_STAGED_DROPIN = "ntpsec-hammunition-gps.conf"
_STAGED_GPSD_DROPIN = "gpsd-hammunition-gps.conf"
_STAGED_APPARMOR = "usr.sbin.ntpd.local"
_STAGED_CONF = "ntp.conf"
_RESTART = ("systemctl", "restart", "ntpsec")


def with_block(text: str) -> str:
    if APPARMOR_BLOCK in text:
        return text
    if text and not text.endswith("\n"):
        text += "\n"
    return text + APPARMOR_BLOCK


def without_block(text: str) -> str:
    return text.replace(APPARMOR_BLOCK, "")


def _read(path: str) -> str | None:
    try:
        return Path(path).read_text(encoding="utf-8")
    except (FileNotFoundError, NotADirectoryError):
        return None


def package_installed(name: str, runner: CommandRunner | None = None) -> bool:
    command = Command(
        argv=("dpkg-query", "-W", "-f=${Status}", name),
        description=f"Ask dpkg whether {name} is installed",
    )
    try:
        result = (runner or SubprocessRunner()).run(command)
    except BackendError:
        return False
    return result.ok and result.stdout.strip() == "install ok installed"


@dataclass(frozen=True)
class TimeGrants:
    ntpsec: bool
    dropin_current: bool
    apparmor_local: str | None
    """The AppArmor local file's text now ("" when absent), or None when ntpd has
    no AppArmor profile here and there is nothing to add or reload."""
    ntp_d_dir: bool
    mode_applied: bool
    """The ntp.d file exists, i.e. the helper has set a mode at least once."""
    mode: Mode
    offer_fake_hwclock: bool
    gpsd: bool = True
    """gpsd is installed. Without it there is no GPS time to read, so nothing
    widens ntpd's privilege or touches ntp.conf."""
    mode_writes: tuple[str, ...] = ()
    """What the first ``time mode`` will write, for the disclosure (empty once a
    mode is applied)."""
    gpsd_dropin_current: bool = False
    """gpsd's ``-n`` drop-in is already there, with exactly our text (possibly
    written by the ``chrony`` unit, which writes the same)."""

    @property
    def gps_time(self) -> bool:
        return self.ntpsec and self.gpsd

    @property
    def apparmor_current(self) -> bool:
        return self.apparmor_local is None or APPARMOR_BLOCK in self.apparmor_local

    @property
    def grants_change(self) -> bool:
        return self.gps_time and not (self.dropin_current and self.apparmor_current)

    @property
    def dropins_change(self) -> bool:
        return self.gps_time and not (self.dropin_current and self.gpsd_dropin_current)

    @property
    def is_noop(self) -> bool:
        if self.offer_fake_hwclock:
            return False
        if not self.gps_time:
            return True
        return (
            self.dropin_current
            and self.gpsd_dropin_current
            and self.apparmor_current
            and self.ntp_d_dir
            and self.mode_applied
        )


def plan_time_grants(*, installed: Callable[[str], bool] = package_installed) -> TimeGrants:
    try:
        mode, _ = read_mode()
    except TimeError:
        mode = DEFAULT_MODE
    profile = Path(files.APPARMOR_PROFILE).is_file()
    ntpsec = ntpsec_installed()
    gpsd = ntpsec and installed("gpsd")
    mode_applied = Path(files.NTP_D_FILE).is_file()
    gpsd_text = _read(files.GPSD_DROPIN)
    if gpsd and gpsd_text is not None and gpsd_text != GPSD_DROPIN_CONTENT:
        raise TimeError(
            f"{files.GPSD_DROPIN} exists and holds text Hammunition did not write. GPS "
            f"time needs gpsd to run with -n from that file, and it is never overwritten. "
            f"Move it aside and re-run, or use `--no-gps-time`. Nothing was changed."
        )
    writes: tuple[str, ...] = ()
    if gpsd and not mode_applied:
        # Raises TimeError on a conffile without its anchors: refused here,
        # before anything runs, not mid-run in the helper.
        conf = Path(files.NTP_CONF).read_text(encoding="utf-8")
        writes = tuple(mode_writes(conf, mode))
    return TimeGrants(
        ntpsec=ntpsec,
        dropin_current=_read(files.DROPIN) == DROPIN_CONTENT,
        apparmor_local=(_read(files.APPARMOR_LOCAL) or "") if profile else None,
        ntp_d_dir=Path(files.NTP_D_DIR).is_dir(),
        mode_applied=mode_applied,
        mode=mode,
        offer_fake_hwclock=not has_rtc() and not installed(FAKE_HWCLOCK),
        gpsd=gpsd,
        mode_writes=writes,
        gpsd_dropin_current=gpsd_text == GPSD_DROPIN_CONTENT,
    )


def disclose(tg: TimeGrants) -> list[str]:
    lines: list[str] = []
    if tg.offer_fake_hwclock:
        lines += [
            "No hardware clock was found (/sys/class/rtc is empty). Will install fake-hwclock:",
            "  it saves the time at shutdown and hourly and restores it at boot. A stopgap:",
            "  the restored time is wrong by however long the machine was off; a battery-",
            "  backed RTC module is the fix. `sudo apt remove fake-hwclock` reverses it.",
        ]
    if not tg.ntpsec:
        return lines
    if not tg.gpsd:
        return [
            *lines,
            "GPS time (D-058): gpsd is not installed, so there is no GPS time for ntpd to",
            "  read; ntpd's privilege and ntp.conf are left alone. Install gpsd (the",
            "  `navigation` profile) and re-run to set it up.",
        ]
    ntp: list[str] = []
    if tg.grants_change:
        ntp.append("Will let ntpd read gpsd's time (D-058):")
    if not tg.dropin_current:
        ntp += [
            f"  {files.DROPIN}: AmbientCapabilities=CAP_IPC_OWNER",
            "    This widens a network-facing daemon's privilege: CAP_IPC_OWNER bypasses",
            "    permission checks on all System V IPC, not only gpsd's segment.",
        ]
    if not tg.apparmor_current:
        ntp.append(f"  {files.APPARMOR_LOCAL}: + {APPARMOR_RULE} (and ntpd's profile is reloaded)")
    if not tg.gpsd_dropin_current:
        ntp += [
            "Will make gpsd poll the receiver with no client connected (gpsd -n), so it",
            "  publishes time for ntpd; without it gpsd writes no time to shared memory:",
            f"  {files.GPSD_DROPIN}:",
            *(f"    {line}" for line in GPSD_DROPIN_CONTENT.splitlines()),
            "  The same file, with the same text, as the `chrony` unit writes. Inspect it",
            "  with `systemctl cat gpsd`. gpsd reads it when it next starts: reboot after",
            "  this run (restarting gpsd in place left two gpsd processes in testing).",
            "  `hardware unapply` removes it unless the `chrony` unit still uses it.",
        ]
    if not tg.ntp_d_dir:
        ntp.append(f"Will create {files.NTP_D_DIR}, which ntpd reads after {files.NTP_CONF}.")
    if not tg.mode_applied:
        ntp.append(f"Will set time mode {tg.mode} through the helper, which writes, as root:")
        ntp += list(tg.mode_writes)
    elif tg.grants_change:
        ntp.append("Will restart ntpsec so it runs with the grants.")
    if ntp:
        ntp.append("`hammunition hardware unapply` reverses all of it.")
    return lines + ntp


def grant_commands(tg: TimeGrants, staging_root: str, helper: str) -> list[Command]:
    out: list[Command] = []
    if tg.offer_fake_hwclock:
        out.append(
            Command(
                argv=("apt-get", "install", "-y", "--no-install-recommends", FAKE_HWCLOCK),
                description=(
                    "Install fake-hwclock: there is no hardware clock, so it saves the time "
                    "at shutdown and hourly and restores it at boot"
                ),
                requires_root=True,
                env={"DEBIAN_FRONTEND": "noninteractive"},
            )
        )
    if not tg.gps_time:
        return out
    if not tg.dropin_current:
        out.append(
            Command(
                argv=(
                    "install",
                    "-D",
                    "-m",
                    "0644",
                    f"{staging_root}/{_STAGED_DROPIN}",
                    files.DROPIN,
                ),
                description="Let ntpd attach gpsd's root-only time segment (CAP_IPC_OWNER)",
                requires_root=True,
            )
        )
    if not tg.gpsd_dropin_current:
        out.append(
            Command(
                argv=(
                    "install",
                    "-D",
                    "-m",
                    "0644",
                    f"{staging_root}/{_STAGED_GPSD_DROPIN}",
                    files.GPSD_DROPIN,
                ),
                description="Run gpsd with -n, so it publishes the receiver's time with no client",
                requires_root=True,
            )
        )
    if tg.dropins_change:
        out.append(
            Command(
                argv=("systemctl", "daemon-reload"),
                description="Reload systemd so ntpsec.service and gpsd.service take the drop-ins",
                requires_root=True,
            )
        )
    if not tg.apparmor_current:
        out += [
            Command(
                argv=(
                    "install",
                    "-D",
                    "-m",
                    "0644",
                    f"{staging_root}/{_STAGED_APPARMOR}",
                    files.APPARMOR_LOCAL,
                ),
                description="Allow ntpd's AppArmor profile the same capability",
                requires_root=True,
            ),
            Command(
                argv=("apparmor_parser", "-r", files.APPARMOR_PROFILE),
                description="Reload ntpd's AppArmor profile",
                requires_root=True,
            ),
        ]
    if not tg.ntp_d_dir:
        out.append(
            Command(
                argv=("install", "-d", "-m", "0755", files.NTP_D_DIR),
                description="Create the directory ntpd reads after ntp.conf",
                requires_root=True,
            )
        )
    if not tg.mode_applied:
        out.append(
            Command(
                argv=(helper, "time", "mode", tg.mode),
                description=f"Set time mode {tg.mode} through the helper, which restarts ntpsec",
                requires_root=True,
            )
        )
    elif tg.grants_change:
        out.append(
            Command(
                argv=_RESTART,
                description="Restart ntpsec so it runs with the grants",
                requires_root=True,
            )
        )
    return out


def stage_grants(tg: TimeGrants, staging_dir: Path) -> None:
    if tg.gps_time and not tg.dropin_current:
        (staging_dir / _STAGED_DROPIN).write_text(DROPIN_CONTENT)
        os.chmod(staging_dir / _STAGED_DROPIN, 0o644)
    if tg.gps_time and not tg.gpsd_dropin_current:
        (staging_dir / _STAGED_GPSD_DROPIN).write_text(GPSD_DROPIN_CONTENT)
        os.chmod(staging_dir / _STAGED_GPSD_DROPIN, 0o644)
    if tg.gps_time and tg.apparmor_local is not None and not tg.apparmor_current:
        (staging_dir / _STAGED_APPARMOR).write_text(with_block(tg.apparmor_local))
        os.chmod(staging_dir / _STAGED_APPARMOR, 0o644)


def verify_grants(
    tg: TimeGrants, *, installed: Callable[[str], bool] = package_installed
) -> list[str]:
    problems: list[str] = []
    if tg.offer_fake_hwclock and not installed(FAKE_HWCLOCK):
        problems.append("fake-hwclock is not installed after apt-get reported success")
    if not tg.gps_time:
        return problems
    if _read(files.DROPIN) != DROPIN_CONTENT:
        problems.append(f"{files.DROPIN} on disk does not match what we wrote")
    if _read(files.GPSD_DROPIN) != GPSD_DROPIN_CONTENT:
        problems.append(f"{files.GPSD_DROPIN} on disk does not match what we wrote")
    if tg.apparmor_local is not None and APPARMOR_BLOCK not in (_read(files.APPARMOR_LOCAL) or ""):
        problems.append(f"{files.APPARMOR_LOCAL} does not hold the {APPARMOR_RULE!r} block")
    if not Path(files.NTP_D_DIR).is_dir():
        problems.append(f"{files.NTP_D_DIR} is not a directory")
    if not Path(files.NTP_D_FILE).is_file():
        problems.append(f"{files.NTP_D_FILE} was not written by the helper")
    return problems


@dataclass(frozen=True)
class TimeRemoval:
    conf_restored: str | None
    """ntp.conf with the marked edits undone, or None when it carries none."""
    ntp_d_ours: bool
    time_config_ours: bool
    dropin_ours: bool
    apparmor_restored: str | None
    """The AppArmor local file without Hammunition's block, or None when the block is absent."""
    apparmor_profile: bool
    ntpsec: bool
    gpsd_dropin_ours: bool = False
    """gpsd's ``-n`` drop-in holds exactly the text Hammunition writes."""
    gpsd_dropin_shared: bool = False
    """The ``chrony`` unit still relies on it (its conf.d file is present), so it stays."""

    @property
    def removes_gpsd_dropin(self) -> bool:
        return self.gpsd_dropin_ours and not self.gpsd_dropin_shared

    @property
    def is_empty(self) -> bool:
        return (
            self.conf_restored is None
            and not (self.ntp_d_ours or self.time_config_ours or self.dropin_ours)
            and not self.removes_gpsd_dropin
            and self.apparmor_restored is None
        )


def _ours(path: str, header: str) -> bool:
    text = _read(path)
    return text is not None and text.startswith(header)


def plan_time_removal() -> TimeRemoval:
    """What unapply takes back. Raises TimeError when ntp.conf was edited by hand."""
    conf = _read(files.NTP_CONF)
    restored = None if conf is None else restore(conf)
    local = _read(files.APPARMOR_LOCAL)
    return TimeRemoval(
        conf_restored=restored if restored != conf else None,
        ntp_d_ours=_ours(files.NTP_D_FILE, HELPER_HEADER),
        time_config_ours=_ours(files.TIME_CONFIG, HELPER_HEADER),
        dropin_ours=_ours(files.DROPIN, DROPIN_HEADER),
        apparmor_restored=(
            None if local is None or APPARMOR_BLOCK not in local else without_block(local)
        ),
        apparmor_profile=Path(files.APPARMOR_PROFILE).is_file(),
        ntpsec=conf is not None,
        gpsd_dropin_ours=_read(files.GPSD_DROPIN) == GPSD_DROPIN_CONTENT,
        gpsd_dropin_shared=Path(files.CHRONY_GPS_CONF).exists(),
    )


def removal_commands(r: TimeRemoval, staging_root: str) -> list[Command]:
    out: list[Command] = []
    if r.conf_restored is not None:
        out.append(
            Command(
                argv=("install", "-m", "0644", f"{staging_root}/{_STAGED_CONF}", files.NTP_CONF),
                description=(
                    f"Put {files.NTP_CONF}'s marked lines back exactly as they were "
                    f"before Hammunition edited them"
                ),
                requires_root=True,
            )
        )
    for path, ours in (
        (files.NTP_D_FILE, r.ntp_d_ours),
        (files.TIME_CONFIG, r.time_config_ours),
        (files.DROPIN, r.dropin_ours),
        (files.GPSD_DROPIN, r.removes_gpsd_dropin),
    ):
        if ours:
            out.append(
                Command(
                    argv=("rm", "-f", path),
                    description=f"Remove {path}, written by Hammunition for GPS time",
                    requires_root=True,
                )
            )
    if r.apparmor_restored is not None:
        out.append(
            Command(
                argv=(
                    "install",
                    "-m",
                    "0644",
                    f"{staging_root}/{_STAGED_APPARMOR}",
                    files.APPARMOR_LOCAL,
                ),
                description=f"Take Hammunition's block out of {files.APPARMOR_LOCAL}, leaving the rest",
                requires_root=True,
            )
        )
        if r.apparmor_profile:
            out.append(
                Command(
                    argv=("apparmor_parser", "-r", files.APPARMOR_PROFILE),
                    description="Reload ntpd's AppArmor profile",
                    requires_root=True,
                )
            )
    if r.dropin_ours or r.removes_gpsd_dropin:
        out.append(
            Command(
                argv=("systemctl", "daemon-reload"),
                description="Reload systemd so ntpsec.service and gpsd.service lose the drop-ins",
                requires_root=True,
            )
        )
    if r.ntpsec and not r.is_empty:
        out.append(
            Command(
                argv=_RESTART,
                description="Restart ntpsec on the package's own configuration",
                requires_root=True,
            )
        )
    return out


def stage_removal(r: TimeRemoval, staging_dir: Path) -> None:
    if r.conf_restored is not None:
        (staging_dir / _STAGED_CONF).write_text(r.conf_restored)
        os.chmod(staging_dir / _STAGED_CONF, 0o644)
    if r.apparmor_restored is not None:
        (staging_dir / _STAGED_APPARMOR).write_text(r.apparmor_restored)
        os.chmod(staging_dir / _STAGED_APPARMOR, 0o644)


def verify_removal(r: TimeRemoval) -> list[str]:
    problems: list[str] = []
    if r.conf_restored is not None and _read(files.NTP_CONF) != r.conf_restored:
        problems.append(f"{files.NTP_CONF} does not read back as the package's lines")
    for path, ours in (
        (files.NTP_D_FILE, r.ntp_d_ours),
        (files.TIME_CONFIG, r.time_config_ours),
        (files.DROPIN, r.dropin_ours),
        (files.GPSD_DROPIN, r.removes_gpsd_dropin),
    ):
        if ours and Path(path).exists():
            problems.append(f"{path} is still present")
    if r.apparmor_restored is not None and APPARMOR_BLOCK in (_read(files.APPARMOR_LOCAL) or ""):
        problems.append(f"{files.APPARMOR_LOCAL} still holds Hammunition's block")
    return problems
