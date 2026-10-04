# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""A read-only report on the GPS resume step.  Issue #177.

``hammunition hardware gps-resume-report`` answers, for an operator who is not
in ``systemd-journal``: is the installed step what this engine would write now,
what did the unit's last run do, does gpsd list the receiver, does it deliver
data, and does the bus look the way the step expects?

It **never writes, never keys a receiver and never changes a power state**. It
reads files, runs ``systemctl show`` (no privilege for a system unit), asks
gpsd's socket ``?DEVICES;`` and ``?WATCH`` as the step does, and reads sysfs.
The socket questions are the step's own functions, imported rather than
copied, so the report and the step cannot disagree about what "alive" means.
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from hammunition.hardware import gps_resume
from hammunition.hardware import gps_resume_script as script

__all__ = [
    "FileCheck",
    "ReceiverReport",
    "ResumeReport",
    "UnitState",
    "UsbFacts",
    "gather",
    "parse_show",
    "usb_facts",
]

LOG_TAIL = 40
_PROPERTIES = (
    "LoadState",
    "UnitFileState",
    "ActiveState",
    "Result",
    "ExecMainStatus",
    "ActiveEnterTimestamp",
    "ExecMainExitTimestamp",
)


@dataclass(frozen=True)
class FileCheck:
    path: str
    state: str
    """``current``, ``differs``, ``absent`` or ``unreadable``."""


@dataclass(frozen=True)
class UnitState:
    load_state: str | None = None
    unit_file_state: str | None = None
    active_state: str | None = None
    result: str | None = None
    exec_main_status: str | None = None
    active_enter: str | None = None
    exec_main_exit: str | None = None
    error: str | None = None


@dataclass(frozen=True)
class UsbFacts:
    device: str | None = None
    vendor: str | None = None
    product: str | None = None
    authorized: str | None = None
    error: str | None = None


@dataclass(frozen=True)
class ReceiverReport:
    link: str
    node: str
    listed_by_gpsd: bool | None
    data_seconds: float | None
    usb: UsbFacts


@dataclass(frozen=True)
class ResumeReport:
    files: tuple[FileCheck, ...]
    enabled: bool
    unit: UnitState
    gpsd_devices: list[str] | None
    receivers: tuple[ReceiverReport, ...]
    data_window: float
    log_path: str
    log_present: bool
    log_modified: str | None
    log_lines: tuple[str, ...]
    findings: tuple[str, ...]


def _compare(path: str, wanted: str) -> FileCheck:
    try:
        text = Path(path).read_text(encoding="utf-8")
    except (FileNotFoundError, NotADirectoryError):
        return FileCheck(path, "absent")
    except (OSError, UnicodeDecodeError):
        return FileCheck(path, "unreadable")
    return FileCheck(path, "current" if text == wanted else "differs")


def parse_show(text: str) -> dict[str, str]:
    """``Key=Value`` lines of ``systemctl show``."""
    pairs: dict[str, str] = {}
    for line in text.splitlines():
        key, sep, value = line.partition("=")
        if sep:
            pairs[key] = value
    return pairs


def unit_state(systemctl: str = "/usr/bin/systemctl") -> UnitState:
    argv = [systemctl, "show", gps_resume.UNIT_NAME, "--no-pager"]
    argv += [f"--property={name}" for name in _PROPERTIES]
    try:
        result = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            timeout=15,
            env={"PATH": "/usr/sbin:/usr/bin:/sbin:/bin"},
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return UnitState(error=str(exc))
    if result.returncode != 0:
        said = (result.stderr or result.stdout).strip().splitlines()
        return UnitState(error=said[-1] if said else f"systemctl exited {result.returncode}")
    shown = parse_show(result.stdout)
    return UnitState(
        load_state=shown.get("LoadState"),
        unit_file_state=shown.get("UnitFileState"),
        active_state=shown.get("ActiveState"),
        result=shown.get("Result"),
        exec_main_status=shown.get("ExecMainStatus"),
        active_enter=shown.get("ActiveEnterTimestamp") or None,
        exec_main_exit=shown.get("ExecMainExitTimestamp") or None,
    )


