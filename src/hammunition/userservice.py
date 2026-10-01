# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""Planning and rendering the rig user service.  D-073 §6.

Pure: given a manifest's ``user_services`` block, the station, and the hardware
catalog, it decides what to render, defer or skip, and produces the unit-file
text. The engine (``execute.py``) writes it as the operator and enables it; the
plan view (``interface/plan.py``) discloses it. Nothing here touches the
filesystem or systemd.

The unit file is rendered from fixed fields — the catalog never carries unit
syntax (D-073 §6). A station value is substituted into ``exec`` and re-checked
by the same rule the schema enforces, so a value that slipped a shell character
past ``station set`` cannot reach ``ExecStart=``.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING

from hammunition.manifest.schema import STATION_REF, UserService
from hammunition.rig import RigError, resolve_rig
from hammunition.station import Station

if TYPE_CHECKING:
    from hammunition.manifest.hardware import DeviceClass, DeviceManifest
    from hammunition.manifest.schema import PackageManifest
    from hammunition.plan import Deferral

__all__ = [
    "HEADER",
    "PlanUserServiceError",
    "PlannedUserService",
    "device_unit_name",
    "plan_user_services",
    "render_unit_file",
]

#: The first line of every unit file the engine writes. Uninstall removes a
#: file only when it still starts with this (D-073 §6d): a file the operator
#: rewrote is left in place and named.
HEADER = "# Written by Hammunition (catalog unit `rig-service`, D-073)."

#: Characters systemd leaves unescaped in a path-derived unit name. ``/`` is
#: handled separately (it becomes ``-``); everything else outside this set,
#: ``-`` included, becomes ``\xNN``. A leading ``.`` is escaped too.
_UNIT_SAFE = set("0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ:_.")


class PlanUserServiceError(ValueError):
    """A user service cannot be rendered — a value failed the post-substitution
    safety check. A bug or a tampered station file, never ordinary input."""


@dataclass(frozen=True)
class PlannedUserService:
    """One user service this plan will write and enable."""

    name: str
    description: str
    exec_argv: tuple[str, ...]
    unit_body: str
    device_path: str | None
    """The resolved ``binds_to_device`` path, or None. The service's restart is
    conditional on this being present."""
    filled_from: tuple[str, ...]
    """The station values that fed it, named for the plan's disclosure."""
    listens: tuple[tuple[str, int], ...]


def device_unit_name(path: str) -> str:
    """systemd's device unit name for a ``/dev`` path, e.g.
    ``dev-serial-by\\x2did-...\\x2dport0.device`` — the same escaping
    ``systemd-escape --path --suffix=device`` produces, done in pure Python so
    it is testable and no subprocess runs."""
    stripped = path.strip("/")
    out: list[str] = []
    for index, char in enumerate(stripped):
        if char == "/":
            out.append("-")
        elif char in _UNIT_SAFE and not (char == "." and index == 0):
            out.append(char)
        else:
            out.append(f"\\x{ord(char):02x}")
    return "".join(out) + ".device"


def render_unit_file(
    name: str, description: str, exec_argv: Sequence[str], device_unit: str | None
) -> str:
    """The systemd user unit, rendered from fixed fields.  D-073 §5."""
    exec_line = " ".join(exec_argv)
    lines = [
        HEADER,
        "# Changed by `hammunition station set` then `hammunition install rig-service`;",
        "# removed by `hammunition uninstall rig-service`. Do not edit: a reinstall",
        "# replaces this file whole.",
        "[Unit]",
        f"Description={description}",
    ]
    if device_unit is not None:
        lines += [f"BindsTo={device_unit}", f"After={device_unit}"]
    # A start limit so a service that cannot start — the user manager still
    # lacking `dialout`, the binary gone — stops after five tries in half a
    # minute rather than restarting forever (review minor).
    lines += ["StartLimitIntervalSec=30", "StartLimitBurst=5"]
    lines += [
        "",
        "[Service]",
        f"ExecStart={exec_line}",
        "Restart=on-failure",
        "RestartSec=5",
        "NoNewPrivileges=yes",
        "",
        "[Install]",
        "WantedBy=default.target",
    ]
    if device_unit is not None:
        lines.append(f"WantedBy={device_unit}")
    return "\n".join(lines) + "\n"


def _matches(conditions: Mapping[str, str], facts: Mapping[str, str]) -> bool:
    """True when every key in *conditions* equals the fact under it."""
    return all(facts.get(key) == value for key, value in conditions.items())


def _substitute(word: str, values: Mapping[str, str], interpreter: str) -> str:
    """Replace every ``{station.*}`` and ``{python}`` in *word*, re-checking the
    result is one safe argv word. A reference with no value is a bug (the caller
    decides what is needed before calling); an unsafe result raises."""

    def repl(match: re.Match[str]) -> str:
        key = match.group(1)
        if key not in values:
            raise PlanUserServiceError(f"no value for {{station.{key}}}")
        return values[key]

    result = STATION_REF.sub(repl, word).replace("{python}", interpreter)
    # A quote or backslash is as much a shell token to systemd as the others;
    # RIG_DEVICE already excludes them, this is defence in depth (review minor).
    if any(c in result for c in " \t\n\r;|&$`%<>\"'\\"):
        raise PlanUserServiceError(
            f"substituted exec word {result!r} carries a shell character or whitespace; "
            f"refusing to write it into a unit file (D-073 §6a)"
        )
    return result


def _needed(kind: str) -> tuple[str, ...]:
    """The station values a rig of *kind* needs before its service renders."""
    if kind == "cat":
        return ("rig_device", "rig_baud")
    return ("rig_device", "rig_ptt_line")


