# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""The ACMA's Register of Radiocommunications Licences as a file.  D-074,
amended 2026-10-01.

The Australian regulator publishes the whole register as one zip, rebuilt
every day at one URL. Measured on 2026-10-01: 67,513,955 bytes, 31 members,
served from Azure Blob storage. **No digest is published**: the ``ETag``
(``0x8DF200353F0B4AF`` that day) is Azure's version stamp, not an MD5, and
no ``Content-MD5`` is stored even when a current storage API version is
asked for. And a sha256 pin would die every day. So nothing is pinned by
Hammunition, and what the engine checks is what the file carries itself:
every member's CRC-32 (a damaged or truncated download fails it), the
tables the repeater import reads, and their header rows. That catches a
damaged download, never a deliberately altered one, and every disclosure
says "unverified" (the FSTopo ruling of 2026-10-01: such a unit is
installed by name only, in no profile).

Nothing here reads ``client.csv``, the table of licensees' names and
addresses; the licence (clause 8) forbids putting a natural person's in a
derivative, and the repeater layer needs none of it.
"""

from __future__ import annotations

import urllib.error
import urllib.request
import zipfile
from dataclasses import dataclass
from datetime import date
from pathlib import Path

__all__ = [
    "CHECK",
    "FETCH_LIMIT",
    "FILE_NAME",
    "MEASURED_ON",
    "MEASURED_SIZE",
    "TABLES",
    "UNIT",
    "URL",
    "VERIFIED_BY",
    "AcmaError",
    "AcmaProbe",
    "RegisterCheck",
    "check_register",
]

UNIT = "acma-register"
URL = "https://cdn.acma.gov.au/rrl/spectra_rrl.zip"
#: The name it is installed and mirrored under (D-070's ``<unit>/<name>``).
FILE_NAME = "spectra_rrl.zip"
#: What the plan prints as "about": the file changes size every day.
MEASURED_SIZE = 67_513_955
MEASURED_ON = "2026-10-01"
#: The download is abandoned past this: four times the measured size.
FETCH_LIMIT = 256 * 1024 * 1024
#: The most the members may declare uncompressed together (603 MB measured),
#: so a crafted archive cannot have the check inflate without bound.
INFLATE_LIMIT = 2 * 1024 * 1024 * 1024
#: ``hammunition artifacts``' name for this check (D-070's ``check``).
CHECK = "unverified-zip"
VERIFIED_BY = (
    "unverified: the ACMA publishes no checksum (its ETag is a storage version stamp, "
    "not a digest) and rebuilds the file daily, so nothing is pinned by Hammunition; "
    "the zip's own CRC-32s and the tables the repeater import reads are checked, which "
    "catches a damaged download, not an altered one"
)

#: Each table the import reads, and the columns it needs, as the 2026-10-01
#: file names them (upper case, the order irrelevant).
TABLES: dict[str, tuple[str, ...]] = {
    "licence.csv": ("LICENCE_NO", "SS_ID", "STATUS"),
    "device_details.csv": (
        "LICENCE_NO",
        "FREQUENCY",
        "EMISSION",
        "DEVICE_TYPE",
        "SITE_ID",
        "EFL_SYSTEM",
        "CALL_SIGN",
    ),
    "site.csv": ("SITE_ID", "LATITUDE", "LONGITUDE", "NAME", "STATE", "SITE_PRECISION"),
}
LICENCE_FILE = "LICENCE.TXT"


class AcmaError(Exception):
    """The file is not a whole ACMA register, named with the reason."""


@dataclass(frozen=True)
class RegisterCheck:
    """What :func:`check_register` found: the register's own date (its
    ``licence.csv`` member's timestamp, the ACMA's local time) and the
    members it holds."""

    day: date
    members: int


def _header(archive: zipfile.ZipFile, name: str) -> list[str]:
    with archive.open(name) as handle:
        line = handle.readline(64 * 1024)
    text = line.decode("utf-8-sig", errors="replace").strip()
    return [cell.strip().strip('"').upper() for cell in text.split(",")]


def register_day(archive: zipfile.ZipFile) -> date:
    """The day the register was written, from ``licence.csv``'s timestamp."""
    year, month, day = archive.getinfo("licence.csv").date_time[:3]
    return date(year, month, day)


