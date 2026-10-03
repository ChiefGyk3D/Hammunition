# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""Read local TCP listeners from the kernel's proc tables."""

from pathlib import Path

LOOPBACK = frozenset(
    {
        "0100007F",
        "00000000000000000000000001000000",
        "0000000000000000FFFF00000100007F",
    }
)


def listening_addresses(
    port: int,
    *,
    tables: tuple[str, ...] = ("/proc/net/tcp", "/proc/net/tcp6"),
) -> set[str] | None:
    """Return uppercase local addresses listening on *port*, or None if unreadable."""
    found: set[str] = set()
    for table in tables:
        try:
            rows = Path(table).read_text().splitlines()[1:]
        except FileNotFoundError:
            continue
        except OSError:
            return None
        for row in rows:
            fields = row.split()
            if len(fields) < 4 or fields[3] != "0A":
                continue
            try:
                address, port_hex = fields[1].rsplit(":", 1)
                matches_port = int(port_hex, 16) == port
            except ValueError:
                continue
            if matches_port:
                found.add(address.upper())
    return found


def bound_to_loopback_only(
    port: int,
    *,
    tables: tuple[str, ...] = ("/proc/net/tcp", "/proc/net/tcp6"),
) -> bool | None:
    """Whether every local listener on *port* is bound to a loopback address."""
    addresses = listening_addresses(port, tables=tables)
    if addresses is None:
        return None
    return addresses <= LOOPBACK
