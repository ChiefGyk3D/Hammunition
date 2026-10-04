# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""The GPS receiver's resume step: installed by ``hardware apply``, removed by
``hardware unapply``.  Issue #177, D-058 (amended 2026-10-01).

Measured on the field laptop: across 19 suspends the USB receiver was never
re-enumerated, so no ``gpsdctl`` remove or add followed a resume, and gpsd can
keep a tty that has gone quiet. Every recovery that worked gave gpsd a fresh
open. Two root-owned files do that after each resume:

- ``/usr/local/libexec/hammunition-gps-resume``, the script in
  :mod:`hammunition.hardware.gps_resume_script`, installed whole with our
  header, 0755;
- ``/etc/systemd/system/hammunition-gps-resume.service``, a oneshot ordered
  after the four sleep targets and wanted by them, enabled (never started).

Both are staged and installed by ``install -D``, the route the helper takes
(D-056), disclosed in full in the plan, read back afterwards (D-031), and
removed by content: a file is removed only when it starts with the header
Hammunition writes. A file at either path without that header refuses the
plan rather than being overwritten.

A device class asks for the step by name (``resume: {step: gpsd_reopen}``);
the catalog never carries the command. Without gpsd installed there is nothing
to reopen, and no step is planned.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from hammunition.backends.base import Command

__all__ = [
    "GPSD",
    "PATHS",
    "SCRIPT",
    "SLEEP_TARGETS",
    "SYSTEMD_DIR",
    "UNIT_HEADER",
    "UNIT_NAME",
    "GpsResume",
    "GpsResumeError",
    "GpsResumeRemoval",
    "ResumeStatus",
    "disclose",
    "install_commands",
    "plan_gps_resume",
    "plan_gps_resume_removal",
    "removal_commands",
    "script_content",
    "stage",
    "status",
    "unit_content",
    "unit_path",
    "verify",
    "verify_removal",
    "wants_links",
]

GPSD = "/usr/sbin/gpsd"
"""gpsd's daemon. Its package depends on python3, so where it is, the script runs."""

SCRIPT = "/usr/local/libexec/hammunition-gps-resume"
SYSTEMD_DIR = "/etc/systemd/system"
UNIT_NAME = "hammunition-gps-resume.service"
SLEEP_TARGETS = (
    "suspend.target",
    "hibernate.target",
    "hybrid-sleep.target",
    "suspend-then-hibernate.target",
)

PATHS: dict[str, str] = {"GPSD": GPSD, "SCRIPT": SCRIPT, "SYSTEMD_DIR": SYSTEMD_DIR}
"""Each path attribute and its real default, for the fixtures that repoint them.
Read as module globals at call time, so a test's ``monkeypatch.setattr`` holds."""

UNIT_HEADER = "# Written by `hammunition hardware apply` (issue #177)."
_SCRIPT_HEADER = (
    f"{UNIT_HEADER} Run by\n"
    f"# {UNIT_NAME} after a resume: gives gpsd a fresh open of each GPS receiver.\n"
    "# `hammunition hardware unapply` removes this file.\n"
)
_STAGED_SCRIPT = "hammunition-gps-resume"
_STAGED_UNIT = "hammunition-gps-resume.service"


class GpsResumeError(Exception):
    """A file at the step's path that Hammunition did not write."""


def unit_path() -> str:
    return f"{SYSTEMD_DIR}/{UNIT_NAME}"


def wants_links() -> tuple[str, ...]:
    """The symlinks ``systemctl enable`` makes for the unit's ``WantedBy=``."""
    return tuple(f"{SYSTEMD_DIR}/{target}.wants/{UNIT_NAME}" for target in SLEEP_TARGETS)


def script_content() -> str:
    """The installed script: a shebang, our header, then the module's own source."""
    source = Path(__file__).with_name("gps_resume_script.py").read_text(encoding="utf-8")
    return f"#!/usr/bin/python3 -I\n{_SCRIPT_HEADER}{source}"


def unit_content() -> str:
    targets = " ".join(SLEEP_TARGETS)
    return (
        f"{UNIT_HEADER} After a suspend or\n"
        "# hibernation, gives gpsd a fresh open of each GPS receiver: one that is not\n"
        "# re-enumerated on resume can leave gpsd holding a tty that has gone quiet.\n"
        "# `hammunition hardware unapply` removes this file and the script it runs.\n"
        "[Unit]\n"
        "Description=Give gpsd a fresh open of the GPS receiver after resume (Hammunition)\n"
        f"After={targets}\n"
        "\n"
        "[Service]\n"
        "Type=oneshot\n"
        f"ExecStart={SCRIPT}\n"
        "\n"
        "[Install]\n"
        f"WantedBy={targets}\n"
    )