def plan_user_services(
    manifest: PackageManifest,
    station: Station,
    devices: Mapping[str, DeviceManifest | DeviceClass],
    *,
    model_lister: Callable[[], Mapping[int, tuple[int, int]]] | None = None,
    interpreter: str | None = None,
) -> tuple[list[PlannedUserService], list[Deferral], list[str]]:
    """Plan *manifest*'s user services against *station*.

    Returns ``(planned, deferrals, notes)``: services to render, D-035
    deferrals for a missing value or a rig no longer catalogued, and operator
    notes for a skipped service (flrig, VOX) or an unmeasured radio.

    ``interpreter`` fills ``{python}`` in an exec (the loopback filter runs
    under the engine's own interpreter); it defaults to :data:`sys.executable`.
    """
    import sys

    from hammunition.plan import Deferral

    python = interpreter or sys.executable

    if not manifest.user_services:
        return [], [], []

    first = manifest.user_services[0].name
    if station.rig is None:
        return (
            [],
            [
                Deferral(
                    subject=manifest.name,
                    what=f"will not run {first}",
                    why="station values not set: rig, rig_device",
                    remedy=(
                        "run `hammunition station set --rig <device> --rig-device <path>` "
                        "(and --rig-baud or --rig-ptt-line for the rig's kind)"
                    ),
                )
            ],
            [],
        )

    try:
        res = resolve_rig(station.rig, devices, model_lister=model_lister)
    except RigError as exc:
        return (
            [],
            [
                Deferral(
                    subject=manifest.name,
                    what=f"will not run {first}",
                    why=f"the rig {station.rig!r} is no longer in the catalog: {exc}",
                    remedy="pick a rig `hammunition list` shows, or hamlib:<model>",
                )
            ],
            [],
        )

    facts = {
        "rig_kind": res.kind,
        "rig_owner": station.rig_owner or "rigctld",
        "rig_ptt_line": station.rig_ptt_line or "",
    }
    values: dict[str, str] = {}
    if station.rig_device is not None:
        values["rig_device"] = station.rig_device
    if station.rig_baud is not None:
        values["rig_baud"] = str(station.rig_baud)
    if res.hamlib_model is not None:
        values["rig_hamlib_model"] = str(res.hamlib_model)
    if station.rig_ptt_line is not None:
        values["rig_ptt_line_hamlib"] = station.rig_ptt_line.upper()

    planned: list[PlannedUserService] = []
    deferrals: list[Deferral] = []
    notes: list[str] = []

    # Which entries this station selects — all of the matching kind, not yet
    # rendered. The rigctld service and its loopback filter are rendered
    # together, so the missing-value and skip decisions are made once over the
    # group, not once per entry (a single deferral line, spec §6b).
    selected = [svc for svc in manifest.user_services if _matches(svc.when_station, facts)]
    # An entry is skipped only by a non-empty unless_station that matches: an
    # empty one means "nothing excludes this", never "always skip" (review
    # minor). The group is skipped only when every selected entry is.
    def _excluded(svc: UserService) -> bool:
        return bool(svc.unless_station) and _matches(svc.unless_station, facts)

    if selected and all(_excluded(svc) for svc in selected):
        if facts["rig_owner"] == "flrig":
            notes.append(f"  {manifest.name}: skipped — the station's rig is owned by flrig")
        else:
            notes.append(f"  {manifest.name}: skipped — the rig is keyed by VOX, nothing to run")
        return planned, deferrals, notes

    # The needed values are station attributes, checked on the station itself —
    # not the substitution dict, which holds derived names.
    missing_station = [v for v in _needed(res.kind) if getattr(station, v) in (None, "")]
    if missing_station:
        deferrals.append(
            Deferral(
                subject=manifest.name,
                what=f"will not run {first}",
                why="station values not set: " + ", ".join(missing_station),
                remedy="run `hammunition station set "
                + " ".join(f"--{m.replace('_', '-')} …" for m in missing_station)
                + "`",
            )
        )
        return planned, deferrals, notes

    for svc in selected:
        exec_argv = tuple(_substitute(word, values, python) for word in svc.exec)
        filled = _station_sources(svc, res)
        device_path = station.rig_device if svc.binds_to_device else None
        device_unit = device_unit_name(device_path) if device_path else None
        body = render_unit_file(svc.name, svc.description, exec_argv, device_unit)
        planned.append(
            PlannedUserService(
                name=svc.name,
                description=svc.description,
                exec_argv=exec_argv,
                unit_body=body,
                device_path=device_path,
                filled_from=filled,
                listens=tuple((lst.address, lst.port) for lst in svc.listens),
            )
        )
    if res.uncatalogued:
        notes.append(
            f"  {manifest.name}: radio {station.rig} has no manifest; its USB shape, "
            f"ports and known problems are unmeasured here"
        )
    if res.kind == "ptt_only":
        notes.append(
            f"  {manifest.name}: no frequency control — programs see the dummy model's "
            f"frequency; start with the radio off or on a dummy load (opening the port "
            f"may key it)"
        )

    return planned, deferrals, notes


def _station_sources(svc: UserService, res: object) -> tuple[str, ...]:
    """The station values that fed a service, for the plan's 'filled from' line:
    the stored values its exec references, mapped from the derived names back to
    what the operator set."""
    stored: set[str] = {"rig"}
    for key in svc.station_variables:
        if key == "rig_hamlib_model":
            stored.add("rig")
        elif key == "rig_ptt_line_hamlib":
            stored.add("rig_ptt_line")
        elif key.startswith("rig_"):
            stored.add(key)
    return tuple(sorted(stored))
