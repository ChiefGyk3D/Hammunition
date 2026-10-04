# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""``hardware gps-resume-report`` as data.  D-059, issue #177.

Everything in it is read: files, ``systemctl show``, gpsd's socket and sysfs.
Nothing is written, nothing is keyed and no power state changes.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar

from hammunition.interface.envelope import Strict, described

if TYPE_CHECKING:
    from hammunition.hardware.gps_resume_report import ResumeReport

__all__ = ["GpsResumeReportDocument", "build_gps_resume_report", "render_gps_resume_report"]


@dataclass(frozen=True)
class FileView(Strict):
    """One file the resume step installs, compared with what this engine would write now."""

    path: str = described("where it is installed")
    state: str = described(
        "`current` (byte for byte what this engine writes), `differs`, `wrong-mode` (the script "
        "is not 0755), `absent` or `unreadable`"
    )


@dataclass(frozen=True)
class UnitView(Strict):
    """``systemctl show`` of the resume unit; no privilege needed."""

    load_state: str | None = described(
        "`loaded` or `not-found`; null when systemctl did not answer"
    )
    unit_file_state: str | None = described("`enabled`, `disabled`, ...; null when unknown")
    active_state: str | None = described("`inactive` between runs is normal for a oneshot")
    result: str | None = described("`success` or what failed")
    exec_main_status: str | None = described("the script's last exit status; 0 when data was seen")
    active_enter: str | None = described("when the unit last became active, as systemd prints it")
    exec_main_exit: str | None = described("when the script last exited, as systemd prints it")
    error: str | None = described("why systemctl could not be asked, when it could not")


@dataclass(frozen=True)
class UsbView(Strict):
    """The receiver's own USB device, found as the resume step finds it."""

    device: str | None = described("the sysfs device directory; null when it was not found")
    vendor: str | None = described("idVendor")
    product: str | None = described("idProduct")
    authorized: str | None = described("the `authorized` file's content (1 is on)")
    error: str | None = described("why the step could not find it, when it could not")


@dataclass(frozen=True)
class ReceiverView(Strict):
    """One /dev/gpsN and what gpsd and the bus say about it."""

    link: str = described("the /dev/gpsN link")
    node: str = described("the device node it names")
    listed_by_gpsd: bool | None = described(
        "gpsd's ?DEVICES; lists it; null when gpsd did not answer"
    )
    data_seconds: float | None = described(
        "seconds until the first SKY or TPV report in the data window; null when silent"
    )
    usb: UsbView = described("the USB facts the step relies on")


@dataclass(frozen=True)
class GpsResumeReportDocument(Strict):
    """Whether the GPS resume step is installed as this engine writes it, what its
    last run did, and whether the receiver is delivering data now."""

    KIND: ClassVar[str] = "gps-resume-report"

    files: tuple[FileView, ...] = described("the script, the unit and the tmpfiles line")
    enabled: bool = described("the unit is wanted by all four sleep targets")
    unit: UnitView = described("the unit's state")
    gpsd_answered: bool = described("gpsd answered ?DEVICES;")
    gpsd_devices: tuple[str, ...] = described("the paths gpsd lists")
    receivers: tuple[ReceiverView, ...] = described("each /dev/gpsN; empty when none is attached")
    data_window: float = described("seconds the data check watched for")
    log_path: str = described("where the step writes its last run's lines")
    log_present: bool = described("the log exists; /run is cleared at boot")
    log_modified: str | None = described("the log's modification time, UTC; null when absent")
    log_lines: tuple[str, ...] = described("the last run's lines, newest last, at most 40")
    findings: tuple[str, ...] = described("what is wrong and what to run; empty when nothing is")


