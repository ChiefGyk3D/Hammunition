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

import contextlib
import json
import os
import pwd
from collections.abc import Iterator, Mapping
from pathlib import Path
from typing import Any

__all__ = ["TransactionLog", "log_path"]

_SECRET_HINTS = ("password", "passwd", "secret", "token", "api_key", "apikey", "private_key")


def log_path(owner: str | None = None) -> Path:
    """``$XDG_STATE_HOME/hammunition/transactions.jsonl``, XDG default applied.

    ``owner`` is the operator the run is *on behalf of*, and it changes the
    answer only when the engine is running as root and that operator is
    somebody else — the ``sudo hammunition install ...`` case.

    Without it the log follows ``$HOME``, which sudo resets to ``/root``. The
    engine already works out who the operator is, because ``gpasswd`` needs a
    name; writing that operator's transaction history somewhere they cannot see
    it, while `hammunition status` run as themselves reports "no transactions
    recorded", is the log being wrong about the one thing it exists to record.

    ``$XDG_STATE_HOME`` is deliberately not consulted in that case: under sudo
    it either does not survive ``env_reset`` or belongs to root, and neither is
    the operator's.
    """
    if owner and os.geteuid() == 0:
        entry = None
        with contextlib.suppress(KeyError):
            entry = pwd.getpwnam(owner)
        if entry is not None and entry.pw_uid != 0:
            return Path(entry.pw_dir) / ".local" / "state" / "hammunition" / "transactions.jsonl"
    base = os.environ.get("XDG_STATE_HOME") or str(Path.home() / ".local" / "state")
    return Path(base) / "hammunition" / "transactions.jsonl"


class TransactionLog:
    """Append-only JSONL writer.

    Not a general logger: this records what was done to the machine, so it is
    written durably and never rewritten.
    """

    def __init__(self, path: Path | None = None, *, owner: str | None = None) -> None:
        self.owner = owner
        self.path = path or log_path(owner)
        self.ownership_error: str | None = None
        """Set when a root-created log could not be handed to its operator.

        Reported rather than suppressed. A swallowed ``chown`` leaves a log the
        operator cannot append to, and the failure surfaces on their *next*
        run, in the one component that exists to keep a record — D-031's shape
        exactly, inside the module that records what D-031 is about.
        """

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
        self._give_to_owner()

    def _give_to_owner(self) -> None:
        """Hand a root-created log back to the operator it belongs to.

        Writing into somebody's home as root leaves a file they cannot append
        to, so the *next* run — the one they do without sudo — fails on a
        permission error in the one component that must never lose its record.
        Best-effort: a chown that cannot be done is not a reason to fail a run
        whose commands already succeeded.
        """
        if not self.owner or os.geteuid() != 0:
            return
        try:
            entry = pwd.getpwnam(self.owner)
        except KeyError:
            return
        home = Path(entry.pw_dir)
        targets: list[Path] = [self.path]
        # Every directory we may have created on the way down, not just the
        # last one: `.local` and `.local/state` are as likely to be new as
        # `hammunition/` is, and a root-owned `.local` breaks far more than
        # this log.
        parent = self.path.parent
        while parent != home and home in parent.parents:
            targets.append(parent)
            parent = parent.parent
        for target in targets:
            try:
                if target.stat().st_uid == 0:
                    os.chown(target, entry.pw_uid, entry.pw_gid)
            except OSError as exc:
                if self.ownership_error is None:
                    self.ownership_error = (
                        f"{target} could not be given to {self.owner!r} ({exc.strerror}). "
                        f"It stays owned by root, so a later run as {self.owner!r} will "
                        f"not be able to append to it; fix with: "
                        f"chown -R {self.owner}: {self.path.parent}"
                    )

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