def _read(path: str) -> str | None:
    """The file's text; None when nothing is there. A directory, a file that is
    not UTF-8 or one this account cannot read is something, and reads as ""
    so it is never taken for ours."""
    try:
        return Path(path).read_text(encoding="utf-8")
    except (FileNotFoundError, NotADirectoryError):
        return None
    except (OSError, UnicodeDecodeError):
        return ""


def _enabled() -> bool:
    return all(Path(link).is_symlink() for link in wants_links())


def _script_executable() -> bool:
    try:
        return os.stat(SCRIPT).st_mode & 0o777 == 0o755
    except OSError:
        return False


@dataclass(frozen=True)
class GpsResume:
    """What ``hardware apply`` will do for the resume step."""

    gpsd: bool
    """gpsd is installed. Without it there is nothing to reopen."""
    script_current: bool
    unit_current: bool
    enabled: bool
    """Every sleep target's ``.wants`` link is present."""

    @property
    def is_noop(self) -> bool:
        return not self.gpsd or (self.script_current and self.unit_current and self.enabled)


def _ours(text: str | None) -> bool:
    """Our header on the first line (the unit) or the second (after the shebang).
    The header's opening words only, so an older engine's file is still ours."""
    return text is not None and any(
        line.startswith(UNIT_HEADER) for line in text.split("\n", 2)[:2]
    )


def _refuse_foreign(path: str, text: str | None) -> None:
    if text is not None and not _ours(text):
        raise GpsResumeError(
            f"{path} exists and was not written by Hammunition. The GPS resume step "
            f"(issue #177) installs a file there and never overwrites one it did not "
            f"write. Move it aside and re-run, or use `--no-gps-resume`. Nothing was changed."
        )


def plan_gps_resume() -> GpsResume:
    """Read what is installed. Raises :class:`GpsResumeError` on a foreign file,
    but only where gpsd is installed and the step would be."""
    if not Path(GPSD).exists():
        return GpsResume(gpsd=False, script_current=False, unit_current=False, enabled=False)
    script = _read(SCRIPT)
    unit = _read(unit_path())
    _refuse_foreign(SCRIPT, script)
    _refuse_foreign(unit_path(), unit)
    return GpsResume(
        gpsd=True,
        script_current=script == script_content() and _script_executable(),
        unit_current=unit == unit_content(),
        enabled=_enabled(),
    )


def disclose(step: GpsResume) -> list[str]:
    if not step.gpsd:
        return [
            "GPS resume step (issue #177): gpsd is not installed, so there is nothing to",
            "  reopen after a suspend; not installed. Install gpsd and re-run to add it.",
        ]
    if step.is_noop:
        return []
    lines = [
        "Will install the GPS receiver's resume step (issue #177). A receiver that is not",
        "  re-enumerated across a suspend can leave gpsd holding a tty that has gone quiet;",
        "  after every suspend or hibernation this gives gpsd a fresh open of it.",
        "  It does nothing when no /dev/gpsN exists, so a parked receiver is never woken.",
        "  It then checks that data flows (up to 20 s). If the receiver stays silent it may",
        "  power-cycle it once through its USB `authorized` switch, the same switch",
        "  `hammunition hardware park` and `wake` use; a cycled receiver loses its warm start",
        "  (a 3D fix returned 74 s after a wake on the bench).",
    ]
    if not step.script_current:
        lines += [
            f"  {SCRIPT} (root-owned 0755, run as root by the unit):",
            *(f"    {line}" for line in script_content().splitlines()),
        ]
    if not step.unit_current:
        lines += [
            f"  {unit_path()}:",
            *(f"    {line}" for line in unit_content().splitlines()),
        ]
    if not step.enabled or not step.unit_current:
        lines.append(
            "  Enabled for suspend, hibernate, hybrid-sleep and suspend-then-hibernate;"
            " it does not run now."
        )
    lines += [
        f"  Inspect: `systemctl cat {UNIT_NAME}`, `systemctl status {UNIT_NAME}`,",
        f"  and each run's lines with `journalctl -u {UNIT_NAME}`.",
        "  Reverse: `hammunition hardware unapply`. `--no-gps-resume` leaves it out of this run.",
    ]
    return lines


