# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""RepeaterBook through its API, with the operator's own key.  D-081.

**Built against the documented format and the unofficial client's source;
not yet run against the live API**: the maintainer had no token on
2026-10-04. The engine does not speak to RepeaterBook itself. It runs
:mod:`hammunition.repeaterbook_runner` with the venv python of the
``repeaterbook-client`` unit (the unofficial ``repeaterbook`` 0.13.0 client,
MIT, App #114, which the maintainer will not re-register under his own name),
hands it the operator's token in the subprocess environment only, and parses
the rows it prints. What was read on 2026-10-04:

- RepeaterBook's wiki (https://www.repeaterbook.com/wiki/doku.php?id=api):
  ``api/export.php`` takes ``country`` and ``state_id``; since 2026-03-03 an
  approved application and a per-user token are required; the token goes in
  ``X-RB-App-Token``; the User-Agent must be the approved one (the client
  sends its own); limits are unpublished and a ``429`` means back off; the
  terms are personal or internal use with attribution, a link on a public
  application, and approval is "less likely" for a public directory or map,
  a mirror, an app that "caches and re-serves repeater data to multiple
  users", or one that uses RepeaterBook "as just one data source inside a
  broader mapping ... platform". So this layer is the operator's own, on
  their own machine: never mirrored, never listed for a Bunker, never shared.
  ``api/exportROW.php`` (``country``, ``region``) is documented and not
  carried: the verb is per state.
- The client's source (``repeaterbook/models.py``, ``na_states.py``,
  ``services.py``): the export is ``{"count": N, "results": [...]}``; its
  row keys are the ones read below (``RepeaterJSON``); a ``state_id`` is the
  US FIPS code, zero-padded (``"06"``, not ``"6"``), and ``CA##`` / ``MX##``
  for Canada and Mexico; an error body is ``{"status": "error",
  "error_code", "message"}``; a ``429`` carries ``Retry-After``; an answer
  is cut at about 3,500 rows.

Fields read: ``Callsign``, ``Frequency``, ``Input Freq``, ``PL``, ``TSQ``,
``Lat``, ``Long``, ``Nearest City``, ``Landmark``, ``Use``,
``Operational Status``, ``Notes``, ``Last Update`` and the ``Yes``/``No``
mode keys ``FM Analog``, ``DMR``, ``D-Star``, ``NXDN``, ``APCO P-25``,
``M17``, ``System Fusion``, ``Tetra``, and the digital details the
client's ``RepeaterJSON`` names: ``DMR Color Code``, ``DMR ID``, ``P-25 NAC``
(kept when non-empty; the API has no D-STAR module, YSF DG-ID or NXDN RAN
key). A key this needs that is absent is a
named error, never a silent empty layer.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from .repeater_sources import _parsed
from .repeaters import (
    _BAD_FREQUENCY,
    _NO_CALLSIGN,
    _NO_POSITION,
    REPEATERBOOK_API,
    ParsedInput,
    Repeater,
    RepeaterFetchError,
    RepeaterInputError,
    _clean,
    _hz,
    _position,
    _Skips,
    _tone,
)

__all__ = [
    "OFF_AIR",
    "RUNNER",
    "TOKEN_ENV",
    "UNIT",
    "RunnerError",
    "StateRead",
    "client_python",
    "explain",
    "layer_name",
    "maybe_cut_short",
    "parse_export",
    "provenance",
    "resolve_area",
    "resolve_state",
    "run_runner",
    "terms",
]

#: The secret's name: the unofficial client's own variable, so an operator who
#: already uses that client has it set (D-081). It holds a token generated for
#: App #114 ("RepeaterBook Python Client") on the operator's own account.
TOKEN_ENV = "REPEATERBOOK"
#: Our own pause between two states of one run: the documented limits are
#: unpublished, so this is a courtesy, not RepeaterBook's number.
INTERVAL_SECONDS = 5.0
#: RepeaterBook answers at most about 3,500 rows per request (the unofficial
#: client warns near it): a list this long may have been cut short.
TRUNCATION_NOTE_AT = 3500
OFF_AIR = "off the air (Operational Status)"

