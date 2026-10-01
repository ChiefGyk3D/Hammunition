# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""GeoClue fed by the GPS tether, so CoMaps can show "you are here".  D-069.

CoMaps on Linux reads its position from GeoClue2 only, through Qt's
``geoclue2`` plugin, by name. GeoClue 2.7 has a network-NMEA source that reads
a unix stream socket named in ``[network-nmea] nmea-socket=``. The spike of
2026-10-01 ran Debian's own GeoClue 2.7.2, its demo agent and Qt 6.8.2's plugin
asking as ``app.comaps.comaps`` in a private namespace, and a fake NMEA feed on
that socket reached the client. A natively installed CoMaps is a *system app*
to GeoClue (only a Flatpak has an app id), so no ``[app.comaps.comaps]`` entry
is needed.

Two root files, both written by ``hardware apply`` and never by the helper,
both disclosed, both removed by ``hardware unapply`` by content:

- ``/etc/geoclue/conf.d/90-hammunition-gps.conf``: the socket, over Debian's
  untouched ``geoclue.conf`` (a drop-in, never an edit to the conffile);
- ``/etc/tmpfiles.d/hammunition-gps.conf``: ``/run/hammunition-gps``, mode
  2750, the operator's and GeoClue's group, made now by ``systemd-tmpfiles
  --create`` and at every boot by systemd. The setgid bit gives the tether's
  0660 socket GeoClue's group, so GeoClue can read it and nobody else can.

The ruling on where these belong: they serve the receiver's position to every
GeoClue client, not to CoMaps alone, so they are a class-level set installed
by ``hardware apply`` beside GPS time (D-058), gated on GeoClue being
installed; ``comaps`` carries only the apt dependencies.

Every path is read as ``geoclue.NAME`` at call time, so one test fixture can
point all of them at a temporary tree.
"""

from __future__ import annotations

import grp
import os
import pwd
import re
import stat
import textwrap
from dataclasses import dataclass
from pathlib import Path

from hammunition.backends.base import BackendError, Command, CommandRunner, SubprocessRunner

__all__ = [
    "DAEMON",
    "DEMO_AGENT",
    "DISCLOSURES",
    "DROPIN",
    "GROUP",
    "HEADER",
    "PATHS",
    "SOCKET",
    "SOCKET_DIR",
    "TMPFILES",
    "GeoClueError",
    "GeoClueGrants",
    "GeoClueRemoval",
    "GeoClueState",
    "agent_running",
    "configured",
    "disclose",
    "dropin_content",
    "grant_commands",
    "plan_geoclue",
    "plan_geoclue_removal",
    "read_state",
    "removal_commands",
    "stage_grants",
    "tmpfiles_content",
    "verify_grants",
    "verify_removal",
]

DAEMON = "/usr/libexec/geoclue"
"""GeoClue's daemon, from Debian's ``geoclue-2.0``. Its absence means GeoClue is
not installed, and nothing here is planned."""

DROPIN = "/etc/geoclue/conf.d/90-hammunition-gps.conf"
"""Read after ``/etc/geoclue/geoclue.conf``, every ``*.conf`` here in order,
the later winning (``gclue-config.c`` at 2.7.2)."""

TMPFILES = "/etc/tmpfiles.d/hammunition-gps.conf"
"""Makes SOCKET_DIR at every boot: /run is a tmpfs."""

SOCKET_DIR = "/run/hammunition-gps"
"""Not under /home, /tmp or /run/user: GeoClue's unit runs as user ``geoclue``
with ProtectSystem=strict, ProtectHome=true and PrivateTmp=true."""

SOCKET = "/run/hammunition-gps/nmea.sock"
"""Where the tether listens when the drop-in is in place."""

PATHS: dict[str, str] = {
    "DAEMON": DAEMON,
    "DROPIN": DROPIN,
    "TMPFILES": TMPFILES,
    "SOCKET_DIR": SOCKET_DIR,
    "SOCKET": SOCKET,
}
"""Each attribute and its real default, for the fixtures that repoint them."""

GROUP = "geoclue"
"""The group GeoClue's daemon runs as (Debian's ``geoclue-2.0`` creates it)."""

DIR_MODE = 0o2750
"""setgid, so the socket made inside takes GeoClue's group; the operator writes,
GeoClue's group reads and traverses, nobody else gets in."""

