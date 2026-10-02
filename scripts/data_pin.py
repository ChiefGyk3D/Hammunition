# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""What the D-075 pin generators share: a fetch that asks one host only, and
the rewrite of a data unit's pinned lines with each found exactly once.

``scripts/gen_nasr_pin.py``, ``scripts/gen_eia860m_pin.py`` and
``scripts/gen_wri_pin.py`` each pin one file into its manifest, as
``scripts/gen_open-repeater-pin.py`` does (D-074): the sha256, the size,
the version, and where the source changes them the URL and the licence
line. A ``sed`` that matched nothing exits 0 (D-031), so every pattern must
match exactly one line, and the manifest is read back after the write.
"""

from __future__ import annotations

import http.client
import os
import re
import urllib.error
import urllib.request
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

#: The lines a generator owns, by name. ``url`` and ``licence`` are the data
#: block's; ``version`` is the manifest's.
PATTERNS: dict[str, re.Pattern[str]] = {
    "version": re.compile(r'^version: "[^"\n]*"$', re.MULTILINE),
    "url": re.compile(r"^(\s+)- url: \S+$", re.MULTILINE),
    "sha256": re.compile(r"^(\s+)sha256: [0-9a-f]{64}$", re.MULTILINE),
    "size": re.compile(r"^(\s+)size: \d+$", re.MULTILINE),
    "licence": re.compile(r'^(\s+)licence: "[^"\n]+"$', re.MULTILINE),
    "md5": re.compile(r"^# publisher MD5 \(the S3 ETag\): [0-9a-f]{32}$", re.MULTILINE),
}
_FORMS: dict[str, str] = {
    "version": 'version: "{}"',
    "url": r"\g<1>- url: {}",
    "sha256": r"\g<1>sha256: {}",
    "size": r"\g<1>size: {}",
    "licence": r'\g<1>licence: "{}"',
    "md5": "# publisher MD5 (the S3 ETag): {}",
}


def owned_problems(text: str, names: tuple[str, ...], file: str) -> list[str]:
    """Each line the generator owns, present exactly once, or why not."""
    return [
        f"{file} must hold exactly one {name} line the generator owns"
        for name in names
        if len(PATTERNS[name].findall(text)) != 1
    ]


def rewrite(text: str, values: Mapping[str, str]) -> str:
    """*text* with each named line replaced; SystemExit when any is not
    found exactly once."""
    out = text
    for name, value in values.items():
        if "\n" in value or "\\" in value or '"' in value:
            raise SystemExit(
                f"{name} {value!r} cannot be written on one line. Nothing was written."
            )
        out, count = PATTERNS[name].subn(_FORMS[name].format(value), out)
        if count != 1:
            raise SystemExit(f"the {name} line matched {count} times, not 1. Nothing was written.")
    return out


def write(path: Path, text: str) -> None:
    temporary = path.with_name(f".{path.name}.tmp")
    try:
        temporary.write_text(text)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


@dataclass(frozen=True)
class Answer:
    status: int
    headers: Mapping[str, str]
    body: bytes


class _HostOnly(urllib.request.HTTPRedirectHandler):
    def __init__(self, host: str) -> None:
        self.host = host

    def redirect_request(
        self,
        req: urllib.request.Request,
        fp: Any,
        code: int,
        msg: str,
        headers: Any,
        newurl: str,
    ) -> urllib.request.Request | None:
        if not newurl.startswith(self.host):
            raise SystemExit(f"refusing a redirect to {newurl!r}: only {self.host} is asked")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def ask(url: str, host: str, *, method: str = "GET", limit: int, timeout: float = 120.0) -> Answer:
    """*url* on *host* only, HTTPS, redirects kept to *host*. A 404 is an
    answer (the EIA move is found by one); any other failure is SystemExit."""
    if not url.startswith(host) or not host.startswith("https://"):
        raise SystemExit(f"refusing {url!r}: only {host} is asked")
    director = urllib.request.OpenerDirector()
    for handler in (
        urllib.request.HTTPSHandler(),
        _HostOnly(host),
        urllib.request.HTTPErrorProcessor(),
        urllib.request.HTTPDefaultErrorHandler(),
    ):
        director.add_handler(handler)
    request = urllib.request.Request(url, method=method, headers={"User-Agent": "hammunition"})
    try:
        with director.open(request, timeout=timeout) as response:
            status = int(response.status)
            headers = {k.lower(): v for k, v in response.headers.items()}
            body: bytes = b"" if method == "HEAD" else response.read(limit + 1)
    except urllib.error.HTTPError as exc:
        return Answer(int(exc.code), {k.lower(): v for k, v in exc.headers.items()}, b"")
    except (urllib.error.URLError, OSError, http.client.HTTPException) as exc:
        # http.client's own exceptions (a truncated answer) are not OSError.
        raise SystemExit(f"could not fetch {url}: {exc!r}") from None
    if len(body) > limit:
        raise SystemExit(f"{url} answered with more than {limit} bytes; refused")
    return Answer(status, headers, body)