#: US state, district and territory names with their FIPS codes (the
#: ``state_id`` assumed above), and the two-letter postal codes.
_US: dict[str, tuple[str, str]] = {
    "alabama": ("AL", "01"),
    "alaska": ("AK", "02"),
    "arizona": ("AZ", "04"),
    "arkansas": ("AR", "05"),
    "california": ("CA", "06"),
    "colorado": ("CO", "08"),
    "connecticut": ("CT", "09"),
    "delaware": ("DE", "10"),
    "district of columbia": ("DC", "11"),
    "florida": ("FL", "12"),
    "georgia": ("GA", "13"),
    "hawaii": ("HI", "15"),
    "idaho": ("ID", "16"),
    "illinois": ("IL", "17"),
    "indiana": ("IN", "18"),
    "iowa": ("IA", "19"),
    "kansas": ("KS", "20"),
    "kentucky": ("KY", "21"),
    "louisiana": ("LA", "22"),
    "maine": ("ME", "23"),
    "maryland": ("MD", "24"),
    "massachusetts": ("MA", "25"),
    "michigan": ("MI", "26"),
    "minnesota": ("MN", "27"),
    "mississippi": ("MS", "28"),
    "missouri": ("MO", "29"),
    "montana": ("MT", "30"),
    "nebraska": ("NE", "31"),
    "nevada": ("NV", "32"),
    "new hampshire": ("NH", "33"),
    "new jersey": ("NJ", "34"),
    "new mexico": ("NM", "35"),
    "new york": ("NY", "36"),
    "north carolina": ("NC", "37"),
    "north dakota": ("ND", "38"),
    "ohio": ("OH", "39"),
    "oklahoma": ("OK", "40"),
    "oregon": ("OR", "41"),
    "pennsylvania": ("PA", "42"),
    "rhode island": ("RI", "44"),
    "south carolina": ("SC", "45"),
    "south dakota": ("SD", "46"),
    "tennessee": ("TN", "47"),
    "texas": ("TX", "48"),
    "utah": ("UT", "49"),
    "vermont": ("VT", "50"),
    "virginia": ("VA", "51"),
    "washington": ("WA", "53"),
    "west virginia": ("WV", "54"),
    "wisconsin": ("WI", "55"),
    "wyoming": ("WY", "56"),
    "puerto rico": ("PR", "72"),
}


#: Postal code to name, for the area switch (D-082): ``OH`` is Geofabrik's
#: ``north-america/us/ohio``, so activating one covers the other.
def _state_names() -> dict[str, str]:
    return {code: name for name, (code, _fips) in _US.items()}


US_STATE_NAMES: dict[str, str] = _state_names()


def resolve_state(country: str, state: str) -> str:
    """The ``state_id`` for a state name or two-letter code, or
    :class:`RepeaterInputError`. A bare number is passed through as given
    (for a country whose ids are not the US table's)."""
    text = _clean(state)
    if re.fullmatch(r"\d{1,2}", text):
        return text.zfill(2)
    if re.fullmatch(r"(?:CA|MX)\d{2}", text.upper()):
        return text.upper()
    if _clean(country).lower() in ("united states", "usa", "us"):
        for name, (code, fips) in _US.items():
            if text.lower() in (name, code.lower()):
                return fips
        raise RepeaterInputError(
            f"--state {state!r} is not a US state name or two-letter code (for example "
            f"Delaware or DE)"
        )
    raise RepeaterInputError(
        f"--state {state!r}: Hammunition knows state names only for the United States; for "
        f"{country} give RepeaterBook's own state_id (CA01, MX14, or the number)"
    )


def layer_name(day: date, area: str) -> str:
    """One area's layer: ``Repeaters (RepeaterBook OH, personal use, DATE, unverified)``."""
    return f"Repeaters (RepeaterBook {area}, personal use, {day.isoformat()}, unverified)"


def resolve_area(country: str, state: str) -> tuple[str, str]:
    """``(state_id, area)`` for a state: the id the export takes and the
    ``<AREA>`` of its layer (#325): the postal code for a US state, else the
    ``state_id`` itself (``CA01``, ``07``)."""
    state_id = resolve_state(country, state)
    if _clean(country).lower() in ("united states", "usa", "us"):
        for code, fips in _US.values():
            if fips == state_id:
                return state_id, code
    return state_id, state_id


def terms() -> str:
    """Printed before the fetch and recorded in the layer (so every rendering
    of it, the GPX metadata and the POI collection's comment, carries it)."""
    return (
        "Data courtesy of RepeaterBook.com (https://www.repeaterbook.com). This is "
        "RepeaterBook's API, reached through the unofficial third-party repeaterbook client "
        "(App #114) with a token you generated for yourself, for your own personal use on this "
        "machine, under its terms (repeaterbook.com/wiki/doku.php?id=api): the data may "
        "not be shared, re-served, mirrored, put in a public directory or map, or bundled. "
        "Hammunition converts it here and never uploads it; it is never mirrored and never "
        "offered to a Bunker; the overlay files are readable only by you. Positions are "
        "approximate: do not use them to visit a repeater site."
    )