UNIT = "geoclue"
DEMO_AGENT = "org.freedesktop.GeoClue2.DemoAgent"
"""The bus name Debian's demo agent takes on the session bus (measured on Plasma,
2026-10-01). ``geoclue-2.0`` autostarts it on every desktop but GNOME from
``/etc/xdg/autostart/geoclue-demo-agent.desktop``; GNOME Shell is its own agent."""

HEADER = "# Written by `hammunition hardware apply` (D-069)."

DISCLOSURES: tuple[str, ...] = (
    "GeoClue reads its configuration only when it starts; it exits after 60 s with "
    "no client, and `systemctl try-restart geoclue` applies a change at once.",
    "While the tether runs, GeoClue hands the GPS fix to any native (non-Flatpak) app "
    "of a user with a GeoClue agent, and Debian's demo agent does not prompt.",
    "Stock GeoClue also asks beacondb (nearby Wi-Fi networks, or GeoIP when Wi-Fi is "
    "off) whenever CoMaps asks for a position, so with the tether stopped the map shows "
    "that coarse network location; only GeoClue's `[static-source]` would stop the "
    "GeoIP lookups, and Hammunition does not change it.",
    "Qt caches the last fix under `~/.local/share/qtposition-geoclue2`.",
)
"""What the plan and the guide both say, word for word (a test holds the guide to it)."""

_STAGED_DROPIN = "geoclue-90-hammunition-gps.conf"
_STAGED_TMPFILES = "tmpfiles-hammunition-gps.conf"
_RESTART = ("systemctl", "try-restart", UNIT)
_OPERATOR = re.compile(r"[A-Za-z_][A-Za-z0-9_.-]{0,31}\$?")


class GeoClueError(ValueError):
    """Refused before anything runs: a file we did not write, a name that is not one."""


def dropin_content(socket_path: str | None = None) -> str:
    return (
        f"{HEADER} GeoClue reads the GPS tether's\n"
        "# NMEA from this socket while `hammunition maps gps-tether` runs.\n"
        "# `hammunition hardware unapply` removes this file.\n"
        "[network-nmea]\n"
        "enable=true\n"
        f"nmea-socket={SOCKET if socket_path is None else socket_path}\n"
    )


def tmpfiles_content(
    operator: str, *, directory: str | None = None, group: str | None = None
) -> str:
    """The one ``d`` line, under our header. The operator's name is written into a
    root file, so anything but an account name is refused."""
    if not _OPERATOR.fullmatch(operator):
        raise GeoClueError(
            f"{operator!r} is not an operator account name; nothing is written for GeoClue"
        )
    where = SOCKET_DIR if directory is None else directory
    owner_group = GROUP if group is None else group
    return (
        f"{HEADER} The GPS tether's socket\n"
        "# lives here, readable by GeoClue's group only. `hardware unapply` removes it.\n"
        f"d {where} {DIR_MODE:o} {operator} {owner_group} -\n"
    )


def _read(path: str) -> str | None:
    try:
        return Path(path).read_text(encoding="utf-8")
    except (FileNotFoundError, NotADirectoryError):
        return None


def _ours(path: str) -> bool:
    text = _read(path)
    return text is not None and text.startswith(HEADER)


def configured() -> bool:
    """Whether GeoClue has been told to read the tether's socket: our drop-in is
    there. The tether reads this to serve the socket by default."""
    return _ours(DROPIN)


def _gid(name: str) -> int | None:
    try:
        return grp.getgrnam(name).gr_gid
    except KeyError:
        return None


def _uid(name: str) -> int | None:
    try:
        return pwd.getpwnam(name).pw_uid
    except KeyError:
        return None


