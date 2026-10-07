# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import os
import stat
import urllib.error
import urllib.request
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import IO
from urllib.parse import quote, unquote, urlsplit

from hammunition.backends import BackendError
from hammunition.catalogue import safe_relative, valid_enrolment_id
from hammunition.fetch import MIRROR_TIMEOUT, TransportUnreachable
from hammunition.station import _check_mirror


def read_catalogue(source: MirrorTransport) -> bytes:
    try:
        return source.read("catalogue.json", max_bytes=32 * 1024 * 1024)
    except BackendError as exc:
        url = source.base.rstrip("/") + "/catalogue.json"
        raise BackendError(
            f"no catalogue at {url}: {exc}. "
            "Enrol a Bunker that serves one, or run without --offline."
        ) from exc


class MirrorTransport:
    def __init__(self, base: str, enrolment_id: str | None = None) -> None:
        self.base = _check_mirror(base).rstrip("/")
        self.parts = urlsplit(self.base)
        if enrolment_id is not None and not valid_enrolment_id(enrolment_id):
            raise BackendError("invalid enrolment id")
        self.enrolment_id = enrolment_id
        self.opener = urllib.request.OpenerDirector()
        for handler in (
            urllib.request.HTTPHandler(),
            urllib.request.HTTPSHandler(),
            urllib.request.HTTPErrorProcessor(),
            urllib.request.HTTPDefaultErrorHandler(),
        ):
            self.opener.add_handler(handler)

    @contextmanager
    def open(self, url: str) -> Iterator[IO[bytes]]:
        parts = urlsplit(url)
        prefix = self.parts.path.rstrip("/") + "/"
        if (
            (parts.scheme, parts.netloc) != (self.parts.scheme, self.parts.netloc)
            or not parts.path.startswith(prefix)
            or parts.query
            or parts.fragment
        ):
            raise BackendError("mirror request leaves the configured base")
        relative = safe_relative(unquote(parts.path[len(prefix) :]), "mirror request")
        if parts.scheme == "file":
            directory = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
            fd = -1
            try:
                components = [*Path(unquote(self.parts.path)).parts[1:], *relative.split("/")]
                for index, component in enumerate(components):
                    safe_relative(component, "file mirror component")
                    flags = os.O_RDONLY | os.O_NOFOLLOW
                    if index < len(components) - 1:
                        flags |= os.O_DIRECTORY
                    child = os.open(component, flags, dir_fd=directory)
                    os.close(directory)
                    directory = child
                fd, directory = directory, -1
                if not stat.S_ISREG(os.fstat(fd).st_mode):
                    raise BackendError("file mirror target is not a regular file")
                stream = os.fdopen(fd, "rb")
                fd = -1
            except OSError as exc:
                raise BackendError(f"file mirror {relative}: {exc}") from exc
            finally:
                if directory >= 0:
                    os.close(directory)
                if fd >= 0:
                    os.close(fd)
            with stream:
                yield stream
            return
        headers = {"User-Agent": "hammunition"}
        if self.enrolment_id is not None:
            headers["X-Hammunition-Enrolment"] = self.enrolment_id
        try:
            response = self.opener.open(
                urllib.request.Request(url, headers=headers), timeout=MIRROR_TIMEOUT
            )
            if response is None:
                raise BackendError("no mirror transport handler")
        except urllib.error.HTTPError as exc:
            raise BackendError(
                f"mirror returned HTTP {exc.code}; redirects are not followed"
            ) from exc
        except (urllib.error.URLError, OSError) as exc:
            raise TransportUnreachable(f"mirror could not be reached: {exc}") from exc

        with response:
            yield response

    def read(self, relative: str, *, max_bytes: int) -> bytes:
        relative = safe_relative(relative, "mirror path")
        url = self.base.rstrip("/") + "/" + "/".join(quote(p, safe="") for p in relative.split("/"))
        with self.open(url) as stream:
            raw = stream.read(max_bytes + 1)
        if len(raw) > max_bytes:
            raise BackendError(f"{relative}: larger than {max_bytes} bytes")
        return raw
