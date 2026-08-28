# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""Identify the machine we are about to modify.

`/etc/os-release` and nothing else (DESIGN.md §8). No heuristics, no probing
for the presence of `apt`, no reading `/etc/debian_version` when the ID is
missing. A system that does not say what it is gets a hard error, because the
alternative is guessing wrong about a machine we are then going to install
packages onto.

Two facts are kept apart on purpose, and callers use different ones:

``Target``
    What the machine reports. This is what manifest selectors resolve against
    (:meth:`hammunition.manifest.schema.PackageManifest.resolve`), and it is
    recorded verbatim in the transaction log so a later reader can tell what a
    run was actually looking at.

``Target.is_debian_family``
    Whether we are willing to *install* here. Inspecting the catalog is safe
    anywhere — ``hammunition list`` on a Fedora laptop is a reasonable thing to
    do — so the refusal lives at the install path rather than at detection.

The parser is deliberately shared with ``scripts/capability_matrix.py``. That
script's ``--check`` mode compares a container's real ``/etc/os-release``
against what ``containers/targets.yaml`` declares; if it read the file with its
own copy of this logic, it would be verifying a parser the engine does not use.
"""

from __future__ import annotations

import platform
from dataclasses import dataclass
from pathlib import Path

__all__ = [
    "DEBIAN_FAMILY",
    "OS_RELEASE_PATHS",
    "DetectionError",
    "Target",
    "parse_os_release",
    "read_os_release",
]


class DetectionError(Exception):
    """The system could not be identified, or identified itself as unsupported."""


# systemd's documented search order: /etc wins, /usr/lib is the vendor default.
OS_RELEASE_PATHS: tuple[Path, ...] = (
    Path("/etc/os-release"),
    Path("/usr/lib/os-release"),
)

# IDs we know are Debian-family without consulting ID_LIKE. Raspberry Pi OS
# reports `raspbian` on the 32-bit image and `debian` on the 64-bit one, so both
# spellings are here; `linuxmint` chains through `ubuntu` rather than `debian`,
# which is why membership is not a single-hop ID_LIKE check.
DEBIAN_FAMILY: frozenset[str] = frozenset(
    {"debian", "ubuntu", "kali", "parrot", "raspbian", "linuxmint", "lmde", "devuan", "pop"}
)


def parse_os_release(text: str) -> dict[str, str]:
    """Parse os-release syntax into a plain mapping.

    Values may be quoted with either quote character and may contain ``=``;
    ``PRETTY_NAME="Debian GNU/Linux 13 (trixie)"`` is the common case. Blank
    lines and comments are skipped. Unparseable lines are skipped rather than
    fatal: this file is written by the distribution, and refusing to identify a
    machine because of one malformed line would be a worse failure than
    ignoring it. A *missing ID* is fatal, and that is checked by the caller.
    """
    fields: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        fields[key.strip()] = value
    return fields


def read_os_release(paths: tuple[Path, ...] = OS_RELEASE_PATHS) -> dict[str, str]:
    """Read the first os-release file that exists, in systemd's search order."""
    for path in paths:
        if path.exists():
            return parse_os_release(path.read_text(encoding="utf-8"))
    searched = ", ".join(str(p) for p in paths)
    raise DetectionError(
        f"no os-release file found (looked in {searched}). Hammunition identifies "
        f"a system only from what it declares about itself and will not guess."
    )


@dataclass(frozen=True)
class Target:
    """What this machine reports about itself, plus its architecture."""

    distro: str
    """os-release ``ID``. Lowercased by the standard; used as-is in selectors."""

    version: str
    """``VERSION_ID`` where present, else ``VERSION_CODENAME``, else empty.

    Empty is a legitimate value: Debian testing and sid ship no ``VERSION_ID``
    at all. A manifest selector that names no ``distro_version`` still matches,
    which is the right outcome — most do not need one.
    """

    arch: str
    """``platform.machine()``. Matches the schema's ``Arch`` values on our targets."""

    id_like: tuple[str, ...] = ()
    pretty_name: str | None = None

    @classmethod
    def from_fields(cls, fields: dict[str, str], *, machine: str) -> Target:
        distro = fields.get("ID", "").strip()
        if not distro:
            raise DetectionError(
                "os-release declares no ID field, so this system does not say what "
                "it is. Hammunition will not infer it from the presence of apt or "
                "from /etc/debian_version (DESIGN.md §8)."
            )
        return cls(
            distro=distro,
            version=fields.get("VERSION_ID", fields.get("VERSION_CODENAME", "")).strip(),
            arch=machine,
            id_like=tuple(fields.get("ID_LIKE", "").split()),
            pretty_name=fields.get("PRETTY_NAME") or None,
        )

    @classmethod
    def detect(cls, paths: tuple[Path, ...] = OS_RELEASE_PATHS) -> Target:
        """Identify the running system."""
        return cls.from_fields(read_os_release(paths), machine=platform.machine())

    @property
    def is_debian_family(self) -> bool:
        """Whether apt-based installation is meaningful here.

        ``ID_LIKE`` is consulted transitively through the known family, so Linux
        Mint (``ID_LIKE=ubuntu``) resolves even though it never names Debian.
        """
        if self.distro in DEBIAN_FAMILY:
            return True
        return any(like in DEBIAN_FAMILY for like in self.id_like)

    def describe(self) -> str:
        """One line for the operator. Says what was read, not what was assumed."""
        name = self.pretty_name or f"{self.distro} {self.version}".strip()
        version = self.version or "no VERSION_ID"
        return f"{name} (ID={self.distro}, version={version}, arch={self.arch})"

    def to_log_entry(self) -> dict[str, str | list[str]]:
        """Transaction-log shape. Records what was read, verbatim."""
        return {
            "distro": self.distro,
            "distro_version": self.version,
            "arch": self.arch,
            "id_like": list(self.id_like),
            "pretty_name": self.pretty_name or "",
        }
