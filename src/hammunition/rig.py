# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""Resolving the station's rig against the catalog and this machine's hamlib.

The station module stays free of the hardware catalog (D-073 §4): it validates
only the *shape* a value needs. This module is where a ``rig`` value becomes a
hamlib model, a kind and a baud range — by looking the device up in the
catalog, or, for ``hamlib:<model>``, by asking this machine's hamlib. Pure and
injectable: the catalog comes in as a mapping and the model list as a callable,
so nothing here shells out in a test.
"""

from __future__ import annotations

import re
import subprocess
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Literal

from hammunition.manifest.hardware import DeviceClass, DeviceManifest

__all__ = [
    "RigError",
    "RigResolution",
    "check_rig_baud",
    "elide_serial",
    "hamlib_models",
    "parse_dump_state_model",
    "resolve_rig",
]

#: Matches the serial run in a /dev/serial/by-id/ name so it can be elided for
#: any surface but the operator's own screen (D-073 §4). udev composes a by-id
#: name as usb-<vendor>_<product>_<serial>-if<NN>-port<N>; the serial is the
#: last underscore-separated field before the -if suffix.
_BY_ID_SERIAL = re.compile(r"(usb-[^\s/]+?_)([^_/\s]+)(-if[0-9a-f]{2}(?:-port[0-9]+)?)")

_HamlibModels = Mapping[int, tuple[int, int]]


class RigError(ValueError):
    """A rig value cannot be resolved: not a rig, or a model this machine lacks."""


@dataclass(frozen=True)
class RigResolution:
    """What a ``rig`` station value resolves to, for the plan and ``station set``."""

    kind: Literal["cat", "ptt_only"]
    hamlib_model: int | None
    baud_range: tuple[int, int] | None
    manifest_name: str | None
    """The catalog device id, or None for an uncatalogued ``hamlib:<model>``."""
    uncatalogued: bool = False


def hamlib_models(*, runner: Callable[[list[str]], str] | None = None) -> _HamlibModels:
    """Every rig model this machine's hamlib knows, mapped to a baud range.

    Reads ``rigctl -l`` (the model numbers) only. The speed for an uncatalogued
    ``hamlib:<model>`` is **not** range-checked against its backend here: each
    model's range would be a separate ``rigctl -m <model> -u`` whose output
    this project has not measured to parse across 300-plus backends, so the
    pair carried is a nominal ``(300, 921600)`` and the real check is the one
    the backend makes when ``rigctld`` opens the port. The operator supplies the
    speed from the radio's menu, and a wrong speed is silence, not an error
    (D-073 §4). Injectable for tests. Raises ``FileNotFoundError`` when
    ``rigctl`` is absent; :func:`resolve_rig` turns that into a ``RigError``.
    """
    run = runner or _run
    out = run(["rigctl", "-l"])
    models: dict[int, tuple[int, int]] = {}
    for line in out.splitlines():
        head = line.strip().split()
        if head and head[0].isdigit():
            models[int(head[0])] = (300, 921600)
    return models


def _run(argv: list[str]) -> str:
    result = subprocess.run(argv, capture_output=True, text=True, check=False)
    return result.stdout


def resolve_rig(
    value: str,
    devices: Mapping[str, DeviceManifest | DeviceClass],
    *,
    model_lister: Callable[[], _HamlibModels] | None = None,
) -> RigResolution:
    """Resolve a ``rig`` station value, or raise :class:`RigError`.

    A catalogued device is taken from its ``rig`` block. ``hamlib:<model>`` is
    checked against this machine's hamlib (``model_lister``, injectable), with
    the baud range taken from the model list; a model this machine does not
    list is refused, because a service for a model hamlib cannot load would
    fail at start with nothing to read it.
    """
    if value.startswith("hamlib:"):
        tail = value.split(":", 1)[1]
        if not tail.isdigit():
            raise RigError(
                f"{value!r} is not a hamlib model: give a number, e.g. hamlib:3073 "
                f"(`rigctl -l` lists them)."
            )
        model = int(tail)
        try:
            models = (model_lister or hamlib_models)()
        except FileNotFoundError:
            raise RigError(
                "rigctl is not installed, so a hamlib:<model> value cannot be checked "
                "against this machine's hamlib; install libhamlib-utils first."
            ) from None
        if model not in models:
            raise RigError(
                f"hamlib model {model} is not listed by this machine's hamlib "
                f"(`rigctl -l`). Check the number, or install a newer hamlib."
            )
        return RigResolution(
            kind="cat",
            hamlib_model=model,
            baud_range=models[model],
            manifest_name=None,
            uncatalogued=True,
        )

    device = devices.get(value)
    rig = getattr(device, "rig", None) if device is not None else None
    if device is None or rig is None:
        rigs = sorted(name for name, d in devices.items() if getattr(d, "rig", None) is not None)
        raise RigError(
            f"{value!r} is not a rig in the catalog. Catalogued rigs: "
            f"{', '.join(rigs) or '(none)'}. Or give hamlib:<model> for a radio "
            f"with no manifest."
        )
    if rig.kind == "cat":
        assert rig.cat is not None  # kind=='cat' guarantees it (schema)
        return RigResolution(
            kind="cat",
            hamlib_model=rig.hamlib_model,
            baud_range=rig.cat.baud,
            manifest_name=value,
        )
    return RigResolution(
        kind="ptt_only",
        hamlib_model=None,
        baud_range=None,
        manifest_name=value,
    )


def check_rig_baud(baud: int, baud_range: tuple[int, int]) -> str | None:
    """None if ``baud`` is inside ``baud_range``, else a sentence naming the range."""
    low, high = baud_range
    if low <= baud <= high:
        return None
    return (
        f"{baud} is outside the backend's serial-speed range {low}..{high}. "
        f"Read the radio's CAT RATE menu and give a value in that range."
    )


def elide_serial(path: str) -> str:
    """A /dev/serial/by-id/ path with the device serial replaced by ``…``.

    For the plan, doctor, status and every --json document but ``station``'s: a
    by-id path carries the device serial, the same class of identifier as a
    hostname (D-073 §4). A path with no recognisable serial run is returned
    unchanged.
    """
    return _BY_ID_SERIAL.sub(r"\1…\3", path)


def parse_dump_state_model(reply: str) -> int | None:
    """The model number from a ``\\dump_state`` reply, or None.

    hamlib's NET rigctl ``\\dump_state`` answers with the protocol version on
    the first line and the model number on the next. Used by ``doctor`` to
    confirm the daemon answers, checked against a dummy rigctld in the suite.
    """
    lines = [line.strip() for line in reply.splitlines() if line.strip()]
    # The reply opens with the protocol version on line 0; the model number is
    # the next bare-integer line. Skip line 0 by position, not by value — the
    # dummy model's version and model are both ``1``.
    for line in lines[1:]:
        if line.isdigit():
            return int(line)
    return None