def provenance(when: str, sha256: str) -> str:
    """What one state's read adds to the layer's description."""
    return (
        f"{when}, sha256 {sha256}. Built against the documented format and not verified "
        f"against the live API; marked unverified."
    )


# --- parsing ---------------------------------------------------------------------------

#: Keys a row must carry (even if empty). Absent keys mean the format is not
#: what this was written against.
_REQUIRED = ("Callsign", "Frequency", "Lat", "Long")
_MODE_KEYS = (
    ("FM Analog", "FM"),
    ("DMR", "DMR"),
    ("D-Star", "D-STAR"),
    ("NXDN", "NXDN"),
    ("APCO P-25", "P25"),
    ("P-25", "P25"),
    ("M17", "M17"),
    ("System Fusion", "Fusion"),
    ("Tetra", "TETRA"),
)


def parse_export(raw: bytes, url: str) -> ParsedInput:
    """One state's export, from memory. Rows with no usable position, no
    callsign or no frequency, and rows whose ``Operational Status`` says
    off-air, are skipped and counted, never silently dropped."""
    try:
        data: Any = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise RepeaterInputError(f"{url}: not JSON (RepeaterBook's export is)") from None
    if isinstance(data, dict) and (data.get("status") == "error" or data.get("ok") is False):
        why = str(data.get("error_code") or data.get("error") or "")[:60]
        message = str(data.get("message") or "")[:120]
        raise RepeaterInputError(
            f"{url}: RepeaterBook answered with an error"
            f"{f' {why}' if why else ''}{f': {message}' if message else ''}"
        )
    records = data.get("results") if isinstance(data, dict) else data
    if not isinstance(records, list):
        why = ""
        if isinstance(data, dict):
            hint = str(data.get("error") or data.get("message") or "")[:120]
            why = f" ({hint})" if hint else f" (keys: {', '.join(sorted(map(str, data))[:8])})"
        raise RepeaterInputError(
            f"{url}: RepeaterBook's answer has no list of repeaters under 'results'{why}"
        )
    for number, item in enumerate(records, start=1):
        if not isinstance(item, dict):
            raise RepeaterInputError(f"{url}: result {number} is not an object")
        missing = [k for k in _REQUIRED if k not in item]
        if missing:
            raise RepeaterInputError(
                f"{url}: result {number} has no {', '.join(missing)} field: RepeaterBook's "
                f"export format is not the one this was built against (D-081); nothing "
                f"was read"
            )
    rows: list[Repeater] = []
    skips = _Skips()
    for number, item in enumerate(records, start=1):
        status = _clean(item.get("Operational Status"))
        if "off" in status.lower():
            skips.add(OFF_AIR, number)
            continue
        where = _position(item.get("Lat"), item.get("Long"))
        if where is None:
            skips.add(_NO_POSITION, number)
            continue
        call = _clean(item.get("Callsign")).upper()
        if not call:
            skips.add(_NO_CALLSIGN, number)
            continue
        hz = _hz(item.get("Frequency"))
        if hz is None:
            skips.add(_BAD_FREQUENCY, number)
            continue
        entry = _hz(item.get("Input Freq"))
        pl, tsq = _clean(item.get("PL")), _clean(item.get("TSQ"))
        tone = _tone(pl)
        if tsq and tsq != pl and tsq.lower() not in ("", "0", "0.0", "none", "csq"):
            tone = f"{tone} (TSQ {tsq})" if tone else f"TSQ {tsq}"
        modes = [label for key, label in _MODE_KEYS if _clean(item.get(key)).lower() == "yes"]
        place = ", ".join(
            x for x in (_clean(item.get("Nearest City")), _clean(item.get("Landmark"))) if x
        )
        digital = {
            key: value
            for key, value in (
                ("dmr_color_code", _clean(item.get("DMR Color Code"))),
                ("dmr_id", _clean(item.get("DMR ID"))),
                ("p25_nac", _clean(item.get("P-25 NAC"))),
            )
            if value
        }
        rows.append(
            Repeater(
                callsign=call,
                output_hz=hz,
                lat=where[0],
                lon=where[1],
                source=REPEATERBOOK_API,
                offset_hz=None if entry is None else entry - hz,
                tone=tone,
                mode=", ".join(dict.fromkeys(modes)),
                digital=digital,
                place=place,
                notes=_clean(item.get("Notes")),
                use=_clean(item.get("Use")),
                status=status,
                updated=_clean(item.get("Last Update")),
            )
        )
    return _parsed(Path(url), REPEATERBOOK_API, len(records), rows, skips, raw, 0.0)