def usb_facts(tty: str, sysfs: str) -> UsbFacts:
    """What the step reads off the bus for this tty, found the way it finds it."""
    try:
        target = script.usb_authorized(tty, sysfs)
    except ValueError as exc:
        return UsbFacts(error=str(exc))
    device = os.path.dirname(target)

    def read(name: str) -> str | None:
        try:
            return Path(device, name).read_text(encoding="ascii").strip()
        except (OSError, UnicodeDecodeError):
            return None

    return UsbFacts(
        device=device,
        vendor=read("idVendor"),
        product=read("idProduct"),
        authorized=read("authorized"),
    )


def _log(path: str) -> tuple[bool, str | None, tuple[str, ...]]:
    try:
        info = os.stat(path)
        text = Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False, None, ()
    when = datetime.fromtimestamp(info.st_mtime, UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    return True, when, tuple(text.splitlines()[-LOG_TAIL:])


def _findings(
    files: tuple[FileCheck, ...],
    enabled: bool,
    unit: UnitState,
    devices: list[str] | None,
    receivers: tuple[ReceiverReport, ...],
    window: float,
    log_present: bool,
) -> tuple[str, ...]:
    out: list[str] = []
    if any(f.state != "current" for f in files) or not enabled:
        bad = ", ".join(f"{f.path} ({f.state})" for f in files if f.state != "current")
        out.append(
            "the installed step is not what this engine writes now"
            + (f": {bad}" if bad else " (not enabled for every sleep target)")
            + "; re-run `hammunition hardware apply`"
        )
    if unit.error is None:
        if unit.load_state == "not-found":
            out.append(f"{gps_resume.UNIT_NAME} is not installed; run `hammunition hardware apply`")
        elif unit.exec_main_status not in (None, "", "0"):
            out.append(
                f"the unit's last run exited {unit.exec_main_status} (result "
                f"{unit.result or 'unknown'}): the step found a receiver silent; "
                "see the last run's lines below"
            )
    if devices is None:
        out.append("gpsd did not answer ?DEVICES; (is gpsd.socket running?)")
    for r in receivers:
        if r.listed_by_gpsd is False:
            out.append(f"gpsd does not list {r.node}")
        if r.data_seconds is None and devices is not None:
            out.append(f"{r.node} was silent for {window:g} s")
        if r.usb.error is not None:
            out.append(
                f"{r.node}: the step could not find the receiver's USB device ({r.usb.error})"
            )
    if not log_present and all(f.state == "current" for f in files):
        out.append(
            "no log of a last run: the step has not run since boot (suspend once, then re-run this)"
        )
    return tuple(out)


def gather(
    *,
    dev: str = "/dev",
    sysfs: str = "/sys",
    host: str = "127.0.0.1",
    port: int = 2947,
    timeout: float = 2.0,
    data_window: float = 10.0,
    systemctl: str = "/usr/bin/systemctl",
    log_path: str | None = None,
) -> ResumeReport:
    """Read everything; change nothing."""
    script_file = _compare(gps_resume.SCRIPT, gps_resume.script_content())
    if script_file.state == "current" and not gps_resume._script_executable():
        script_file = FileCheck(gps_resume.SCRIPT, "wrong-mode")
    files = (
        script_file,
        _compare(gps_resume.unit_path(), gps_resume.unit_content()),
        _compare(gps_resume.TMPFILES, gps_resume.tmpfiles_content()),
    )
    enabled = all(Path(link).is_symlink() for link in gps_resume.wants_links())
    unit = unit_state(systemctl)
    found = script.receivers(Path(dev))
    devices = script.devices(host, port, timeout)

    names = {
        i: {link, node, os.path.realpath(node), os.path.realpath(link)}
        for i, (link, node) in enumerate(found)
    }
    seen = script.watch(host, port, names, data_window) if found else {}
    receivers = tuple(
        ReceiverReport(
            link=link,
            node=node,
            listed_by_gpsd=None if devices is None else (link in devices or node in devices),
            data_seconds=seen.get(i),
            usb=usb_facts(os.path.basename(node), sysfs),
        )
        for i, (link, node) in enumerate(found)
    )
    where = gps_resume.LOG if log_path is None else log_path
    present, modified, lines = _log(where)
    return ResumeReport(
        files=files,
        enabled=enabled,
        unit=unit,
        gpsd_devices=devices,
        receivers=receivers,
        data_window=data_window,
        log_path=where,
        log_present=present,
        log_modified=modified,
        log_lines=lines,
        findings=_findings(files, enabled, unit, devices, receivers, data_window, present),
    )