def build_gps_resume_report(report: ResumeReport) -> GpsResumeReportDocument:
    return GpsResumeReportDocument(
        files=tuple(FileView(path=f.path, state=f.state) for f in report.files),
        enabled=report.enabled,
        unit=UnitView(
            load_state=report.unit.load_state,
            unit_file_state=report.unit.unit_file_state,
            active_state=report.unit.active_state,
            result=report.unit.result,
            exec_main_status=report.unit.exec_main_status,
            active_enter=report.unit.active_enter,
            exec_main_exit=report.unit.exec_main_exit,
            error=report.unit.error,
        ),
        gpsd_answered=report.gpsd_devices is not None,
        gpsd_devices=tuple(report.gpsd_devices or ()),
        receivers=tuple(
            ReceiverView(
                link=r.link,
                node=r.node,
                listed_by_gpsd=r.listed_by_gpsd,
                data_seconds=r.data_seconds,
                usb=UsbView(
                    device=r.usb.device,
                    vendor=r.usb.vendor,
                    product=r.usb.product,
                    authorized=r.usb.authorized,
                    error=r.usb.error,
                ),
            )
            for r in report.receivers
        ),
        data_window=report.data_window,
        log_path=report.log_path,
        log_present=report.log_present,
        log_modified=report.log_modified,
        log_lines=tuple(report.log_lines),
        findings=tuple(report.findings),
    )


def _dash(value: object) -> str:
    return "-" if value is None else str(value)


def render_gps_resume_report(doc: GpsResumeReportDocument) -> list[str]:
    """A plain table, as the terminal shows it."""
    lines = ["GPS resume step (issue #177)", ""]
    lines.append(f"{'file':64} state")
    lines += [f"{f.path:64} {f.state}" for f in doc.files]
    lines.append(f"{'unit enabled for the four sleep targets':64} {'yes' if doc.enabled else 'no'}")
    u = doc.unit
    lines += ["", "Unit (systemctl show)"]
    if u.error is not None:
        lines.append(f"  could not ask systemctl: {u.error}")
    else:
        for label, value in (
            ("LoadState", u.load_state),
            ("UnitFileState", u.unit_file_state),
            ("ActiveState", u.active_state),
            ("Result", u.result),
            ("ExecMainStatus", u.exec_main_status),
            ("ActiveEnterTimestamp", u.active_enter),
            ("ExecMainExitTimestamp", u.exec_main_exit),
        ):
            lines.append(f"  {label:22} {_dash(value) if value != '' else '-'}")
    lines += ["", "gpsd"]
    if not doc.gpsd_answered:
        lines.append("  ?DEVICES; got no answer on 127.0.0.1:2947")
    else:
        lines.append(f"  ?DEVICES; lists {', '.join(doc.gpsd_devices) or 'no device'}")
    if not doc.receivers:
        lines.append("  no /dev/gpsN: no receiver attached, or it is parked")
    for r in doc.receivers:
        listed = {True: "yes", False: "no", None: "unknown"}[r.listed_by_gpsd]
        data = (
            f"data within {r.data_seconds:.0f} s"
            if r.data_seconds is not None
            else f"silent for {doc.data_window:g} s"
        )
        lines.append(f"  {r.link} -> {r.node}: listed {listed}; {data}")
        if r.usb.error is not None:
            lines.append(f"    USB: {r.usb.error}")
        else:
            lines.append(
                f"    USB: {_dash(r.usb.vendor)}:{_dash(r.usb.product)} at {_dash(r.usb.device)}, "
                f"authorized={_dash(r.usb.authorized)}"
            )
    lines += [
        "",
        f"Last run ({doc.log_path}" + (f", {doc.log_modified})" if doc.log_present else ")"),
    ]
    if doc.log_present:
        lines += [f"  {line}" for line in doc.log_lines] or ["  (empty)"]
    else:
        lines.append(
            "  no log: the step has not run since boot (/run is cleared then), or it was "
            "installed before it kept one"
        )
    lines += [""]
    if doc.findings:
        lines.append("Findings")
        lines += [f"  - {f}" for f in doc.findings]
    else:
        lines.append("Nothing to fix: the step is current and the receiver is delivering data.")
    return lines
