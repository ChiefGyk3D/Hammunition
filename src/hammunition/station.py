# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""Station-local values: callsign, grid square, and the rest.  DESIGN.md §15.5.

The open design question this closes has been blocking since the 1.0 packet
core was admitted. AX.25 writes a callsign into ``/etc/ax25/axports``, Direwolf
is admitted *with configuration rather than merely installation*, and
``linbpq``'s manifest templates ``NODECALL``, ``NODEALIAS`` and ``LOCATOR``.
Until now any manifest carrying a ``config_files`` block failed the whole
transaction, so the `packet` profile — the reason the 73Linux delta was
acquired at all — could not be installed by anyone.

Three properties, in order of how much they matter.

**Missing values defer, they do not block.** A profile with twenty packages and
one templated config file installs the twenty packages and reports the one file
as outstanding, with the values it needs and how to supply them. Refusing the
whole transaction because a callsign is unknown gets an operator nowhere; a
station that is ninety-five per cent built and honest about the rest is a
success. Refusing was the old behaviour and it is what this replaces.

**Values are never invented.** There is no default callsign, no placeholder, no
"CHANGEME". A file templated with a made-up callsign would transmit it. What
this cannot fill in, it declines to write and says so.

**The file lives outside the repository by construction.** It is written to the
operator's XDG config directory through :mod:`hammunition.paths`, which is
owner-aware — running under ``sudo`` still resolves the invoking user's home
rather than root's. The repository's ``.gitignore`` additionally covers
``station.local.yml`` so that a copy kept beside a checkout for testing cannot
be committed by accident.

