# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""``hammunition maps phone``: the phone files in one folder, and the ways across.  D-067.

The laptop builds the team's phone maps (``mapsforge-map``, ``mapsforge-poi``)
and, when ``navigation`` is installed, Garmin maps (``osm-garmin``). This
copies each installed one into ``$XDG_DATA_HOME/hammunition/phone/`` as
``<slug>.<ext>``, with a ``SHA256SUMS`` in ``sha256sum -c`` format beside
them, and says how to carry them to a phone. **Nothing is transferred and
nothing is served by the engine**: every route is a command the operator runs.

Per user and unprivileged, like the menu files (D-050). Each source is hashed
as it is read and each copy after it is written (D-031: the effect, not the
exit status). A copy whose hash already matches is left alone, so a second run
copies nothing. A file of ours -- a ``.map``, ``.poi`` or ``.img`` at the top
of the folder -- whose region is gone is removed; nothing else in the folder is
touched. The folder must be a real directory, never a symbolic link, and the
copies must fit on its file system; each is refused by name before anything
is copied.

The web server line binds the hotspot's address, not every interface: served
on the hotspot link only, never on another network the laptop has joined.
"""

from __future__ import annotations

import contextlib
import hashlib
import os
import shutil
import stat
import tempfile
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from .paths import data_dir

#: (unit, suffix) of every phone file, in the order they are listed.
PHONE_FILES: tuple[tuple[str, str], ...] = (
    ("mapsforge-map", ".map"),
    ("mapsforge-poi", ".poi"),
    ("osm-garmin", ".img"),
)
SUFFIXES = frozenset(suffix for _, suffix in PHONE_FILES)
SUMS = "SHA256SUMS"
#: NetworkManager's shared mode (``nmcli device wifi hotspot``) gives the
#: laptop this address on the hotspot unless it is configured otherwise.
HOTSPOT_ADDRESS = "10.42.0.1"
PORT = 8000
_CHUNK = 1024 * 1024


class PhoneError(Exception):
    """Refused before anything was copied, with the reason."""


def phone_dir() -> Path:
    """``$XDG_DATA_HOME/hammunition/phone``: this operator's folder of phone files."""
    return data_dir() / "phone"


@dataclass(frozen=True)
class Found:
    unit: str
    name: str
    source: Path


@dataclass(frozen=True)
class Staged:
    unit: str
    name: str
    size: int
    sha256: str
    copied: bool


@dataclass(frozen=True)
class Result:
    directory: Path
    files: tuple[Staged, ...]
    removed: tuple[str, ...]


def installed(data: Path) -> list[Found]:
    """Every phone file installed under *data* (the prefix's data root): regular
    files only, never through a symbolic link, in :data:`PHONE_FILES` order."""
    out: list[Found] = []
    for unit, suffix in PHONE_FILES:
        directory = data / unit
        if not directory.is_dir():
            continue
        for path in sorted(directory.glob(f"*{suffix}")):
            if stat.S_ISREG(path.lstat().st_mode):
                out.append(Found(unit, path.name, path))
    return out


def missing_units(data: Path) -> tuple[str, ...]:
    """The phone units with no file installed, for the "install these" line."""
    have = {f.unit for f in installed(data)}
    return tuple(unit for unit, _ in PHONE_FILES if unit not in have)


def _open(path: Path) -> int:
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    if not stat.S_ISREG(os.fstat(fd).st_mode):
        os.close(fd)
        raise PhoneError(f"{path} is not a regular file")
    return fd


def _hash(path: Path) -> str:
    digest = hashlib.sha256()
    with os.fdopen(_open(path), "rb") as handle:
        while chunk := handle.read(_CHUNK):
            digest.update(chunk)
    return digest.hexdigest()


def _current(path: Path, size: int, sha256: str) -> bool:
    try:
        info = path.lstat()
    except FileNotFoundError:
        return False
    return stat.S_ISREG(info.st_mode) and info.st_size == size and _hash(path) == sha256


def _prepare(directory: Path) -> None:
    if directory.is_symlink():
        raise PhoneError(f"{directory} is a symbolic link; refusing to copy through it")
    if directory.exists() and not directory.is_dir():
        raise PhoneError(f"{directory} is not a directory")
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)


def _copy(source: Path, directory: Path, name: str, sha256: str) -> None:
    fd, temporary = tempfile.mkstemp(prefix=f".{name}.", dir=directory)
    try:
        digest = hashlib.sha256()
        with os.fdopen(_open(source), "rb") as reader, os.fdopen(fd, "wb") as writer:
            while chunk := reader.read(_CHUNK):
                digest.update(chunk)
                writer.write(chunk)
            writer.flush()
            os.fsync(writer.fileno())
        if digest.hexdigest() != sha256:
            raise PhoneError(f"{source} changed while it was being copied; run this again")
        os.replace(temporary, directory / name)
    except BaseException:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(temporary)
        raise
    copied = _hash(directory / name)
    if copied != sha256:
        raise PhoneError(f"{directory / name} does not hash to its source after the copy")


def _write_sums(directory: Path, files: Sequence[Staged]) -> None:
    text = "".join(f"{f.sha256}  {f.name}\n" for f in sorted(files, key=lambda f: f.name))
    fd, temporary = tempfile.mkstemp(prefix=f".{SUMS}.", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, directory / SUMS)
    except BaseException:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(temporary)
        raise


