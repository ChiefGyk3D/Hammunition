# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""Take a URL's user and password out of text before it is shown or logged.

A mirror URL with ``user:password@`` is refused wherever a station or an
enrolment is saved, but the text of the refusal, or of a direct API call, must
not repeat what it refused (#381). The userinfo is what :func:`urllib.parse
.urlsplit` calls it: the part of the authority before its last ``@``. Nothing
after the authority (a path, a query) is touched.
"""

from __future__ import annotations

import re

#: ``scheme://`` then the authority, which ends at the first ``/``, ``?``, ``#``
#: or whitespace.
_AUTHORITY = re.compile(r"([A-Za-z][A-Za-z0-9+.\-]*://)([^/?#\s]*)")


def redact_url_text(text: str) -> str:
    """*text* with the userinfo of every URL in it removed."""

    def strip(match: re.Match[str]) -> str:
        _userinfo, at, host = match.group(2).rpartition("@")
        return match.group(1) + (host if at else match.group(2))

    return _AUTHORITY.sub(strip, text)