Validation is deliberately loose. Callsign formats vary by country far more
than the common regexes admit -- prefixes, suffixes, portable indicators,
special event calls -- so this checks the shape a *file format* needs (no
whitespace, plausible length, no shell metacharacters) and leaves the question
of whether a callsign is real to the licensing authority that issued it.
"""

from __future__ import annotations

import os
import re
import sys
import urllib.parse
from collections.abc import Callable, Sequence
from dataclasses import dataclass, fields
from pathlib import Path

import yaml

from .kiwix import BOOK_ID
from .maidenhead import centre
from .paths import owner_aware_dir

__all__ = [
    "DERIVED",
    "STATION_FIELDS",
    "TEMPLATE_VARIABLES",
    "Station",
    "StationError",
    "config_path",
    "load_station",
    "prompt_for",
    "save_station",
]


class StationError(ValueError):
    """A station value is unusable, or the file holding them is malformed."""


#: Loose on purpose. Callsigns carry prefixes, suffixes and portable
#: indicators; a strict pattern rejects real ones. This is the shape a
#: configuration file needs, not a licensing check.
CALLSIGN = re.compile(r"^[A-Z0-9]{1,3}[0-9][A-Z0-9]{0,3}(?:/[A-Z0-9]{1,4})*$")

#: Maidenhead: two letters, two digits, optionally two more letters, and the
#: extended pairs some software wants. Case is normalised before matching.
GRID_SQUARE = re.compile(r"^[A-R]{2}[0-9]{2}(?:[A-X]{2}(?:[0-9]{2})?)?$")

#: How often a downloaded map region is refreshed. ``yearly`` is the default
#: applied when nothing is set, never invented as a stored value.
FRESHNESS = ("yearly", "monthly", "latest")

#: A Geofabrik download path: lowercase words joined by ``/``, e.g.
#: ``north-america/us/vermont``. No leading/trailing slash, no ``..``, no
#: whitespace -- the shape a URL path segment needs, not a check that the
#: region exists in Geofabrik's index.
REGION = re.compile(r"[a-z0-9-]+(/[a-z0-9-]+)*")

#: Station fields not named in this set are also `Station` dataclass fields,
#: but map settings are data the maps subsystem reads directly -- never a
#: `{station.*}` template variable -- so they are excluded here.
_MAP_FIELDS = frozenset({"map_regions", "map_freshness"})

#: Station values that are never a `{station.*}` template variable: the map
#: settings, the LAN mirror the verified fetch tries first (D-070), and the
#: Kiwix books chosen for `kiwix-library` (D-066).
_NOT_TEMPLATES = _MAP_FIELDS | {"mirror", "reference_books"}

#: A mirror is fetched by :class:`hammunition.fetch.UrllibTransport`, which
#: speaks these and nothing else. Plain http is allowed on purpose: the
#: content is public data and the check is the hash, not the transport.
MIRROR_SCHEMES = ("http", "https")


def _check_mirror(url: str) -> str:
    """*url* stripped, or a StationError saying what a mirror URL must be.

    The shape a base URL needs and nothing more: whether the host is on the
    LAN cannot be decided from a name without resolving it, and is the
    operator's statement to make (D-070). A user or password is refused,
    because the station file is no place for a credential."""
    value = url.strip()
    problem = None
    try:
        parts = urllib.parse.urlsplit(value)
        parts.port  # noqa: B018 - read for its ValueError on a bad port
    except ValueError as exc:
        raise StationError(
            f"mirror {url!r} is not usable: {exc}. Expected a LAN address such as "
            f"http://bunker.lan:8080/ (D-070)."
        ) from exc
    if parts.scheme not in MIRROR_SCHEMES:
        problem = "it must start with http:// or https://"
    elif not parts.hostname or any(c.isspace() for c in value):
        problem = "it names no host"
    elif parts.username is not None or parts.password is not None:
        problem = "it carries a user or password, and the station file holds no credentials"
    elif parts.query or parts.fragment or "?" in value or "#" in value:
        problem = "it has a query or a fragment; a mirror is a base URL"
    if problem is not None:
        raise StationError(
            f"mirror {url!r} is not usable: {problem}. Expected a LAN address such as "
            f"http://bunker.lan:8080/ (D-070)."
        )
    return value


@dataclass(frozen=True)
class Station:
    """What a manifest's `{station.*}` templates can reference.

    Every field is optional. A station being partly known is the normal case
    and is what makes deferral possible: `callsign` alone is enough for several
    manifests, and nothing needs all of them.
    """

    callsign: str | None = None
    grid_square: str | None = None
    node_alias: str | None = None
    """A short name a packet node answers to, distinct from the callsign."""
    map_regions: tuple[str, ...] = ()
    """Geofabrik region paths to carry offline maps for, e.g.
    ``north-america/us/vermont``. Several at once; none means the map data
    units are deferred (D-035)."""
    map_freshness: str | None = None
    """``yearly`` (the default when unset), ``monthly`` or ``latest``."""
    reference_books: tuple[str, ...] = ()
    """Kiwix book ids from ``catalog/data/kiwix-books.yaml``, e.g.
    ``ham.stackexchange.com_en_all``. None means ``kiwix-library`` is
    deferred (D-066). Which books somebody reads is not where they are, so
    these are printed where map regions are only counted."""
    mirror: str | None = None
    """A LAN mirror of the catalog's data artifacts, tried before the
    publisher and verified the same way (D-070). Never an internet address."""

    def __post_init__(self) -> None:
        if self.callsign is not None:
            normalised = self.callsign.strip().upper()
            if not CALLSIGN.match(normalised):
                raise StationError(
                    f"callsign {self.callsign!r} does not look like a callsign. "
                    f"Expected something like M0ABC, W1AW/4 or VK2XYZ — letters, "
                    f"digits and optional /suffix, no spaces."
                )
            object.__setattr__(self, "callsign", normalised)
        if self.grid_square is not None:
            normalised = self.grid_square.strip()
            canonical = normalised[:2].upper() + normalised[2:4] + normalised[4:].lower()
            if not GRID_SQUARE.match(canonical.upper()):
                raise StationError(
                    f"grid square {self.grid_square!r} is not a Maidenhead locator. "
                    f"Expected four or six characters like IO91 or IO91wm."
                )
            object.__setattr__(self, "grid_square", canonical)
        if self.node_alias is not None:
            alias = self.node_alias.strip().upper()
            if not alias or len(alias) > 6 or not alias.isalnum():
                raise StationError(
                    f"node alias {self.node_alias!r} must be one to six alphanumeric "
                    f"characters — packet node aliases are short by protocol."
                )
            object.__setattr__(self, "node_alias", alias)
        regions = tuple(r.strip() for r in self.map_regions)
        for region in regions:
            if not REGION.fullmatch(region):
                raise StationError(
                    f"map region {region!r} is not a Geofabrik region path "
                    f"(lowercase words joined by '/', e.g. north-america/us/vermont). "
                    f"`hammunition maps regions` lists them."
                )
        object.__setattr__(self, "map_regions", regions)
        books = tuple(b.strip() for b in self.reference_books)
        for book in books:
            if not BOOK_ID.fullmatch(book):
                raise StationError(
                    f"reference book {book!r} is not a Kiwix book id (lowercase, no spaces, "
                    f"e.g. ham.stackexchange.com_en_all). `hammunition reference books` "
                    f"lists them."
                )
        object.__setattr__(self, "reference_books", tuple(dict.fromkeys(books)))
        if self.map_freshness is not None and self.map_freshness not in FRESHNESS:
            raise StationError(
                f"map freshness {self.map_freshness!r} is not one of {', '.join(FRESHNESS)}"
            )
        if self.mirror is not None:
            object.__setattr__(self, "mirror", _check_mirror(self.mirror))

    @property
    def freshness(self) -> str:
        """The effective freshness: what is stored, or ``yearly`` if unset."""
        return self.map_freshness or "yearly"

    def get(self, variable: str) -> str | None:
        """The value a `{station.<variable>}` reference resolves to, or None.

        A derived variable (:data:`DERIVED`) is computed from the stored value
        it names, and is None when that value is unset *or* cannot give it --
        :meth:`missing` and :meth:`unusable` say which.
        """
        if variable in DERIVED:
            source, derive, _why = DERIVED[variable]
            stored = self.get(source)
            return derive(stored) if stored else None
        return getattr(self, variable, None) if variable in STATION_FIELDS else None

    def missing(self, variables: set[str]) -> tuple[str, ...]:
        """Of *variables*, the stored values this station does not have.

        Named as the operator sets them: a derived variable reports the value
        it comes from (``latitude`` needs ``grid_square``), because that is
        what ``station set`` and the install prompt can ask for.
        """
        out: set[str] = set()
        for variable in variables:
            source = DERIVED[variable][0] if variable in DERIVED else variable
            if not self.get(source):
                out.add(source)
        return tuple(sorted(out))

    def unusable(self, variables: set[str]) -> tuple[str, ...]:
        """Why a derived variable cannot be had although its source is set.

        One sentence per variable, sorted. Empty when every derived variable
        in *variables* either resolves or is simply :meth:`missing`.
        """
        reasons: set[str] = set()
        for variable in variables:
            if variable not in DERIVED:
                continue
            source, _derive, why = DERIVED[variable]
            stored = self.get(source)
            if stored and self.get(variable) is None:
                reasons.add(why.format(value=stored))
        return tuple(sorted(reasons))

    def as_dict(self) -> dict[str, str | list[str]]:
        result: dict[str, str | list[str]] = {
            f.name: v
            for f in fields(self)
            if f.name not in _NOT_TEMPLATES and (v := getattr(self, f.name))
        }
        if self.map_regions:
            result["map_regions"] = list(self.map_regions)
        if self.map_freshness is not None:
            result["map_freshness"] = self.map_freshness
        if self.reference_books:
            result["reference_books"] = list(self.reference_books)
        if self.mirror is not None:
            result["mirror"] = self.mirror
        return result


#: The variables a manifest may reference. Kept beside the dataclass so a
#: template naming something unknown is a reportable error rather than an
#: empty substitution. Map settings, the mirror and the books are excluded -- they are
#: read directly by the engine, never templated into a config file.
STATION_FIELDS: frozenset[str] = frozenset(f.name for f in fields(Station)) - _NOT_TEMPLATES

#: An AX.25 address: one to six letters and digits. The SSID is a separate
#: field of the frame, and a ``/P`` or ``W1AW/4`` suffix cannot be carried at
#: all -- Direwolf's example config says "up to 6 letters and digits with an
#: optional ssid", and ``axports`` and aprx take the same address.
AX25_CALLSIGN = re.compile(r"^[A-Z0-9]{1,6}$")


def _ax25(callsign: str) -> str | None:
    return callsign if AX25_CALLSIGN.match(callsign) else None


def _latitude(grid: str) -> str:
    return f"{centre(grid)[0]:.4f}"


def _longitude(grid: str) -> str:
    return f"{centre(grid)[1]:.4f}"


#: Template variables computed from a stored value rather than stored. Each is
#: ``(stored value it comes from, how, why it can be unavailable when that
#: value is set)``. Nothing is invented: a derivation that cannot be made
#: defers the file (D-035), with the reason, exactly as an unset value does.
#: ``latitude``/``longitude`` are the centre of the grid square, to four
#: decimal places (gpredict's own sample file uses four); the precision is the
#: square's, never more (:mod:`hammunition.maidenhead`).
DERIVED: dict[str, tuple[str, Callable[[str], str | None], str]] = {
    "ax25_callsign": (
        "callsign",
        _ax25,
        "the callsign {value} is not an AX.25 address (one to six letters and digits, "
        "no /suffix), so AX.25 and APRS cannot carry it",
    ),
    "latitude": ("grid_square", _latitude, "latitude cannot be derived from {value}"),
    "longitude": ("grid_square", _longitude, "longitude cannot be derived from {value}"),
}

#: Every name a ``{station.<name>}`` reference may use: stored and derived.
TEMPLATE_VARIABLES: frozenset[str] = STATION_FIELDS | frozenset(DERIVED)

#: Every value the station file may hold, template variable or not -- what
#: `load_station` accepts without raising "sets values nothing can use".
_KNOWN_KEYS: frozenset[str] = frozenset(f.name for f in fields(Station))

PROMPTS: dict[str, str] = {
    "callsign": "Your callsign (transmitted, so it must be yours)",
    "grid_square": "Your Maidenhead grid square, four or six characters",
    "node_alias": "Short alias for a packet node, up to six characters",
}


def config_path(owner: str | None = None) -> Path:
    """Where station values live. Outside the repository, by construction."""
    return (
        owner_aware_dir(
            xdg_var="XDG_CONFIG_HOME",
            home_relative=(".config",),
            owner=owner,
        )
        / "station.yml"
    )


def load_station(path: Path | None = None, owner: str | None = None) -> Station:
    """Read the station file, or return an empty station if there is none.

    An absent file is not an error: an operator who has never set a callsign is
    the starting state, not a fault.
    """
    target = path or config_path(owner)
    if not target.exists():
        return Station()
    try:
        data = yaml.safe_load(target.read_text()) or {}
    except yaml.YAMLError as exc:
        raise StationError(f"{target} is not valid YAML: {exc}") from exc
    if not isinstance(data, dict):
        raise StationError(f"{target} must contain a mapping, not {type(data).__name__}")
    unknown = sorted(set(data) - _KNOWN_KEYS)
    if unknown:
        raise StationError(
            f"{target} sets values nothing can use: {', '.join(unknown)}. "
            f"Known values: {', '.join(sorted(_KNOWN_KEYS))}."
        )

    def _str(key: str) -> str | None:
        value = data.get(key)
        return str(value) if value is not None else None

    regions = data.get("map_regions")
    books = data.get("reference_books")
    return Station(
        callsign=_str("callsign"),
        grid_square=_str("grid_square"),
        node_alias=_str("node_alias"),
        map_regions=tuple(str(r) for r in regions) if regions is not None else (),
        map_freshness=_str("map_freshness"),
        reference_books=tuple(str(b) for b in books) if books is not None else (),
        mirror=_str("mirror"),
    )


def save_station(station: Station, path: Path | None = None, owner: str | None = None) -> Path:
    """Write the station file, creating its directory. Returns the path."""
    target = path or config_path(owner)
    target.parent.mkdir(parents=True, exist_ok=True)
    body = (
        "# Station-local values, used to fill in configuration this catalog\n"
        "# writes on your behalf. Written by `hammunition station set`.\n"
        "#\n"
        "# Your callsign is transmitted. It identifies you and it must be yours.\n"
        + yaml.safe_dump(station.as_dict(), sort_keys=True, default_flow_style=False)
    )
    target.write_text(body)
    os.chmod(target, 0o600)
    return target


def prompt_for(variables: Sequence[str], station: Station) -> Station:
    """Ask for the values *variables* names that *station* does not have.

    Returns a new Station. Only called when standard input is a terminal --
    a non-interactive run defers instead, which is the whole point.
    """
    # Map settings and the mirror are not template variables (`variable` only ever names one
    # of STATION_FIELDS -- `station.get` gates on that), so they are carried
    # through unchanged rather than passed through this dict of strings.
    values: dict[str, str] = {f: v for f in STATION_FIELDS if (v := station.get(f)) is not None}
    for variable in variables:
        if station.get(variable):
            continue
        question = PROMPTS.get(variable, f"Value for {variable}")
        while True:
            answer = input(f"{question}: ").strip()
            if not answer:
                print("  (skipped — the configuration needing it will not be written)")
                break
            try:
                Station(
                    map_regions=station.map_regions,
                    map_freshness=station.map_freshness,
                    reference_books=station.reference_books,
                    mirror=station.mirror,
                    **{**values, variable: answer},
                )
            except StationError as exc:
                print(f"  {exc}")
                continue
            values[variable] = answer
            break
    return Station(
        map_regions=station.map_regions,
        map_freshness=station.map_freshness,
        reference_books=station.reference_books,
        mirror=station.mirror,
        **values,
    )


def is_interactive() -> bool:
    """Whether it is reasonable to ask a question.

    Both ends matter: a piped stdin cannot answer, and output going nowhere
    visible means the question is never seen.
    """
    return sys.stdin.isatty() and sys.stdout.isatty()
