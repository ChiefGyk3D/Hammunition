# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""The tray's list of user services: ``~/.config/hammunition/devctl-services.yaml``.

hammunition-tray's helper (contract v1) reads this file to know which user
services it may start, stop, enable and disable, and never takes a unit name
from an argument. The engine writes a row when it installs a catalog unit that
has a ``user_services`` block and removes it on uninstall (D-073, amended
2026-10-02). The file is the operator's: mode 0600, written atomically, and
when root is acting for an operator it is written through the same
descriptor-relative, ``O_NOFOLLOW`` walk the other operator-home writers use.

One row per catalog unit, not per systemd unit: the rig's two services
(``rigctld`` and its loopback filter) are one row, ``rig``, naming ``rigctld``.
"""

from __future__ import annotations

import contextlib
import json
import os
import re
import stat
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import yaml

from hammunition.paths import OperatorDirError, open_operator_dir, operator_for

if TYPE_CHECKING:
    from hammunition.userservice import PlannedUserService

__all__ = [
    "FILE_NAME",
    "HEADER",
    "Row",
    "parse_rows",
    "remove_row",
    "render_rows",
    "row_for",
    "service_name",
    "update_file",
]

FILE_NAME = "devctl-services.yaml"
HEADER = "# Written by `hammunition install` (D-073, amended 2026-10-02)."

_NAME = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")


@dataclass(frozen=True)
class Row:
    name: str
    unit: str
    description: str


def service_name(catalog_unit: str) -> str:
    """The tray's name for a catalog unit: the unit name without a ``-service``
    suffix, so ``rig-service`` is ``rig`` and ``gps-tether`` stays itself."""
    return catalog_unit.removesuffix("-service")


def row_for(services: Sequence[PlannedUserService]) -> Row:
    """The row for one catalog unit's planned services (the first names it)."""
    first = services[0]
    name = service_name(first.unit)
    if not _NAME.match(name):
        raise ValueError(f"{name!r} is not a name the tray's helper accepts")
    description = _CONTROL.sub(" ", first.description)[:200]
    return Row(name, f"{first.name}.service", description)


def parse_rows(text: str) -> list[Row]:
    """The rows in *text*; raises ValueError when it is not the v1 shape."""
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ValueError(f"not YAML: {exc}") from exc
    if data is None:
        return []
    if not isinstance(data, dict) or not isinstance(data.get("services", []), list):
        raise ValueError("not a version 1 services file")
    rows: list[Row] = []
    for item in data.get("services", []):
        if not isinstance(item, dict) or not {"name", "unit", "description"} <= set(item):
            raise ValueError("a row lacks name, unit or description")
        rows.append(Row(str(item["name"]), str(item["unit"]), str(item["description"])))
    return rows


def render_rows(rows: Sequence[Row]) -> str:
    """The file's text. Strings are JSON-quoted, which is valid YAML."""
    lines = [HEADER, "version: 1", "services:"]
    for row in rows:
        lines += [
            f"  - name: {json.dumps(row.name)}",
            f"    unit: {json.dumps(row.unit)}",
            "    scope: user",
            f"    description: {json.dumps(row.description)}",
        ]
    return "\n".join(lines) + "\n"


def remove_row(rows: Sequence[Row], name: str) -> list[Row]:
    return [row for row in rows if row.name != name]


def _merged(existing: str | None, add: Row | None, remove_name: str | None) -> str | None:
    """The new text, or None for 'delete the file'. Raises ValueError when the
    existing text cannot be parsed."""
    rows = parse_rows(existing) if existing else []
    if remove_name is not None:
        rows = remove_row(rows, remove_name)
    if add is not None:
        replaced = [add if row.name == add.name else row for row in rows]
        rows = replaced if any(row.name == add.name for row in rows) else [*rows, add]
    return render_rows(rows) if rows else None


def update_file(path: Path, *, add: Row | None = None, remove_name: str | None = None) -> str:
    """Add or remove one row in *path*, atomically, mode 0600.

    Returns a one-line outcome. A file that cannot be parsed is left alone and
    said so; one that ends with no rows is deleted. A symlink is never
    followed: the temporary file is renamed over the name, not written through.
    """
    entry = operator_for(path)
    dir_fd: int | None = None
    if remove_name is not None and add is None and not path.parent.exists():
        return f"{path} was already gone"
    if entry is not None:
        try:
            dir_fd = open_operator_dir(path.parent, entry.pw_name)
        except OperatorDirError as exc:
            return f"left {path}: {exc}"
        if dir_fd is None:
            dir_fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        dir_fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    name = path.name
    try:
        existing: str | None = None
        try:
            st = os.stat(name, dir_fd=dir_fd, follow_symlinks=False)
        except FileNotFoundError:
            st = None
        if st is not None and stat.S_ISREG(st.st_mode):
            handle = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=dir_fd)
            with os.fdopen(handle, "r") as reader:
                existing = reader.read()
        try:
            text = _merged(existing, add, remove_name)
        except ValueError as exc:
            return f"left {path} as it is: it is not a services file hammunition can read ({exc})"
        if text is None:
            if st is not None:
                os.unlink(name, dir_fd=dir_fd)
                return f"removed {path}: no services left in it"
            return f"{path} was already gone"
        tmp = f".{name}.{os.getpid()}.tmp"
        handle = os.open(
            tmp,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
            0o600,
            dir_fd=dir_fd,
        )
        try:
            os.write(handle, text.encode())
            os.fchmod(handle, 0o600)
            if entry is not None:
                os.fchown(handle, entry.pw_uid, entry.pw_gid)
            os.fsync(handle)
        except BaseException:
            os.close(handle)
            with contextlib.suppress(OSError):
                os.unlink(tmp, dir_fd=dir_fd)
            raise
        os.close(handle)
        os.rename(tmp, name, src_dir_fd=dir_fd, dst_dir_fd=dir_fd)
        verb = "removed a row from" if add is None else "wrote a row to"
        return f"{verb} {path} (mode 0600)"
    finally:
        os.close(dir_fd)
