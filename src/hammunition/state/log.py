# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""Append-only transaction log.

CLAUDE.md puts structured logging in ``~/.local/state/hammunition/`` and D-004
makes the log the basis of ``uninstall``, since true rollback is not achievable
and must not be promised.

JSON Lines, one event per line, append-only. Chosen because a crashed or killed
install leaves every completed event intact and readable, which a single JSON
document does not.

Every entry carries ``event`` and ``version``. Readers must tolerate unknown
event types rather than failing — a newer engine writing a log an older one
reads should degrade to ignoring what it does not understand.
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterator, Mapping
from pathlib import Path
from typing import Any

__all__ = ["TransactionLog", "log_path"]

_SECRET_HINTS = ("password", "passwd", "secret", "token", "api_key", "apikey", "private_key")


def log_path() -> Path:
    """``$XDG_STATE_HOME/hammunition/transactions.jsonl``, XDG default applied."""
    base = os.environ.get("XDG_STATE_HOME") or str(Path.home() / ".local" / "state")
    return Path(base) / "hammunition" / "transactions.jsonl"


class TransactionLog:
    """Append-only JSONL writer.

    Not a general logger: this records what was done to the machine, so it is
    written durably and never rewritten.
    """

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or log_path()

    def append(self, entry: Mapping[str, Any]) -> None:
        if "event" not in entry:
            raise ValueError("transaction log entries must carry an 'event' key")
        self._reject_secrets(entry)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(entry, sort_keys=False, default=str)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")
            handle.flush()
            os.fsync(handle.fileno())

    def read(self) -> Iterator[dict[str, Any]]:
        """Yield entries, skipping any line that is not valid JSON.

        A truncated final line is the expected result of a kill during a write;
        refusing to read the whole log because of it would be the wrong trade.
        """
        if not self.path.exists():
            return
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                parsed = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict):
                yield parsed

    @staticmethod
    def _reject_secrets(entry: Mapping[str, Any]) -> None:
        """CLAUDE.md: no credentials, keys or tokens in generated files.

        The log records what happened to a machine and is a natural place for a
        rendered config to leak into. Refuse loudly rather than write it.
        """

        def walk(node: Any, trail: str) -> None:
            if isinstance(node, Mapping):
                for key, value in node.items():
                    name = str(key).lower()
                    if any(hint in name for hint in _SECRET_HINTS):
                        raise ValueError(
                            f"refusing to write {trail}{key!r} to the transaction log: "
                            f"the field name suggests a credential"
                        )
                    walk(value, f"{trail}{key}.")
            elif isinstance(node, (list, tuple)):
                for item in node:
                    walk(item, trail)

        walk(entry, "")
