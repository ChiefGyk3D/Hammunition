# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""``services`` as data.  D-059, D-056 (amended 2026-10-02).

The privileged helper lives in hammunition-tray; its ``services state`` verb
answers one document (the contract's shape, version 1). The engine reads it,
checks it, and renders **the same dataclasses** as text and as its own
``--json`` document, so a front end that reads the engine and one that reads the
helper read one shape. The engine never asks systemd anything itself.

A field the helper adds later is ignored here, not fatal: the contract grows
by adding fields within a version. A document this parser cannot read is
refused by name, with what was wrong with it.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, ClassVar

from hammunition.interface.envelope import Strict, described

__all__ = [
    "CONTRACT_VERSION",
    "LingerView",
    "ServiceView",
    "ServicesDocument",
    "ServicesError",
    "parse_helper_services",
    "render_services",
]

CONTRACT_VERSION = 1
"""The helper contract's ``services`` document version this engine reads."""


class ServicesError(ValueError):
    """The helper's ``services state`` document could not be used."""


@dataclass(frozen=True)
class ServiceView(Strict):
    """One service the helper may start, stop, enable and disable by name."""

    name: str = described("the name `hammunition services start|stop|enable|disable` takes")
    unit: str = described("the systemd unit the name stands for, e.g. `gpsd.socket`")
    scope: str = described("`user` (the operator's own systemd) or `system`")
    description: str = described("one line, as the helper's service list words it")
    active: str = described(
        "`active`, `inactive`, `failed`, `activating` or `unknown`: what is running now"
    )
    enabled: str = described(
        "`enabled`, `disabled`, `static`, `not-found` or `unknown`: whether it starts at "
        "boot (system) or login (user). `not-found` means the unit is not installed"
    )
    root: bool = described(
        "true when changing it asks for a password (system scope); false when the "
        "helper acts for the operator alone"
    )


@dataclass(frozen=True)
class LingerView(Strict):
    """Whether the operator's user services keep running after logout."""

    state: str = described("`on` or `off`")
    ours: bool = described("true when Hammunition turned it on, so it is Hammunition's to turn off")


@dataclass(frozen=True)
class ServicesDocument(Strict):
    """The services the privileged helper may start, stop, enable and disable,
    with what each is doing now.

    Read fresh on every call, unprivileged, by asking the installed helper
    (`hammunition-devctl services state`); the engine adds nothing to it."""

    KIND: ClassVar[str] = "services"

    version: int = described("the helper contract's `services` document version; 1")
    services: tuple[ServiceView, ...] = described(
        "every service in the helper's lists, an uninstalled one included (`enabled: not-found`)"
    )
    linger: LingerView | None = described(
        "whether user services outlive the login session; null when the helper did not say"
    )


def _text(row: Mapping[str, Any], key: str, where: str) -> str:
    value = row.get(key)
    if not isinstance(value, str) or not value:
        raise ServicesError(f"the helper's services document: {where} has no text `{key}`")
    return value


def parse_helper_services(text: str) -> ServicesDocument:
    """The helper's ``services state`` output as a document, or :class:`ServicesError`."""
    try:
        raw = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ServicesError(f"the helper's services output is not JSON ({exc.msg})") from exc
    if not isinstance(raw, dict):
        raise ServicesError("the helper's services output is not a JSON object")
    if raw.get("kind") != "services":
        raise ServicesError(f"the helper's document is kind {raw.get('kind')!r}, not 'services'")
    version = raw.get("version")
    if not isinstance(version, int) or isinstance(version, bool) or version != CONTRACT_VERSION:
        raise ServicesError(
            f"the helper's services document has version {version!r}; this engine reads "
            f"version {CONTRACT_VERSION}. Update hammunition or hammunition-tray, whichever is older."
        )
    rows = raw.get("services")
    if not isinstance(rows, list):
        raise ServicesError("the helper's services document has no `services` list")
    services: list[ServiceView] = []
    seen: set[str] = set()
    for index, row in enumerate(rows):
        where = f"service {index + 1}"
        if not isinstance(row, dict):
            raise ServicesError(f"the helper's services document: {where} is not an object")
        name = _text(row, "name", where)
        if name in seen:
            raise ServicesError(f"the helper's services document names {name!r} twice")
        seen.add(name)
        root = row.get("root")
        if not isinstance(root, bool):
            raise ServicesError(f"the helper's services document: {name!r} has no boolean `root`")
        services.append(
            ServiceView(
                name=name,
                unit=_text(row, "unit", name),
                scope=_text(row, "scope", name),
                description=str(row.get("description") or ""),
                active=_text(row, "active", name),
                enabled=_text(row, "enabled", name),
                root=root,
            )
        )
    linger: LingerView | None = None
    raw_linger = raw.get("linger")
    if isinstance(raw_linger, dict):
        state = raw_linger.get("state")
        ours = raw_linger.get("ours")
        if isinstance(state, str) and isinstance(ours, bool):
            linger = LingerView(state=state, ours=ours)
    return ServicesDocument(version=version, services=tuple(services), linger=linger)


def _boot(view: ServiceView) -> str:
    if view.enabled == "not-found":
        return "not installed"
    return view.enabled


def render_services(doc: ServicesDocument) -> list[str]:
    """``services`` as the terminal shows it."""
    if not doc.services:
        return [
            "The helper lists no services. `hammunition hardware apply` writes the "
            "system ones; installing a unit that runs as a user service adds its own."
        ]
    lines = [f"{'service':12} {'scope':7} {'running':11} {'at boot/login':14} unit"]
    for s in doc.services:
        lines.append(f"{s.name:12} {s.scope:7} {s.active:11} {_boot(s):14} {s.unit}")
    lines.append("")
    for s in doc.services:
        lines.append(f"  {s.name}: {s.description}")
    if doc.linger is not None:
        lines += ["", f"Linger (user services after logout): {doc.linger.state}"]
    lines += [
        "",
        "`hammunition services start NAME`, `stop NAME`, `enable NAME` and `disable NAME` "
        + "change one. A system service asks for your password once; a user service never does.",
    ]
    return lines
