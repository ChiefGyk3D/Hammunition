# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""Navit's stock config, rewritten for Hammunition's maps and voice.  D-057.

Built from the installed /etc/navit/navit.xml each time, so it follows
Debian's version; only two things change. Anchored string edits rather than an
XML round-trip, which would drop Navit's comments and its XInclude namespace."""

from __future__ import annotations

import re
from collections.abc import Sequence
from pathlib import Path
from xml.sax.saxutils import quoteattr

STOCK = Path("/etc/navit/navit.xml")
_SPEECH = re.compile(r'<speech type="cmdline" data="[^"]*"[^>]*/>')
# The whole block, open tag through close tag, not just the open tag: Navit's
# stock file leaves the other mapsets already enabled="no", but the one this
# targets carries the $NAVIT_SHAREDIR/maps/*.xml XInclude as its content, and
# that text has to go too, not just the attribute wrapping it.
_ENABLED_MAPSET = re.compile(r'<mapset enabled="yes">.*?</mapset>', re.DOTALL)


class NavitConfigError(Exception):
    """The stock config is missing an anchor rewrite() needs, or no maps were given."""


def rewrite(stock: str, maps: Sequence[Path]) -> str:
    """Return *stock* with speech routed to espeak-ng and one enabled mapset of *maps*.

    Raises :class:`NavitConfigError` naming what is missing: no maps, no
    ``<speech type="cmdline">`` element, or no enabled ``<mapset>``.
    """
    if not maps:
        raise NavitConfigError("no converted maps to point Navit at")
    if not _SPEECH.search(stock):
        raise NavitConfigError(f'{STOCK} has no <speech type="cmdline"> element to replace')
    if not _ENABLED_MAPSET.search(stock):
        raise NavitConfigError(f"{STOCK} has no enabled <mapset> to replace")

    out = _SPEECH.sub(
        lambda _: '<speech type="cmdline" data="espeak-ng \'%s\'" cps="15"/>', stock, count=1
    )

    ours = "\n".join(
        f'\t\t\t<map type="binfile" enabled="yes" data={quoteattr(str(p))}/>' for p in maps
    )
    mapset = f'<mapset enabled="yes">\n{ours}\n\t\t</mapset>'
    return _ENABLED_MAPSET.sub(lambda _: mapset, out, count=1)
