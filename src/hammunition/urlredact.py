# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""Take a URL's user and password out of text before it is shown or logged.

A mirror URL with ``user:password@`` is refused wherever a station or an
enrolment is saved, but the text of the refusal, or of a direct API call, must
not repeat what it refused (#381). The userinfo is what :func:`urllib.parse
.urlsplit` calls it: the part of the authority before its last ``@``. Nothing
after the authority (a path, a query) is touched.

It fails closed. An authority that holds a ``@`` but that ``urlsplit`` refuses,
that does not round-trip through it, or that carries a control character is
replaced whole, host included, rather than trusted to be split correctly.
"""

from __future__ import annotations

import re
import urllib.parse

#: ``scheme://`` then the authority, which ends at the first ``/``, ``?``, ``#``
#: or whitespace.
_AUTHORITY = re.compile(r"([A-Za-z][A-Za-z0-9+.\-]*://)([^/?#\s]*)")

#: What stands in for an authority that could not be split with confidence.
REDACTED = "<redacted>"


def _parses_cleanly(scheme: str, authority: str) -> bool:
    if any(ord(c) < 32 or ord(c) == 127 for c in authority):
        return False
    try:
        parts = urllib.parse.urlsplit(scheme + authority)
        if parts.netloc != authority:
            return False  # urlsplit dropped or changed something
        _ = (parts.hostname, parts.port)  # read for the errors they can raise
    except ValueError:
        return False
    return True


def redact_url_text(text: str) -> str:
    """*text* with the userinfo of every URL in it removed."""

    def strip(match: re.Match[str]) -> str:
        scheme, authority = match.group(1), match.group(2)
        if "@" not in authority:
            return match.group(0)
        if not _parses_cleanly(scheme, authority):
            return scheme + REDACTED
        return scheme + authority.rpartition("@")[2]

    return _AUTHORITY.sub(strip, text)