NOT_A_DIRECTORY = "not a directory"


def _directory_state(uid: int | None, gid: int | None) -> str:
    """``absent``, ``current``, or what is wrong with SOCKET_DIR, never following
    a symlink."""
    try:
        st = os.lstat(SOCKET_DIR)
    except FileNotFoundError:
        return "absent"
    if not stat.S_ISDIR(st.st_mode):
        return NOT_A_DIRECTORY
    wrong: list[str] = []
    mode = stat.S_IMODE(st.st_mode)
    if mode != DIR_MODE:
        wrong.append(f"mode {mode:04o}, not {DIR_MODE:o}")
    if uid is not None and st.st_uid != uid:
        wrong.append(f"owner uid {st.st_uid}, not {uid}")
    if gid is not None and st.st_gid != gid:
        wrong.append(f"group gid {st.st_gid}, not {GROUP}'s {gid}")
    return "current" if not wrong else "; ".join(wrong)


@dataclass(frozen=True)
class GeoClueGrants:
    installed: bool
    """GeoClue's daemon and its group are both here; without them nothing is planned."""
    operator: str
    reason: str = ""
    """Why nothing is planned, when ``installed`` is False."""
    dropin_current: bool = False
    tmpfiles_current: bool = False
    directory_current: bool = False

    @property
    def is_noop(self) -> bool:
        return not self.installed or (
            self.dropin_current and self.tmpfiles_current and self.directory_current
        )


def plan_geoclue(operator: str) -> GeoClueGrants:
    """What ``hardware apply`` will write for GeoClue. Reads, never writes; raises
    :class:`GeoClueError` before anything runs on a file we did not write."""
    if not Path(DAEMON).is_file():
        return GeoClueGrants(
            installed=False,
            operator=operator,
            reason=f"GeoClue is not installed ({DAEMON} is missing)",
        )
    gid = _gid(GROUP)
    if gid is None:
        return GeoClueGrants(
            installed=False,
            operator=operator,
            reason=f"GeoClue's `{GROUP}` group does not exist",
        )
    wanted_tmpfiles = tmpfiles_content(operator)
    uid = _uid(operator)
    if uid is None:
        raise GeoClueError(f"there is no account named {operator!r} to own {SOCKET_DIR}")
    for path in (DROPIN, TMPFILES):
        text = _read(path)
        if text is not None and not text.startswith(HEADER):
            raise GeoClueError(
                f"{path} exists and holds text Hammunition did not write; it is never "
                f"overwritten. Move it aside and re-run, or use `--no-geoclue`. Nothing "
                f"was changed."
            )
    directory = _directory_state(uid, gid)
    if directory == NOT_A_DIRECTORY:
        raise GeoClueError(
            f"{SOCKET_DIR} exists and is {NOT_A_DIRECTORY} (a symlink or a file); it is "
            f"never replaced. Remove it and re-run, or use `--no-geoclue`. Nothing was changed."
        )
    return GeoClueGrants(
        installed=True,
        operator=operator,
        dropin_current=_read(DROPIN) == dropin_content(),
        tmpfiles_current=_read(TMPFILES) == wanted_tmpfiles,
        directory_current=directory == "current",
    )


def _wrap(text: str, indent: str = "  ") -> list[str]:
    """Wrapped at spaces only: a path or a command is never split."""
    return textwrap.wrap(
        text,
        width=88,
        initial_indent=indent,
        subsequent_indent=indent,
        break_long_words=False,
        break_on_hyphens=False,
    )