def check_register(path: Path, *, crc: bool = True) -> RegisterCheck:
    """*path* as an ACMA register, or :class:`AcmaError` naming why not.

    Checked: it is a zip; it holds ``LICENCE.TXT`` and each table in
    :data:`TABLES` with the columns named there; the members declare no more
    than :data:`INFLATE_LIMIT` uncompressed; and, with *crc*, every member's
    CRC-32 matches its bytes (all of them are read once). The import passes
    ``crc=False``: the install already ran the full check."""
    try:
        archive = zipfile.ZipFile(path)
    except (zipfile.BadZipFile, OSError) as exc:
        raise AcmaError(f"{path} is not a zip archive ({exc})") from None
    with archive:
        infos = archive.infolist()
        names = {i.filename for i in infos}
        missing = [n for n in (*TABLES, LICENCE_FILE) if n not in names]
        if missing:
            raise AcmaError(
                f"{path} is not the ACMA register: it lacks {', '.join(missing)} "
                f"(a web page or another archive is not the register)"
            )
        declared = sum(i.file_size for i in infos)
        if declared > INFLATE_LIMIT:
            raise AcmaError(
                f"{path}: its members declare {declared} bytes uncompressed, past the "
                f"{INFLATE_LIMIT}-byte limit; refused"
            )
        try:
            for table, columns in TABLES.items():
                header = _header(archive, table)
                absent = [c for c in columns if c not in header]
                if absent:
                    raise AcmaError(
                        f"{path}: {table} has no column {', '.join(absent)}; the register's "
                        f"layout changed and the import would misread it"
                    )
            if crc:
                try:
                    bad = archive.testzip()
                except zipfile.BadZipFile as exc:  # Python 3.12+ raises for a bad CRC
                    raise AcmaError(f"{path}: {exc}: a damaged download") from None
                if bad is not None:
                    raise AcmaError(
                        f"{path}: the member {bad} does not match its CRC-32: a damaged download"
                    )
            day = register_day(archive)
        except (
            zipfile.BadZipFile,
            OSError,
            EOFError,
            ValueError,
            NotImplementedError,
            RuntimeError,
        ) as exc:
            # zlib.error is not an OSError; testzip and open raise BadZipFile
            # for it, and a truncated member raises EOFError. A member in a
            # compression zipfile cannot read raises NotImplementedError, an
            # encrypted one RuntimeError (final review).
            raise AcmaError(f"{path}: the archive is damaged ({exc})") from None
        return RegisterCheck(day=day, members=len(infos))


class AcmaProbe:
    """A ``HEAD`` to the register's one URL, for ``hammunition artifacts``:
    the day's size, which nothing else announces. Only the HTTP handlers:
    no redirect is followed, and nothing but :data:`URL` is asked."""

    def __init__(self, *, timeout: float = 30.0) -> None:
        self.timeout = timeout
        opener = urllib.request.OpenerDirector()
        opener.add_handler(urllib.request.HTTPSHandler())
        self._opener = opener

    def size(self, url: str) -> int:
        if url != URL:
            raise AcmaError(f"refusing {url!r}: only {URL} is asked")
        request = urllib.request.Request(url, headers={"User-Agent": "hammunition"})
        request.method = "HEAD"
        try:
            response = self._opener.open(request, timeout=self.timeout)
        except (urllib.error.URLError, OSError) as exc:
            raise AcmaError(f"{url} could not be reached: {exc}") from None
        if response is None:  # pragma: no cover - no handler claimed the scheme
            raise AcmaError(f"no handler would ask {url!r}")
        with response:
            length = response.headers.get("Content-Length") or ""
            if response.status != 200 or not length.isdigit():
                raise AcmaError(
                    f"{url} answered HTTP {response.status} with no usable Content-Length"
                )
            return int(length)