def install_commands(step: GpsResume, staging_root: str) -> list[Command]:
    if step.is_noop:
        return []
    out: list[Command] = []
    if not step.script_current:
        out.append(
            Command(
                argv=("install", "-D", "-m", "0755", f"{staging_root}/{_STAGED_SCRIPT}", SCRIPT),
                description=f"Install the GPS resume script to {SCRIPT}",
                requires_root=True,
            )
        )
    if not step.unit_current:
        out += [
            Command(
                argv=("install", "-D", "-m", "0644", f"{staging_root}/{_STAGED_UNIT}", unit_path()),
                description=f"Install the GPS resume unit to {unit_path()}",
                requires_root=True,
            ),
            Command(
                argv=("systemctl", "daemon-reload"),
                description=f"Reload systemd so it reads {UNIT_NAME}",
                requires_root=True,
            ),
        ]
    if not step.enabled or not step.unit_current:
        out.append(
            Command(
                argv=("systemctl", "enable", UNIT_NAME),
                description=f"Enable {UNIT_NAME} for the four sleep targets (it does not run now)",
                requires_root=True,
            )
        )
    return out


def stage(step: GpsResume, staging_dir: Path) -> None:
    if step.is_noop:
        return
    if not step.script_current:
        (staging_dir / _STAGED_SCRIPT).write_text(script_content())
        # Semgrep: a deliberate mode (0755/0644 on installed files and launchers, 0700 private); nothing group- or world-writable.
        # nosemgrep: python.lang.security.audit.insecure-file-permissions.insecure-file-permissions
        os.chmod(staging_dir / _STAGED_SCRIPT, 0o755)
    if not step.unit_current:
        (staging_dir / _STAGED_UNIT).write_text(unit_content())
        os.chmod(staging_dir / _STAGED_UNIT, 0o644)


def verify(step: GpsResume) -> list[str]:
    """D-031: the files read back and the links exist, not the exit codes."""
    if not step.gpsd:
        return []
    problems: list[str] = []
    if _read(SCRIPT) != script_content():
        problems.append(f"{SCRIPT} on disk does not match what we wrote")
    elif not _script_executable():
        problems.append(f"{SCRIPT} is not mode 0755")
    if _read(unit_path()) != unit_content():
        problems.append(f"{unit_path()} on disk does not match what we wrote")
    missing = [link for link in wants_links() if not Path(link).is_symlink()]
    if missing:
        problems.append(f"{UNIT_NAME} is not enabled: {', '.join(missing)} missing")
    return problems


ResumeStatus = Literal["installed", "stale", "absent"]


def status() -> ResumeStatus:
    """For ``doctor``: installed as this engine writes it, present but not
    current (an older engine's, or not enabled), or absent."""
    script = _read(SCRIPT)
    unit = _read(unit_path())
    if script is None and unit is None:
        return "absent"
    if script == script_content() and unit == unit_content() and _enabled():
        return "installed"
    return "stale"


@dataclass(frozen=True)
class GpsResumeRemoval:
    unit_ours: bool
    script_ours: bool

    @property
    def is_empty(self) -> bool:
        return not (self.unit_ours or self.script_ours)


def plan_gps_resume_removal() -> GpsResumeRemoval:
    """By content, not by the log: only a file that starts with our header."""
    script = _read(SCRIPT)
    unit = _read(unit_path())
    return GpsResumeRemoval(
        unit_ours=_ours(unit),
        script_ours=_ours(script),
    )


def removal_commands(removal: GpsResumeRemoval) -> list[Command]:
    out: list[Command] = []
    if removal.unit_ours:
        out += [
            Command(
                argv=("systemctl", "disable", UNIT_NAME),
                description=f"Disable {UNIT_NAME}, removing its links from the sleep targets",
                requires_root=True,
            ),
            Command(
                argv=("rm", "-f", unit_path()),
                description=f"Remove {unit_path()}, written by Hammunition (issue #177)",
                requires_root=True,
            ),
        ]
    if removal.script_ours:
        out.append(
            Command(
                argv=("rm", "-f", SCRIPT),
                description=f"Remove {SCRIPT}, written by Hammunition (issue #177)",
                requires_root=True,
            )
        )
    if removal.unit_ours:
        out.append(
            Command(
                argv=("systemctl", "daemon-reload"),
                description=f"Reload systemd so it forgets {UNIT_NAME}",
                requires_root=True,
            )
        )
    return out


def verify_removal(removal: GpsResumeRemoval) -> list[str]:
    problems: list[str] = []
    if removal.unit_ours:
        if Path(unit_path()).exists():
            problems.append(f"{unit_path()} is still present")
        problems += [
            f"{link} is still present" for link in wants_links() if Path(link).is_symlink()
        ]
    if removal.script_ours and Path(SCRIPT).exists():
        problems.append(f"{SCRIPT} is still present")
    return problems
