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
import fcntl
import json
import os
import pwd
import re
from collections.abc import Iterator, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from hammunition.paths import state_dir

__all__ = ["KEEP_TRANSACTIONS", "ROTATE_BYTES", "TransactionLog", "log_path"]

#: ``transactions.jsonl`` is rotated at the start of a transaction once it is
#: larger than this (D-077). Constants, not station config: a retention policy
#: is not a value only the operator can supply (D-035).
ROTATE_BYTES = 1024 * 1024
#: A rotation leaves this many of the newest transactions in the live file.
KEEP_TRANSACTIONS = 20

_ARCHIVE = re.compile(r"^transactions-(\d{6})-(\d{8}T\d{6}Z)\.jsonl$")

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

    The owner-aware resolution itself lives in :mod:`hammunition.paths`, shared
    with the artifact cache, which faces the identical sudo problem.
    """
    return state_dir(owner) / "transactions.jsonl"


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
        with self._locked(exclusive=entry["event"] == "transaction_begin"):
            if entry["event"] == "transaction_begin":
                # Best effort: a full disk or a stale file must not stop the
                # transaction from recording that it began.
                with contextlib.suppress(OSError):
                    self._rotate_locked()
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(line + "\n")
                handle.flush()
                os.fsync(handle.fileno())
        self._give_to_owner()

    # -- rotation (D-077) ----------------------------------------------------
    #
    # Every reader walks the whole log through :meth:`read`, so rotation moves
    # the *oldest whole transactions* into ``transactions-<UTC>.jsonl`` beside
    # it and :meth:`read` yields the archives in name order and then the live
    # file: the same events in the same order, which is every property the
    # replay in state/uninstall.py needs. Nothing is ever deleted -- what
    # ``uninstall`` attributes is history -- and the archives are small (a
    # month of a station's use was ~2,800 events). A rotation intent file
    # makes a kill between the two renames harmless: see :meth:`_pending`.

    @property
    def _lock_path(self) -> Path:
        return self.path.with_name(self.path.name + ".lock")

    @property
    def _intent_path(self) -> Path:
        return self.path.with_name(self.path.name + ".rotating")

    @contextlib.contextmanager
    def _locked(self, *, exclusive: bool, create: bool = True) -> Iterator[None]:
        """Appends share, a rotation excludes: a line cannot be written to the
        file a rotation is about to replace. Best-effort when the lock file
        cannot be opened -- the log must not fail a run over its own lock.

        A reader passes ``create=False``: reading must not make a file, so a
        read-only command writes nothing and, under sudo, root never leaves a
        root-owned lock in an operator's state directory."""
        flags = os.O_CLOEXEC | (os.O_RDWR | os.O_CREAT if create else os.O_RDONLY)
        try:
            fd = os.open(self._lock_path, flags, 0o600)
        except OSError:
            if not create:
                yield
                return
            try:
                fd = os.open(self._lock_path, os.O_RDONLY | os.O_CLOEXEC)
            except OSError:
                yield
                return
        try:
            fcntl.flock(fd, fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH)
            yield
        finally:
            os.close(fd)

    def archives(self) -> list[Path]:
        """The rotated archives, oldest first."""
        try:
            found = [p for p in self.path.parent.iterdir() if self._is_archive(p)]
        except OSError:
            return []
        return sorted(found)

    def _is_archive(self, path: Path) -> bool:
        return bool(_ARCHIVE.match(path.name)) and path.parent == self.path.parent

    def rotate(self, *, threshold: int | None = None, keep: int | None = None) -> Path | None:
        """Archive the oldest closed transactions when the live file is larger
        than *threshold*, keeping the newest *keep*. Returns the archive made,
        or None when nothing needed doing."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._locked(exclusive=True):
            return self._rotate_locked(threshold=threshold, keep=keep)

    def _rotate_locked(
        self, *, threshold: int | None = None, keep: int | None = None
    ) -> Path | None:
        threshold = ROTATE_BYTES if threshold is None else threshold
        keep = KEEP_TRANSACTIONS if keep is None else keep
        self._finish_interrupted()
        try:
            if self.path.stat().st_size <= threshold:
                return None
            data = self.path.read_bytes()
        except OSError:
            return None
        lines = data.splitlines(keepends=True)
        begins = [
            i
            for i, line in enumerate(lines)
            if b'"transaction_begin"' in line and self._is_begin(line)
        ]
        if len(begins) <= keep:
            return None
        cut = begins[-keep] if keep > 0 else len(lines)
        head, tail = lines[:cut], lines[cut:]
        # Ordered by a sequence number, not the clock: on a machine whose clock
        # is wrong until a GPS or NTP fix (D-058) a stepped clock would put a
        # newer archive's events before an older one's.
        last = max(
            (int(m.group(1)) for a in self.archives() if (m := _ARCHIVE.match(a.name))), default=0
        )
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        archive = self.path.with_name(f"transactions-{last + 1:06d}-{stamp}.jsonl")
        self._write_atomic(
            self._intent_path, json.dumps({"archive": archive.name, "lines": len(head)}).encode()
        )
        self._write_atomic(archive, b"".join(head))
        self._write_atomic(self.path, b"".join(tail))
        with contextlib.suppress(OSError):
            self._intent_path.unlink()
        self._give_to_owner(extra=[archive, self._lock_path])
        return archive

    @staticmethod
    def _is_begin(line: bytes) -> bool:
        try:
            parsed = json.loads(line)
        except ValueError:
            return False
        return isinstance(parsed, dict) and parsed.get("event") == "transaction_begin"

    def _write_atomic(self, target: Path, payload: bytes) -> None:
        tmp = target.with_name(target.name + ".tmp")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_CLOEXEC, 0o600)
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
        except BaseException:
            with contextlib.suppress(OSError):
                tmp.unlink()
            raise
        os.replace(tmp, target)

    def _pending(self) -> tuple[Path, int] | None:
        """The archive, and how many lines of the live file it duplicates, after
        a rotation killed between writing the archive and shrinking the file --
        or after shrinking it and before deleting the intent, which is why the
        claim is checked against the file rather than trusted. Readers skip
        those lines; the next rotation finishes the job."""
        try:
            intent = json.loads(self._intent_path.read_text(encoding="utf-8"))
            archive = self.path.with_name(str(intent["archive"]))
            count = int(intent["lines"])
            if not self._is_archive(archive):
                return None
            head = archive.read_text(encoding="utf-8").splitlines()
            live = self.path.read_text(encoding="utf-8").splitlines()
        except (OSError, ValueError, KeyError, TypeError):
            return None  # no intent, or the archive never landed: the file is whole
        if count == 0 or len(head) != count or live[:count] != head:
            return None
        return archive, count

    def _finish_interrupted(self) -> None:
        pending = self._pending()
        if pending is not None:
            lines = self.path.read_bytes().splitlines(keepends=True)
            self._write_atomic(self.path, b"".join(lines[pending[1] :]))
        with contextlib.suppress(OSError):
            self._intent_path.unlink()

    def _give_to_owner(self, extra: list[Path] | None = None) -> None:
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
        targets: list[Path] = [self.path, *(extra or [])]
        # Every directory we may have created on the way down, not just the
        # last one: `.local` and `.local/state` are as likely to be new as
        # `hammunition/` is, and a root-owned `.local` breaks far more than
        # this log.
        parent = self.path.parent
        while parent != home and home in parent.parents:
            targets.append(parent)
            parent = parent.parent
        targets.extend(p for p in (self._lock_path,) if p.exists() and p not in targets)
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
        """Yield entries, oldest first: every archive in name order, then the
        live file. Skips any line that is not valid JSON.

        A truncated final line is the expected result of a kill during a write;
        refusing to read the whole log because of it would be the wrong trade.
        An archive that exists and cannot be read is a different matter and
        raises: skipping it would report units as not installed (D-077).
        """
        with self._locked(exclusive=False, create=False):
            pending = self._pending()
            skip = pending[1] if pending is not None else 0
            chunks = [a.read_text(encoding="utf-8").splitlines() for a in self.archives()]
            live = self.path.read_text(encoding="utf-8").splitlines() if self.path.exists() else []
        for chunk in chunks:
            yield from self._parse(chunk)
        yield from self._parse(live[skip:])

    @staticmethod
    def _parse(lines: list[str]) -> Iterator[dict[str, Any]]:
        for line in lines:
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
