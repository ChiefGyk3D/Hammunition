# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""Navit's stock config, rewritten for Hammunition's maps and voice.  D-057.

Built from the installed /etc/navit/navit.xml each time, so it follows
Debian's version; only four things change: speech, the mapset, where Navit
opens (``center=``, on the maps it has rather than the stock Munich) and the
gpsd vehicle's ``follow="1"``, which moves the view with the GPS. Anchored
string edits rather than an XML round-trip, which would drop Navit's comments
and its XInclude namespace; every anchor is looked for outside comments,
because the stock file's comments carry commented-out ``<vehicle>`` elements
of their own."""

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
_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
_NAVIT_CENTER = re.compile(r'(<navit\b[^>]*?\scenter=")[^"]*(")')
_VEHICLE = re.compile(r"<vehicle\b[^>]*>")
_GPSD_SOURCE = re.compile(r'\ssource="gpsd://')
_DISABLED = re.compile(r'\senabled="no"')
_FOLLOW = re.compile(r"\sfollow=")


class NavitConfigError(Exception):
    """The stock config is missing an anchor rewrite() needs, or no maps were given."""


def _outside_comments(pattern: re.Pattern[str], text: str) -> list[re.Match[str]]:
    comments = [m.span() for m in _COMMENT.finditer(text)]
    return [m for m in pattern.finditer(text) if not any(a <= m.start() < b for a, b in comments)]


def _gpsd_vehicles(text: str) -> list[re.Match[str]]:
    """The enabled ``<vehicle>`` open tags reading ``gpsd://``, comments excluded."""
    return [
        m
        for m in _outside_comments(_VEHICLE, text)
        if _GPSD_SOURCE.search(m.group()) and not _DISABLED.search(m.group())
    ]


def format_center(center: tuple[float, float]) -> str:
    """``"lon lat"`` to four decimal places, the stock file's own form."""
    lon, lat = center
    return f"{lon:.4f} {lat:.4f}"


def rewrite(stock: str, maps: Sequence[Path], center: tuple[float, float] | None = None) -> str:
    """Return *stock* for *maps*: speech through espeak-ng, one enabled mapset
    of *maps*, the gpsd vehicle following the position and, given *center*
    as (lon, lat), Navit opening there.

    Raises :class:`NavitConfigError` naming what is missing: no maps, no
    ``<speech type="cmdline">`` element, not exactly one enabled
    ``<mapset>``, not exactly one enabled gpsd ``<vehicle>``, or -- with a
    *center* -- no ``<navit center=>``. Navit's own comment says only one
    mapset may be enabled at a time; if the stock file ever violates that,
    replacing just the first match would silently leave a second one enabled
    alongside ours, which Navit would mis-load. Fail loudly instead of
    guessing which one to keep; the vehicle is refused on the same reasoning.

    ``follow="1"`` is what Navit's own stock comment says to add "to have the
    view centered on your position"; without it the view never moved to the
    GPS, even with a 3D fix (bench, 2026-09-28). A vehicle that already says
    ``follow=`` anything is the operator's or Debian's choice and is left alone.
    """
    if not maps:
        raise NavitConfigError("no converted maps to point Navit at")
    if not _SPEECH.search(stock):
        raise NavitConfigError(f'{STOCK} has no <speech type="cmdline"> element to replace')
    enabled_mapsets = list(_ENABLED_MAPSET.finditer(stock))
    if len(enabled_mapsets) != 1:
        raise NavitConfigError(
            f"{STOCK} has {len(enabled_mapsets)} enabled <mapset> elements, need exactly 1"
        )
    vehicles = _gpsd_vehicles(stock)
    if len(vehicles) != 1:
        raise NavitConfigError(
            f'{STOCK} has {len(vehicles)} enabled <vehicle source="gpsd://..."> elements, '
            f"need exactly 1 to follow the GPS"
        )
    if center is not None and not _outside_comments(_NAVIT_CENTER, stock):
        raise NavitConfigError(f'{STOCK} has no <navit center="..."> attribute to replace')

    out = _SPEECH.sub(
        lambda _: '<speech type="cmdline" data="espeak-ng \'%s\'" cps="15"/>', stock, count=1
    )

    ours = "\n".join(
        f'\t\t\t<map type="binfile" enabled="yes" data={quoteattr(str(p))}/>' for p in maps
    )
    mapset = f'<mapset enabled="yes">\n{ours}\n\t\t</mapset>'
    out = _ENABLED_MAPSET.sub(lambda _: mapset, out, count=1)

    (vehicle,) = _gpsd_vehicles(out)
    tag = vehicle.group()
    if not _FOLLOW.search(tag):
        source = _GPSD_SOURCE.search(tag)
        assert source is not None  # _gpsd_vehicles matched on it
        tag = f'{tag[: source.start()]} follow="1"{tag[source.start() :]}'
        out = out[: vehicle.start()] + tag + out[vehicle.end() :]

    if center is not None:
        anchor = _outside_comments(_NAVIT_CENTER, out)[0]
        out = (
            out[: anchor.start()]
            + f"{anchor.group(1)}{format_center(center)}{anchor.group(2)}"
            + out[anchor.end() :]
        )
    return out
