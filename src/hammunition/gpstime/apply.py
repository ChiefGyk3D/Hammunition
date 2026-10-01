# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""The root half of ``time mode``: three files, one restart.  D-058.

Runs inside ``hammunition-devctl`` only. It takes a mode from a fixed enum and
derives every byte it writes from it; each path is admitted by
:func:`guard_time`, an exact match against three constants, and written by
:func:`hammunition.rootfiles.atomic_write` under a lock on
``/etc/hammunition``, so two runs (a tray click and a CLI call) cannot splice.

It never writes the systemd drop-in or the AppArmor rule. Those widen a
daemon's privilege and are installed, disclosed, by ``hardware apply``.

A configuration change needs ``systemctl restart ntpsec`` (SIGHUP does not
reread it). If the restart fails, the previous files are put back and ntpsec
is started on them, so a mode change cannot leave the machine with no time
daemon.
"""

from __future__ import annotations

from pathlib import Path

from hammunition.backends.base import BackendError, Command, CommandRunner, SubprocessRunner
from hammunition.gpstime import files
from hammunition.gpstime.mode import (
    ROUTE,
    Mode,
    Route,
    TimeError,
    as_mode,
    render_mode_file,
    render_ntp_d,
)
from hammunition.gpstime.ntpconf import transform
from hammunition.gpstime.state import ntpsec_installed
from hammunition.rootfiles import atomic_write, dir_lock

__all__ = ["RESTART", "apply_mode", "guard_time"]

RESTART = Command(
    argv=("systemctl", "restart", "ntpsec"),
    description="Restart ntpsec: it rereads its configuration only on a restart",
)


def guard_time(path: str) -> str:
    """The three files ``time mode`` writes, by exact string, and nothing else."""
    allowed = (files.TIME_CONFIG, files.NTP_D_FILE, files.NTP_CONF)
    if path not in allowed:
        raise TimeError(
            f"{path!r} is not one of the three files `time mode` writes ({', '.join(allowed)})"
        )
    return path


def _read(path: str) -> str | None:
    try:
        return Path(path).read_text(encoding="utf-8")
    except FileNotFoundError:
        return None


def _put(path: str, content: str | None) -> None:
    target = Path(guard_time(path))
    if content is None:
        target.unlink(missing_ok=True)
        return
    target.parent.mkdir(mode=0o755, parents=True, exist_ok=True)
    atomic_write(target, content)


def _put_back(before: dict[str, str | None]) -> str:
    failed: list[str] = []
    for path, content in before.items():
        try:
            _put(path, content)
        except OSError as exc:
            failed.append(f"{path} ({exc})")
    if failed:
        return f"putting the previous files back failed for {', '.join(failed)}"
    return "the previous files were put back"


def _restart(runner: CommandRunner) -> str | None:
    try:
        result = runner.run(RESTART)
    except BackendError as exc:
        return str(exc)
    return None if result.ok else (result.stderr.strip() or f"exit {result.returncode}")


def apply_mode(
    mode: Mode, *, route: Route = ROUTE, runner: CommandRunner | None = None
) -> list[str]:
    """Write ``mode``'s three files and restart ntpsec. Returns the problems;
    empty is success. Raises :class:`TimeError` before writing anything when
    ntpsec is absent or ntp.conf lacks an anchor."""
    mode = as_mode(mode)
    run = runner or SubprocessRunner()
    if not ntpsec_installed():
        raise TimeError(
            f"ntpsec is not installed ({files.NTPD} or {files.NTP_CONF} is missing), and "
            f"only ntpsec can take time from a GPS here (D-058). Nothing was changed."
        )
    lock_dir = Path(files.TIME_CONFIG).parent
    lock_dir.mkdir(mode=0o755, parents=True, exist_ok=True)
    with dir_lock(lock_dir):
        order = (files.NTP_D_FILE, files.NTP_CONF, files.TIME_CONFIG)
        before = {path: _read(path) for path in order}
        conf = before[files.NTP_CONF]
        if conf is None:
            raise TimeError(f"{files.NTP_CONF} vanished while it was being read")
        wanted: dict[str, str | None] = {
            files.NTP_D_FILE: render_ntp_d(mode, route),
            files.NTP_CONF: transform(conf, mode, route),
            files.TIME_CONFIG: render_mode_file(mode),
        }
        if wanted == before:
            return []
        try:
            for path in order:
                if wanted[path] != before[path]:
                    _put(path, wanted[path])
        except OSError as exc:
            return [f"could not write the time files ({exc}); {_put_back(before)}"]
        unread = [path for path in order if _read(path) != wanted[path]]
        if unread:
            return [f"{', '.join(unread)} did not read back what was written; {_put_back(before)}"]
        reason = _restart(run)
        if reason is None:
            return []
        note = _put_back(before)
        again = _restart(run)
        tail = "" if again is None else f" ntpsec did not start on them either ({again})."
        return [
            f"ntpsec did not restart ({reason}); {note}.{tail} "
            f"`journalctl -u ntpsec -n 20` shows why."
        ]