# --- fetching --------------------------------------------------------------------------

#: The unit that carries the unofficial client, and the runner it executes.
UNIT = "repeaterbook-client"
RUNNER = Path(__file__).with_name("repeaterbook_runner.py")
#: The client's own name for the token variable: the subprocess is handed it
#: and nothing else of the operator's environment.
CLIENT_TOKEN_VARIABLE = "REPEATERBOOK"
RUN_TIMEOUT_SECONDS = 600


class RunnerError(Exception):
    """The runner reported a failure. *kind* is its own word: ``unauthorized``,
    ``forbidden`` and ``rate_limited`` stop the whole run and are never
    retried."""

    def __init__(
        self,
        message: str,
        *,
        kind: str,
        status: int | None = None,
        retry_after: float | None = None,
    ) -> None:
        super().__init__(message)
        self.kind = kind
        self.status = status
        self.retry_after = retry_after


def client_python(owner: str | None = None) -> Path:
    """The ``repeaterbook-client`` unit's venv python."""
    from .paths import venv_root

    return venv_root(owner) / UNIT / "bin" / "python"


@dataclass(frozen=True)
class StateRead:
    parsed: ParsedInput
    sha256: str
    when: datetime
    where: str


def run_runner(
    python: Path,
    country: str,
    state_id: str,
    token: str,
    county: str | None = None,
    *,
    runner: Path | None = None,
    run: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> StateRead:
    """One state through the client, in its own venv. The token is in the
    subprocess's environment only: never argv, never printed. Never retried."""
    argv = [str(python), "-I", str(runner or RUNNER), "--country", country, "--state-id", state_id]
    if county:
        argv += ["--county", county]
    env = {CLIENT_TOKEN_VARIABLE: token}
    for keep in ("PATH", "LANG", "LC_ALL", "TMPDIR", "SSL_CERT_FILE", "SSL_CERT_DIR"):
        if keep in os.environ:
            env[keep] = os.environ[keep]
    try:
        done = run(
            argv, capture_output=True, text=True, check=False, env=env, timeout=RUN_TIMEOUT_SECONDS
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise RepeaterFetchError(
            f"could not run the repeaterbook client: {exc.__class__.__name__}"
        ) from None
    out = done.stdout or ""
    try:
        document: Any = json.loads(out.strip().splitlines()[-1]) if out.strip() else None
    except (json.JSONDecodeError, IndexError):
        document = None
    if not isinstance(document, dict):
        first = next(
            (x.strip() for x in (done.stderr or "").splitlines() if x.strip()), "no message"
        )
        raise RepeaterFetchError(
            f"the repeaterbook client printed no document (exit {done.returncode}): "
            f"{first.replace(token, '<redacted>')[:200]}"
        )
    if document.get("ok") is not True:
        raise RunnerError(
            str(document.get("message") or "no message").replace(token, "<redacted>"),
            kind=str(document.get("kind") or "unknown"),
            status=document.get("status") if isinstance(document.get("status"), int) else None,
            retry_after=document.get("retry_after")
            if isinstance(document.get("retry_after"), int | float)
            else None,
        )
    raw = out.encode("utf-8")
    where = f"{UNIT}: country={country} state_id={state_id}" + (
        f" county={county}" if county else ""
    )
    parsed = parse_export(raw, where)
    return StateRead(
        parsed, hashlib.sha256(raw).hexdigest(), datetime.now(UTC).replace(microsecond=0), where
    )


def maybe_cut_short(read: StateRead) -> bool:
    """Whether an answer is long enough that RepeaterBook may have cut it."""
    return read.parsed.read >= TRUNCATION_NOTE_AT


def explain(exc: RunnerError) -> str:
    """What a failure means, for the operator."""
    if exc.kind == "rate_limited":
        wait = (
            f" It asked for {exc.retry_after:g} s before the next request."
            if exc.retry_after
            else ""
        )
        return (
            f"RepeaterBook says too many requests (429).{wait} Hammunition stops at once and "
            f"does not retry; wait before asking again"
        )
    if exc.kind in ("unauthorized", "forbidden"):
        return (
            f"RepeaterBook refused the token ({exc.status or 'no status'}): {exc}. It must be a "
            f"token generated for App #114 (RepeaterBook Python Client) on your own account at "
            f"https://www.repeaterbook.com/user/api_apps.php. Hammunition does not retry"
        )
    return f"{exc} ({exc.kind})"


def pause(seconds: float = INTERVAL_SECONDS, sleep: Callable[[float], None] = time.sleep) -> None:
    sleep(seconds)
