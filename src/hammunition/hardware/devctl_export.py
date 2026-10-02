# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""The two lists ``hardware apply`` exports for the tray's helper.  D-056 amended.

The privileged helper moved to ``hammunition-tray`` (D-056, amended
2026-10-02), and the catalog stayed here. The helper therefore reads two data
files this engine writes, instead of importing the engine's catalog and its
``systemctl`` knowledge:

- ``/etc/hammunition/devctl-devices.yaml``: every catalogued class or device
  that carries ``power_control``, with what ``state`` needs to recognise it on
  the USB bus from the file alone (name, summary, method, quiet verbs, and each
  confirmed identifier as quoted ``vendor``/``product`` strings, with
  ``product_string`` for an ambiguous identifier the catalog has read one for).
  The shapes are hammunition-tray's contract 1.
- ``/etc/hammunition/devctl-services.yaml``: the system services the helper may
  start, stop, enable and disable by name: ``gpsd`` (its socket), ``time``
  (the daemon the station's GPS time uses) and ``gps-resume``.

**Allow-lists are data, never arguments** (the contract's D7). A name the files
do not carry is refused by name by the helper; the engine never passes a unit.

Both are root-owned 0644, staged and installed by ``install -D`` (the route the
helper takes, D-056), disclosed whole in the plan, read back afterwards
(D-031), and removed by content. The foreign-file check is made at plan time and
``install -D`` replaces whatever is at the path when it runs; ``/etc/hammunition``
is root's, so only root could race the two, and nothing here pretends otherwise.
Removal is by content: a file is removed only when it starts with the
header Hammunition writes, and a file at either path without that header
refuses the plan. ``/etc/hammunition`` itself is never removed: ``time.yaml``
lives there (D-058).

Nothing here takes a station value, and none can reach either file.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import yaml

from hammunition.backends.base import Command
from hammunition.hardware import gps_resume
from hammunition.manifest.hardware import DeviceClass, DeviceManifest

__all__ = [
    "CHRONYD",
    "DEVICES_PATH",
    "HEADER",
    "PATHS",
    "SERVICES_PATH",
    "VERSION",
    "DevctlExport",
    "DevctlExportError",
    "DevctlExportRemoval",
    "detect_time_unit",
    "devices_content",
    "disclose",
    "install_commands",
    "plan_devctl_export",
    "plan_removal",
    "removal_commands",
    "services_content",
    "stage",
    "verify",
    "verify_removal",
]

VERSION = 1
"""The file shapes' version, the first key of each file. A reader refuses a
version it does not know, by name."""

DEVICES_PATH = "/etc/hammunition/devctl-devices.yaml"
SERVICES_PATH = "/etc/hammunition/devctl-services.yaml"
CHRONYD = "/usr/sbin/chronyd"
"""chrony's daemon. Where it is, and ntpsec's is not, the ``time`` row names chrony."""

PATHS: dict[str, str] = {
    "DEVICES_PATH": DEVICES_PATH,
    "SERVICES_PATH": SERVICES_PATH,
    "CHRONYD": CHRONYD,
}
"""Each path attribute and its real default, for the fixtures that repoint them.
Read as module globals at call time, so a test's ``monkeypatch.setattr`` holds."""

HEADER = "# Written by `hammunition hardware apply` (D-056, amended 2026-10-02)."
_STAGED_DEVICES = "devctl-devices.yaml"
_STAGED_SERVICES = "devctl-services.yaml"


class DevctlExportError(Exception):
    """A file at one of the two paths that Hammunition did not write."""


def _preamble(what: str) -> str:
    return (
        f"{HEADER} {what}\n"
        "# Read by hammunition-devctl, the tray's privileged helper. Do not edit:\n"
        "# `hammunition hardware apply` rewrites it and `hammunition hardware unapply`\n"
        "# removes it.\n"
    )


def _q(text: str) -> str:
    """A YAML double-quoted scalar. JSON's string syntax is a subset of it, so an
    identifier like ``0003`` or ``1e10`` is always a string and never a number,
    whatever the reader's YAML version."""
    return json.dumps(text, ensure_ascii=False)


def devices_content(classes: dict[str, DeviceClass], devices: dict[str, DeviceManifest]) -> str:
    """The devices file: every entry with ``power_control``, by name.

    The shape is hammunition-tray's contract 1 (``docs/contract.md`` there): each
    confirmed identifier is ``vendor`` and ``product`` (absent when the entry
    matches a whole vendor), plus ``product_string`` only for an identifier the
    catalog marks ambiguous and has read a product string for. That is exactly
    what :func:`hammunition.hardware.detect.match_catalog` compares, so the
    helper recognises what the engine does. ``Match.ambiguous`` and the
    distinctiveness of a string are the engine's report on how sure a match is
    and change nothing about whether a device may be parked (D-056), so neither
    is exported.
    """
    every: dict[str, DeviceClass | DeviceManifest] = {**classes, **devices}
    lines = ["version: 1"]
    rows: list[list[str]] = []
    for name in sorted(every):
        entry = every[name]
        if entry.power_control is None:
            continue
        row = [
            f"  - name: {_q(entry.name)}",
            f"    summary: {_q(entry.summary)}",
            f"    method: {_q(str(entry.power_control.method))}",
        ]
        quiet = [str(verb) for verb in entry.power_control.quiet]
        if quiet:
            row.append("    quiet:")
            row += [f"      - {_q(verb)}" for verb in quiet]
        else:
            row.append("    quiet: []")
        ids = [u for u in entry.usb_ids if u.confirmed]  # an unconfirmed id names nothing
        if not ids:
            row.append("    usb_ids: []")
        else:
            row.append("    usb_ids:")
            for usb_id in ids:
                row.append(f"      - vendor: {_q(usb_id.vendor.lower())}")
                if usb_id.product:
                    row.append(f"        product: {_q(usb_id.product.lower())}")
                if usb_id.ambiguity is not None and usb_id.product_string:
                    row.append(f"        product_string: {_q(usb_id.product_string)}")
        rows.append(row)
    if rows:
        lines.append("devices:")
        for row in rows:
            lines += row
    else:
        lines.append("devices: []")
    return _preamble("The devices the helper may park and wake.") + "\n".join(lines) + "\n"


def detect_time_unit() -> tuple[str, bool]:
    """The time daemon's unit, and whether one was found.

    ntpsec first: it is the daemon D-058's GPS time disciplines, so where both
    exist ntpsec is the station's time path. chrony where only it exists
    (D-072). Neither found names ntpsec anyway, the daemon the project's own
    time path is written for, and the helper reports it not installed rather
    than the row being missing.
    """
    from hammunition.gpstime import state as time_state

    if time_state.ntpsec_installed():
        return "ntpsec.service", True
    if Path(CHRONYD).is_file():
        return "chrony.service", True
    return "ntpsec.service", False


def services_content(unit: str) -> str:
    """The services file: the system units the helper may start, stop, enable, disable."""
    rows = [
        {
            "name": "gpsd",
            "unit": "gpsd.socket",
            "scope": "system",
            "description": "the GPS daemon (socket-activated)",
        },
        {
            "name": "time",
            "unit": unit,
            "scope": "system",
            "description": "the clock: the daemon GPS time feeds",
        },
        {
            "name": "gps-resume",
            "unit": gps_resume.UNIT_NAME,
            "scope": "system",
            "description": "re-adds the receiver to gpsd after sleep",
        },
    ]
    body = yaml.safe_dump(
        {"version": VERSION, "services": rows},
        sort_keys=False,
        default_flow_style=False,
        allow_unicode=True,
        width=100,
    )
    return _preamble("The system services the helper may start, stop, enable and disable.") + body


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


def _ours(text: str | None) -> bool:
    """Our header on the first line. The opening words only, so an older engine's
    file is still ours."""
    return text is not None and text.startswith(HEADER)


@dataclass(frozen=True)
class DevctlExport:
    """What ``hardware apply`` will do for the two lists."""

    devices: str
    """The complete devices file the apply will write."""
    services: str
    """The complete services file the apply will write."""
    devices_current: bool
    services_current: bool
    time_unit: str
    time_found: bool
    """False when no time daemon was found and ``time_unit`` is the default."""
    device_names: tuple[str, ...]

    @property
    def is_noop(self) -> bool:
        return self.devices_current and self.services_current


def _refuse_foreign(path: str, text: str | None) -> None:
    if text is not None and not _ours(text):
        raise DevctlExportError(
            f"{path} exists and was not written by Hammunition, or could not be read by this "
            f"account. `hardware apply` writes the helper's device and service lists there "
            f"and never overwrites a file it did not write. Move it aside and re-run. "
            f"Nothing was changed."
        )


def plan_devctl_export(
    classes: dict[str, DeviceClass],
    devices: dict[str, DeviceManifest],
    *,
    time_unit: str | None = None,
    time_found: bool = True,
) -> DevctlExport:
    """Read what is installed. Raises :class:`DevctlExportError` on a foreign file.

    ``time_unit`` overrides detection (for tests and for a caller that has
    already read it).
    """
    if time_unit is None:
        unit, found = detect_time_unit()
    else:
        unit, found = time_unit, time_found
    devices_text = devices_content(classes, devices)
    services_text = services_content(unit)
    current_devices = _read(DEVICES_PATH)
    current_services = _read(SERVICES_PATH)
    _refuse_foreign(DEVICES_PATH, current_devices)
    _refuse_foreign(SERVICES_PATH, current_services)
    names = tuple(
        sorted(e.name for e in {**classes, **devices}.values() if e.power_control is not None)
    )
    return DevctlExport(
        devices=devices_text,
        services=services_text,
        devices_current=current_devices == devices_text,
        services_current=current_services == services_text,
        time_unit=unit,
        time_found=found,
        device_names=names,
    )


def disclose(step: DevctlExport) -> list[str]:
    if step.is_noop:
        return []
    lines = [
        "Will write the lists the tray's helper reads (D-056, amended). The helper is no longer",
        "  this engine's; it starts and stops only the services named in the second file and",
        "  parks only the devices named in the first, and it takes a name, never a path or a unit.",
        f"  Devices exported: {', '.join(step.device_names) or 'none'}.",
    ]
    if not step.time_found:
        lines.append(
            "  No time daemon was found (neither ntpsec nor chrony): the `time` row names "
            f"{step.time_unit}, and the helper reports it not installed until one is."
        )
    else:
        lines.append(f"  The `time` row names {step.time_unit}, the daemon this machine has.")
    if not step.devices_current:
        lines += [
            f"  {DEVICES_PATH} (root-owned 0644):",
            *(f"    {line}" for line in step.devices.splitlines()),
        ]
    if not step.services_current:
        lines += [
            f"  {SERVICES_PATH} (root-owned 0644):",
            *(f"    {line}" for line in step.services.splitlines()),
        ]
    lines += [
        f"  Inspect: `cat {DEVICES_PATH} {SERVICES_PATH}`, and what the helper makes of them with",
        "  `hammunition services` and `hammunition hardware state`.",
        "  Reverse: `hammunition hardware unapply` removes both, and only if Hammunition wrote them.",
    ]
    return lines


def stage(step: DevctlExport, staging_dir: Path) -> None:
    if not step.devices_current:
        (staging_dir / _STAGED_DEVICES).write_text(step.devices, encoding="utf-8")
    if not step.services_current:
        (staging_dir / _STAGED_SERVICES).write_text(step.services, encoding="utf-8")


def install_commands(step: DevctlExport, staging_root: str) -> list[Command]:
    out: list[Command] = []
    if not step.devices_current:
        out.append(
            Command(
                argv=(
                    "install",
                    "-D",
                    "-m",
                    "0644",
                    f"{staging_root}/{_STAGED_DEVICES}",
                    DEVICES_PATH,
                ),
                description=f"Install the helper's device list to {DEVICES_PATH}",
                requires_root=True,
            )
        )
    if not step.services_current:
        out.append(
            Command(
                argv=(
                    "install",
                    "-D",
                    "-m",
                    "0644",
                    f"{staging_root}/{_STAGED_SERVICES}",
                    SERVICES_PATH,
                ),
                description=f"Install the helper's service list to {SERVICES_PATH}",
                requires_root=True,
            )
        )
    return out


def verify(step: DevctlExport) -> list[str]:
    """D-031: the files read back, not the exit codes."""
    problems: list[str] = []
    for path, want in ((DEVICES_PATH, step.devices), (SERVICES_PATH, step.services)):
        text = _read(path)
        if text is None:
            problems.append(f"{path} is missing after the install")
        elif text != want:
            problems.append(f"{path} on disk does not match what we wrote")
    return problems


@dataclass(frozen=True)
class DevctlExportRemoval:
    devices_ours: bool
    services_ours: bool

    @property
    def is_empty(self) -> bool:
        return not (self.devices_ours or self.services_ours)


def plan_removal() -> DevctlExportRemoval:
    """By content, not by the log: only a file that starts with our header."""
    return DevctlExportRemoval(
        devices_ours=_ours(_read(DEVICES_PATH)),
        services_ours=_ours(_read(SERVICES_PATH)),
    )


def removal_commands(removal: DevctlExportRemoval) -> list[Command]:
    out: list[Command] = []
    if removal.devices_ours:
        out.append(
            Command(
                argv=("rm", "-f", DEVICES_PATH),
                description=f"Remove {DEVICES_PATH}, written by Hammunition (D-056)",
                requires_root=True,
            )
        )
    if removal.services_ours:
        out.append(
            Command(
                argv=("rm", "-f", SERVICES_PATH),
                description=f"Remove {SERVICES_PATH}, written by Hammunition (D-056)",
                requires_root=True,
            )
        )
    return out


def verify_removal(removal: DevctlExportRemoval) -> list[str]:
    problems: list[str] = []
    if removal.devices_ours and Path(DEVICES_PATH).exists():
        problems.append(f"{DEVICES_PATH} is still present")
    if removal.services_ours and Path(SERVICES_PATH).exists():
        problems.append(f"{SERVICES_PATH} is still present")
    return problems