def stage(
    found: Sequence[Found],
    directory: Path,
    *,
    free_at: Callable[[Path], int] = lambda path: shutil.disk_usage(path).free,
) -> Result:
    """Copy *found* into *directory*, write ``SHA256SUMS``, and remove our
    files whose region is gone. Raises :class:`PhoneError` before copying
    anything when the folder is unusable or too small."""
    _prepare(directory)
    wanted: list[tuple[Found, int, str, bool]] = []
    for item in found:
        size = item.source.lstat().st_size
        sha256 = _hash(item.source)
        wanted.append((item, size, sha256, _current(directory / item.name, size, sha256)))
    need = sum(size for _, size, _, current in wanted if not current)
    free = free_at(directory)
    if need > free:
        raise PhoneError(
            f"copying the phone files needs {need} bytes in {directory} and its file "
            f"system has {free} free; nothing was copied"
        )
    staged: list[Staged] = []
    for item, size, sha256, current in wanted:
        if not current:
            _copy(item.source, directory, item.name, sha256)
        staged.append(Staged(item.unit, item.name, size, sha256, copied=not current))
    names = {s.name for s in staged}
    removed: list[str] = []
    for entry in sorted(directory.iterdir()):
        if entry.name in names or entry.suffix not in SUFFIXES:
            continue
        if stat.S_ISREG(entry.lstat().st_mode):
            entry.unlink()
            removed.append(entry.name)
    _write_sums(directory, staged)
    return Result(directory=directory, files=tuple(staged), removed=tuple(removed))


@dataclass(frozen=True)
class Route:
    name: str
    laptop: str
    phone: str
    commands: tuple[str, ...]
    note: str


def routes(directory: Path) -> tuple[Route, ...]:
    """The ways to carry *directory* to a phone, none of which the engine runs."""
    folder = str(directory)
    return (
        Route(
            name="Laptop hotspot and a web browser",
            laptop="NetworkManager and python3, already on the machine; nothing to install",
            phone="a web browser, joined to the laptop's hotspot",
            commands=(
                "nmcli device wifi hotspot ssid hammunition-maps password '<8 or more characters>'",
                "ip -4 addr show  # the hotspot's address, 10.42.0.1 unless configured otherwise",
                f"python3 -m http.server {PORT} --bind 127.0.0.1 --directory {folder}",
                f"python3 -m http.server {PORT} --bind {HOTSPOT_ADDRESS} --directory {folder}",
            ),
            note=(
                f"Check the listing on this laptop first with the 127.0.0.1 line, then stop it "
                f"and serve on the hotspot's address; the phone opens "
                f"http://{HOTSPOT_ADDRESS}:{PORT}/. It is bound to that one address so the "
                f"files are served on the hotspot link only, never on another network this "
                f"laptop has joined; never run http.server without --bind, whose default is "
                f"every interface. Plain HTTP on a local link: {SUMS} is served beside the "
                f"files. Many phones can fetch at once. Ctrl-C stops it."
            ),
        ),
        Route(
            name="USB cable (MTP)",
            laptop=(
                "on KDE Plasma, kio-extras, installed with Plasma: Dolphin shows the phone; "
                "elsewhere gvfs-backends, jmtpfs or mtp-tools"
            ),
            phone="set to 'File transfer' when plugged in",
            commands=(),
            note=f"Copy the files from {folder} to the phone's Download folder, one phone at a time.",
        ),
        Route(
            name="adb (opt-in)",
            laptop=(
                "the package adb, which brings android-udev-rules, a system modification: "
                "sudo apt install adb"
            ),
            phone="Developer options with USB debugging turned on",
            commands=(f"adb push {folder}/. /sdcard/Download/hammunition/",),
            note="Most phones do not have USB debugging on; turn it off again afterwards.",
        ),
        Route(
            name="KDE Connect (opt-in)",
            laptop="the package kdeconnect: sudo apt install kdeconnect",
            phone="the KDE Connect app, installed while the phone had internet, and paired",
            commands=(),
            note="Works over the laptop's hotspot; share the files from Dolphin or the app.",
        ),
    )


APPS = (
    "Apps that read these files, from their own documentation only (none has been "
    "checked on a phone here): Cruiser, Locus Map, OruxMaps and c:geo read Mapsforge "
    ".map and .poi files; a Garmin handheld reads the .img from its card's Garmin "
    "folder, and OruxMaps reads .img too."
)


def render(result: Result, found_routes: Sequence[Route]) -> list[str]:
    """The text ``maps phone`` prints."""
    lines = [f"Phone files in {result.directory}:"]
    width = max((len(f.name) for f in result.files), default=0)
    for f in result.files:
        what = "copied" if f.copied else "already current"
        lines.append(f"  {f.name:<{width}}  {f.size:>12} bytes  {what}")
    for name in result.removed:
        lines.append(f"  removed {name}: its region is no longer installed")
    lines.append(f"  {SUMS}: check a copy with `sha256sum -c {SUMS}` in the folder")
    lines.append("")
    lines.append("Nothing was transferred. To carry them to a phone:")
    for number, route in enumerate(found_routes, 1):
        lines.append("")
        lines.append(f"{number}. {route.name}")
        lines.append(f"   On the laptop: {route.laptop}")
        lines.append(f"   On the phone: {route.phone}")
        lines.extend(f"     {command}" for command in route.commands)
        lines.append(f"   {route.note}")
    lines.append("")
    lines.append(APPS)
    return lines