def disclose(g: GeoClueGrants) -> list[str]:
    if not g.installed:
        return [
            f"GeoClue (D-069): {g.reason}, so nothing is written for it. `comaps` depends",
            "  on geoclue-2.0; once it is installed, re-run `hammunition hardware apply`.",
        ]
    if g.is_noop:
        return ["GeoClue (D-069): already reads the GPS tether's socket; nothing to change."]
    lines = [
        "Will let GeoClue read the GPS tether's NMEA from a socket (D-069), so CoMaps can",
        '  show "you are here" (no CoMaps patch, no app entry: a native CoMaps is a system app):',
    ]
    if not g.dropin_current:
        lines.append(f"  {DROPIN}:")
        lines += [f"    {line}" for line in dropin_content().splitlines()]
    if not g.tmpfiles_current:
        lines.append(f"  {TMPFILES}:")
        lines += [f"    {line}" for line in tmpfiles_content(g.operator).splitlines()]
    lines += _wrap(
        f"`systemd-tmpfiles --create {TMPFILES}` makes {SOCKET_DIR} now ({DIR_MODE:o}, "
        f"{g.operator}:{GROUP}), and systemd makes it at every boot. The tether "
        f"(`hammunition maps gps-tether`) serves {SOCKET} there, mode 0660, so GeoClue can "
        f"read it and no other account can."
    )
    if not g.dropin_current:
        lines += _wrap("`systemctl try-restart geoclue` makes a running GeoClue read the drop-in.")
    for sentence in DISCLOSURES:
        lines += _wrap(sentence)
    lines += _wrap(
        f"Inspect: `cat {DROPIN} {TMPFILES}`, `ls -ld {SOCKET_DIR}`, "
        f'`journalctl -u geoclue | grep -i nmea` ("NMEA service connected." once the '
        f"tether runs)."
    )
    lines += _wrap(
        f"Reverse: `hammunition hardware unapply` deletes both files and the socket, runs "
        f"`rmdir {SOCKET_DIR}` and `systemctl try-restart geoclue`. "
        f"`hardware apply --no-geoclue` leaves GeoClue alone."
    )
    return lines


def grant_commands(g: GeoClueGrants, staging_root: str) -> list[Command]:
    if g.is_noop:
        return []
    out: list[Command] = []
    if not g.dropin_current:
        out.append(
            Command(
                argv=("install", "-D", "-m", "0644", f"{staging_root}/{_STAGED_DROPIN}", DROPIN),
                description="Tell GeoClue to read the GPS tether's NMEA socket",
                requires_root=True,
            )
        )
    if not g.tmpfiles_current:
        out.append(
            Command(
                argv=(
                    "install",
                    "-D",
                    "-m",
                    "0644",
                    f"{staging_root}/{_STAGED_TMPFILES}",
                    TMPFILES,
                ),
                description=f"Have systemd make {SOCKET_DIR} at every boot",
                requires_root=True,
            )
        )
    if not (g.tmpfiles_current and g.directory_current):
        out.append(
            Command(
                argv=("systemd-tmpfiles", "--create", TMPFILES),
                description=f"Make {SOCKET_DIR} now ({DIR_MODE:o}, {g.operator}:{GROUP})",
                requires_root=True,
            )
        )
    if not g.dropin_current:
        out.append(
            Command(
                argv=_RESTART,
                description="Restart GeoClue if it is running, so it reads the drop-in",
                requires_root=True,
            )
        )
    return out


def stage_grants(g: GeoClueGrants, staging_dir: Path) -> None:
    if g.is_noop:
        return
    for name, current, text in (
        (_STAGED_DROPIN, g.dropin_current, dropin_content()),
        (_STAGED_TMPFILES, g.tmpfiles_current, tmpfiles_content(g.operator)),
    ):
        if not current:
            (staging_dir / name).write_text(text, encoding="utf-8")
            os.chmod(staging_dir / name, 0o644)


def verify_grants(g: GeoClueGrants) -> list[str]:
    """D-031: what landed, read back."""
    if not g.installed:
        return []
    problems: list[str] = []
    if _read(DROPIN) != dropin_content():
        problems.append(f"{DROPIN} on disk does not match what we wrote")
    if _read(TMPFILES) != tmpfiles_content(g.operator):
        problems.append(f"{TMPFILES} on disk does not match what we wrote")
    directory = _directory_state(_uid(g.operator), _gid(GROUP))
    if directory != "current":
        problems.append(f"{SOCKET_DIR}: {directory}")
    return problems


@dataclass(frozen=True)
class GeoClueRemoval:
    dropin_ours: bool = False
    tmpfiles_ours: bool = False
    socket_present: bool = False
    """SOCKET is a socket (a stale one, or a running tether's). Anything else at
    that path is not removed, and ``rmdir`` then fails loudly."""
    directory_present: bool = False
    """SOCKET_DIR is a real directory, not a symlink."""

    @property
    def is_empty(self) -> bool:
        return not (
            self.dropin_ours or self.tmpfiles_ours or self.socket_present or self.directory_present
        )


def _is(path: str, kind: int) -> bool:
    try:
        return stat.S_IFMT(os.lstat(path).st_mode) == kind
    except (FileNotFoundError, NotADirectoryError):
        return False


def plan_geoclue_removal() -> GeoClueRemoval:
    """What unapply takes back, by content: a file only when it carries our header."""
    return GeoClueRemoval(
        dropin_ours=_ours(DROPIN),
        tmpfiles_ours=_ours(TMPFILES),
        socket_present=_is(SOCKET, stat.S_IFSOCK),
        directory_present=_is(SOCKET_DIR, stat.S_IFDIR),
    )


def removal_commands(r: GeoClueRemoval) -> list[Command]:
    out: list[Command] = []
    for path, ours in ((DROPIN, r.dropin_ours), (TMPFILES, r.tmpfiles_ours)):
        if ours:
            out.append(
                Command(
                    argv=("rm", "-f", path),
                    description=f"Remove {path}, written by Hammunition for GeoClue",
                    requires_root=True,
                )
            )
    if r.socket_present:
        out.append(
            Command(
                argv=("rm", "-f", SOCKET),
                description="Remove the tether's socket (a running tether keeps serving TCP)",
                requires_root=True,
            )
        )
    if r.directory_present:
        out.append(
            Command(
                argv=("rmdir", SOCKET_DIR),
                description=f"Remove {SOCKET_DIR}",
                requires_root=True,
            )
        )
    if r.dropin_ours:
        out.append(
            Command(
                argv=_RESTART,
                description="Restart GeoClue if it is running, so it forgets the socket",
                requires_root=True,
            )
        )
    return out


def verify_removal(r: GeoClueRemoval) -> list[str]:
    problems: list[str] = []
    for path, removed in (
        (DROPIN, r.dropin_ours),
        (TMPFILES, r.tmpfiles_ours),
        (SOCKET_DIR, r.directory_present),
    ):
        if removed and os.path.lexists(path):
            problems.append(f"{path} is still present")
    return problems


@dataclass(frozen=True)
class GeoClueState:
    """What ``doctor`` reports, read without privilege."""

    dropin_ours: bool
    tmpfiles_ours: bool
    directory: str
    """``absent``, ``current``, ``not a directory``, or what is wrong with it."""
    agent: bool | None
    """Debian's demo agent is on this session's bus; None when it was not asked."""


def agent_running(runner: CommandRunner | None = None) -> bool | None:
    """Whether the demo agent holds its name on the session bus, from ``busctl
    --user list``: read-only, nothing is started. None when busctl did not answer."""
    command = Command(
        argv=("busctl", "--user", "list", "--no-pager"),
        description="List the names on this session's bus (read-only)",
    )
    try:
        result = (runner or SubprocessRunner()).run(command)
    except BackendError:
        return None
    if not result.ok:
        return None
    return any(line.split()[:1] == [DEMO_AGENT] for line in result.stdout.splitlines())


def read_state(
    operator: str, *, runner: CommandRunner | None = None, ask_agent: bool = True
) -> GeoClueState | None:
    """None when GeoClue is not installed: there is nothing to report."""
    if not Path(DAEMON).is_file():
        return None
    return GeoClueState(
        dropin_ours=_ours(DROPIN),
        tmpfiles_ours=_ours(TMPFILES),
        directory=_directory_state(_uid(operator), _gid(GROUP)),
        agent=agent_running(runner) if ask_agent else None,
    )
