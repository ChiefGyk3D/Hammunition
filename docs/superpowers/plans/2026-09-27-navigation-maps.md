# Navigation piece 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `hammunition install navigation` downloads the operator's chosen OpenStreetMap regions from Geofabrik, verified and disclosed, converts them for Navit, and leaves a Navit launcher that follows the GPS with voice, for daily use and for when the phone network is down.

**Architecture:** Two new install methods beside D-049's `data`: `osm-regions` (fetches the station's Geofabrik regions per the freshness mode, pinned by sha256 where the catalog carries a pin, else by Geofabrik's MD5, disclosed per region) and `derived` (runs a converter named by enum over another unit's data). Both record `install-data` actions so the existing uninstall attribution removes their files. Pure, injectable modules (`geofabrik.py`, `navit_config.py`) hold the logic; backends turn it into plan steps.

**Tech Stack:** Python 3.11+ (`mypy --strict`, pytest, ruff), Pydantic schema, Geofabrik's download server, Navit 0.5.6 and `maptool` from Parrot's archive.

**Spec:** `docs/superpowers/specs/2026-09-27-navigation-maps-design.md`

## Global Constraints

- Freshness modes: `yearly` (default) → `<region>-YY0101.osm.pbf` of the current year; `monthly` → `<region>-YYMM01.osm.pbf` of the current month; `latest` → the dated file `<region>-latest.osm.pbf` redirects to.
- Base URL: `https://download.geofabrik.de/<region>-<YYMMDD>.osm.pbf`; its MD5 at the same URL plus `.md5` (format `<32 hex>  <filename>`).
- Region path pattern: `^[a-z0-9-]+(/[a-z0-9-]+)*$`. Slug: the path with `/` replaced by `-`.
- Verification wording printed per region, exactly: `sha256, pinned by Hammunition` or `MD5 from Geofabrik only; not pinned`.
- Pinned regions: the 50 US states and DC, under `north-america/us/<state>`.
- Licence: `ODbL-1.0`, `https://www.openstreetmap.org/copyright`.
- Install locations: region files `<prefix>/share/hammunition/data/osm-regions/<slug>.osm.pbf`; Navit maps `<prefix>/share/hammunition/data/osm-navit/<slug>.bin`; Navit config `<prefix>/share/hammunition/data/osm-navit/navit.xml`.
- Converter enum value: `navit-maptool` → `maptool --protobuf -i <input> <output>`.
- Unset `map_regions` defers `osm-regions` and `osm-navit` by name; `navit` still installs (D-035).
- The catalog never carries a command line: converters are an enum the engine implements.
- No doc claims cross-region routing, conversion size or conversion time until Task 10 measured it.
- The operator's regions are station data: never in a commit, doc, PR, test or log excerpt. Tests use `north-america/us/vermont` and `north-america/us/new-hampshire`.
- Commits end with `Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>`.
- Gates: `.venv/bin/python -m pytest -q`, `.venv/bin/mypy --strict`, `.venv/bin/ruff check src tests`, `.venv/bin/ruff format --check src tests`, `.venv/bin/python scripts/check_doc_links.py`.

## Review Focus

1. **A region larger than the fetcher's 512 MB cap.** California is 1.33 GB. Expected: the regional fetch raises the cap to the declared size plus a margin, never removes it. Test in Task 3.
2. **The year or month just rolled over** and Geofabrik has not yet published `YY0101`/`YYMM01`. Expected: fall back to the previous snapshot, disclosed, never to `latest` silently. Test in Task 2.
3. **Clock wrong on a field machine** (no NTP offline). Expected: the chosen snapshot date is printed, and a 404 names the file, so a wrong clock shows up as a wrong date in the plan. Test in Task 2 (404 message names the file).
4. **A region dropped from station config.** Expected: its `.pbf` and `.bin` are removed on the next install and the plan says so. Test in Task 6.
5. **`/etc/navit/navit.xml` missing or a different shape** (package not installed, or a future Navit). Expected: the Navit config step refuses with the path, not a traceback; the transformation tests pin the anchors it relies on. Test in Task 5.

---

### Task 1: Station config carries `map_regions` and `map_freshness`

**Files:**
- Modify: `src/hammunition/station.py`, `src/hammunition/cli/main.py` (`cmd_station_set`, `cmd_station_show`, the `station set` parser)
- Test: `tests/test_station.py`, `tests/test_cli.py`

**Interfaces:**
- Produces: `Station.map_regions: tuple[str, ...] = ()`, `Station.map_freshness: str | None = None` (validated; `None` means `yearly`), `Station.freshness -> str` property (`self.map_freshness or "yearly"`), `FRESHNESS = ("yearly", "monthly", "latest")`, `REGION = re.compile(r"[a-z0-9-]+(/[a-z0-9-]+)*")`. `load_station`/`save_station` round-trip both. `hammunition station set --map-regions A,B --map-freshness monthly`.

- [ ] **Step 1: Write the failing tests**

In `tests/test_station.py`:

```python
def test_map_regions_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "station.yaml"
    save_station(
        Station(map_regions=("north-america/us/vermont", "north-america/us/new-hampshire"),
                map_freshness="monthly"),
        path,
    )
    loaded = load_station(path)
    assert loaded.map_regions == ("north-america/us/vermont", "north-america/us/new-hampshire")
    assert loaded.freshness == "monthly"


def test_freshness_defaults_to_yearly() -> None:
    assert Station().freshness == "yearly"


@pytest.mark.parametrize("bad", ["North-America/us", "north-america/../etc", "us vermont", "a//b", ""])
def test_a_region_that_is_not_a_geofabrik_path_is_refused(bad: str) -> None:
    with pytest.raises(StationError):
        Station(map_regions=(bad,))


def test_an_unknown_freshness_is_refused() -> None:
    with pytest.raises(StationError):
        Station(map_freshness="daily")


def test_template_variables_are_unchanged_by_map_fields() -> None:
    s = Station(callsign="N0CALL", map_regions=("north-america/us/vermont",))
    assert s.get("callsign") == "N0CALL"
    assert "map_regions" not in s.as_dict() or isinstance(s.as_dict()["map_regions"], list)
```

In `tests/test_cli.py`, beside the existing `station set` tests (reuse their `tmp_path`/`HOME` or `config_path` stubbing):

```python
def test_station_set_map_regions_and_freshness(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import importlib

    cli = importlib.import_module("hammunition.cli.main")
    target = tmp_path / "station.yaml"
    monkeypatch.setattr("hammunition.station.config_path", lambda owner=None: target)
    assert cli.main([
        "station", "set",
        "--map-regions", "north-america/us/vermont,north-america/us/new-hampshire",
        "--map-freshness", "latest",
    ]) == 0
    from hammunition.station import load_station

    s = load_station(target)
    assert s.map_regions == ("north-america/us/vermont", "north-america/us/new-hampshire")
    assert s.freshness == "latest"
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv/bin/python -m pytest -q tests/test_station.py tests/test_cli.py -k "map_ or freshness or region"`
Expected: TypeError (unexpected keyword `map_regions`).

- [ ] **Step 3: Implement**

In `station.py`: add `import re` if absent; module constants `FRESHNESS = ("yearly", "monthly", "latest")` and `REGION = re.compile(r"[a-z0-9-]+(/[a-z0-9-]+)*")`. Add to the dataclass, after the existing fields:

```python
    map_regions: tuple[str, ...] = ()
    """Geofabrik region paths to carry offline maps for, e.g.
    ``north-america/us/vermont``. Several at once; none means the map data
    units are deferred (D-035)."""
    map_freshness: str | None = None
    """``yearly`` (the default when unset), ``monthly`` or ``latest``."""
```

In `__post_init__`, after the existing checks:

```python
        regions = tuple(r.strip() for r in self.map_regions)
        for region in regions:
            if not REGION.fullmatch(region):
                raise StationError(
                    f"map region {region!r} is not a Geofabrik region path "
                    f"(lowercase words joined by '/', e.g. north-america/us/vermont). "
                    f"`hammunition maps regions` lists them."
                )
        object.__setattr__(self, "map_regions", regions)
        if self.map_freshness is not None and self.map_freshness not in FRESHNESS:
            raise StationError(
                f"map freshness {self.map_freshness!r} is not one of {', '.join(FRESHNESS)}"
            )

    @property
    def freshness(self) -> str:
        return self.map_freshness or "yearly"
```

(`__post_init__` already exists; add the block at its end and the property after it.) `as_dict()`: include `map_regions` as a list and `map_freshness` only when set, and keep `get()` returning only template string values (it reads the string fields by name, so it is unaffected; leave `STATION_VARIABLES` unchanged — map settings are not template variables). Change `as_dict`'s return annotation to `dict[str, str | list[str]]` and check its other callers with `grep -n "as_dict()" -r src` (`save_station` dumps it to YAML; any caller that assumes `str` values must skip list values). `load_station`: read `map_regions` as a list of strings (or absent → `()`), and `map_freshness`.

`src/hammunition/cli/main.py`: add to the `station set` parser

```python
    p_station_set.add_argument(
        "--map-regions", default=None,
        help="comma-separated Geofabrik regions to carry offline maps for",
    )
    p_station_set.add_argument("--map-freshness", default=None, choices=("yearly", "monthly", "latest"))
```

In `cmd_station_set`, merge `map_regions=tuple(r for r in args.map_regions.split(",") if r)` when given and `map_freshness` when given, and update the "nothing to set" message to list the two new flags. `cmd_station_show` prints `map regions: <n> set` and the freshness — **the count, not the names**, because `station show` output is the kind of thing that gets pasted into issues (the regions reveal where the operator lives; CLAUDE.md treats that like the grid square).

- [ ] **Step 4: Run, gates, commit**

Run: `.venv/bin/python -m pytest -q && .venv/bin/mypy --strict && .venv/bin/ruff check src tests && .venv/bin/ruff format --check src tests`
Expected: all pass.

```bash
git add src/hammunition/station.py src/hammunition/cli/main.py tests/test_station.py tests/test_cli.py
git commit -m "Station: map regions and map freshness, validated, shown as a count

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: `geofabrik.py`: which file, from where, verified how

**Files:**
- Create: `src/hammunition/geofabrik.py`
- Test: `tests/test_geofabrik.py`

**Interfaces:**
- Consumes: `Station.freshness`, `Station.map_regions` (Task 1).
- Produces:
  - `BASE = "https://download.geofabrik.de"`
  - `@dataclass(frozen=True) class Pin: region: str; snapshot: str; size: int; sha256: str` (`snapshot` is `YYMMDD`)
  - `@dataclass(frozen=True) class RegionFile: region: str; snapshot: str; url: str; size: int; sha256: str | None; md5: str | None` with `@property verified_by -> str` returning the exact Global Constraints wording and `@property slug -> str`
  - `class Probe(Protocol)`: `def head(self, url: str) -> tuple[int, int, str | None]` (status, content-length, redirect location) and `def text(self, url: str) -> str` (raises `GeofabrikError` on a non-200)
  - `def snapshot_for(freshness: str, today: date) -> str` (yearly/monthly only)
  - `def resolve(region: str, freshness: str, *, today: date, pins: Mapping[tuple[str, str], Pin], probe: Probe) -> RegionFile`
  - `def load_pins(path: Path) -> dict[tuple[str, str], Pin]`
  - `class GeofabrikError(Exception)`

- [ ] **Step 1: Write the failing tests**

```python
"""Which Geofabrik file a region and freshness mode mean, and how it is verified."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from hammunition.geofabrik import (
    GeofabrikError,
    Pin,
    RegionFile,
    load_pins,
    resolve,
    snapshot_for,
)

VT = "north-america/us/vermont"
MD5 = "f96442116ca488f5e2f8647166d20bb0"
SHA = "a" * 64


class FakeProbe:
    def __init__(self, heads: dict[str, tuple[int, int, str | None]], texts: dict[str, str]):
        self.heads, self.texts, self.seen = heads, texts, []

    def head(self, url: str) -> tuple[int, int, str | None]:
        self.seen.append(url)
        return self.heads.get(url, (404, 0, None))

    def text(self, url: str) -> str:
        if url not in self.texts:
            raise GeofabrikError(f"{url}: 404")
        return self.texts[url]


def _url(snapshot: str) -> str:
    return f"https://download.geofabrik.de/{VT}-{snapshot}.osm.pbf"


def test_snapshot_names() -> None:
    assert snapshot_for("yearly", date(2026, 9, 27)) == "260101"
    assert snapshot_for("monthly", date(2026, 9, 27)) == "260901"


def test_yearly_pinned_region_uses_the_pin_and_asks_nothing() -> None:
    pins = {(VT, "260101"): Pin(VT, "260101", 45_000_000, SHA)}
    probe = FakeProbe({}, {})
    got = resolve(VT, "yearly", today=date(2026, 9, 27), pins=pins, probe=probe)
    assert got == RegionFile(VT, "260101", _url("260101"), 45_000_000, SHA, None)
    assert got.verified_by == "sha256, pinned by Hammunition"
    assert probe.seen == []


def test_unpinned_region_uses_geofabriks_md5_and_says_so() -> None:
    probe = FakeProbe(
        {_url("260101"): (200, 44_000_000, None)},
        {_url("260101") + ".md5": f"{MD5}  vermont-260101.osm.pbf\n"},
    )
    got = resolve(VT, "yearly", today=date(2026, 9, 27), pins={}, probe=probe)
    assert got.sha256 is None and got.md5 == MD5 and got.size == 44_000_000
    assert got.verified_by == "MD5 from Geofabrik only; not pinned"


def test_latest_resolves_the_redirect_to_a_dated_file() -> None:
    latest = f"https://download.geofabrik.de/{VT}-latest.osm.pbf"
    probe = FakeProbe(
        {latest: (302, 0, _url("260926")), _url("260926"): (200, 45_951_595, None)},
        {_url("260926") + ".md5": f"{MD5}  vermont-260926.osm.pbf\n"},
    )
    got = resolve(VT, "latest", today=date(2026, 9, 27), pins={}, probe=probe)
    assert got.snapshot == "260926" and got.url == _url("260926") and got.md5 == MD5


def test_a_snapshot_not_yet_published_falls_back_to_the_previous_one() -> None:
    probe = FakeProbe(
        {_url("261001"): (404, 0, None), _url("260901"): (200, 44_000_000, None)},
        {_url("260901") + ".md5": f"{MD5}  vermont-260901.osm.pbf\n"},
    )
    got = resolve(VT, "monthly", today=date(2026, 10, 1), pins={}, probe=probe)
    assert got.snapshot == "260901"


def test_an_unknown_region_is_refused_naming_the_file() -> None:
    probe = FakeProbe({}, {})
    with pytest.raises(GeofabrikError, match="north-america/us/atlantis-260101.osm.pbf"):
        resolve("north-america/us/atlantis", "yearly", today=date(2026, 9, 27), pins={}, probe=probe)


def test_an_md5_file_that_is_not_an_md5_is_refused() -> None:
    probe = FakeProbe(
        {_url("260101"): (200, 1, None)},
        {_url("260101") + ".md5": "<html>not found</html>"},
    )
    with pytest.raises(GeofabrikError, match="md5"):
        resolve(VT, "yearly", today=date(2026, 9, 27), pins={}, probe=probe)


def test_load_pins(tmp_path: Path) -> None:
    f = tmp_path / "pins.yaml"
    f.write_text(
        "pins:\n"
        f"  - region: {VT}\n    snapshot: '260101'\n    size: 45000000\n    sha256: {SHA}\n"
    )
    assert load_pins(f) == {(VT, "260101"): Pin(VT, "260101", 45_000_000, SHA)}


def test_slug() -> None:
    assert RegionFile(VT, "260101", _url("260101"), 1, SHA, None).slug == "north-america-us-vermont"
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv/bin/python -m pytest -q tests/test_geofabrik.py`
Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement `src/hammunition/geofabrik.py`**

```python
# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""Which Geofabrik file a region and a freshness mode mean, and how it is
verified.  D-057.

Measured 2026-09-27: Geofabrik keeps a dated extract every 1 January, the
1st of the last three months, and the last seven days; ``-latest`` is a 302
to today's dated file; every file has a ``.md5`` beside it. A pinned region
is verified by the sha256 the catalog carries; anything else by Geofabrik's
MD5, and the plan says which, per region, every time.

Pure apart from the injected :class:`Probe`, so every branch is testable
without the network.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Protocol

import yaml

BASE = "https://download.geofabrik.de"
PINNED = "sha256, pinned by Hammunition"
UNPINNED = "MD5 from Geofabrik only; not pinned"
_MD5 = re.compile(r"([0-9a-f]{32})\s+\S+\s*")


class GeofabrikError(Exception):
    """A region could not be resolved to a verifiable file."""


@dataclass(frozen=True)
class Pin:
    region: str
    snapshot: str
    size: int
    sha256: str


@dataclass(frozen=True)
class RegionFile:
    region: str
    snapshot: str
    url: str
    size: int
    sha256: str | None
    md5: str | None

    @property
    def verified_by(self) -> str:
        return PINNED if self.sha256 else UNPINNED

    @property
    def slug(self) -> str:
        return self.region.replace("/", "-")


class Probe(Protocol):
    def head(self, url: str) -> tuple[int, int, str | None]: ...
    def text(self, url: str) -> str: ...


def snapshot_for(freshness: str, today: date) -> str:
    if freshness == "yearly":
        return f"{today:%y}0101"
    if freshness == "monthly":
        return f"{today:%y%m}01"
    raise GeofabrikError(f"{freshness!r} has no fixed snapshot")


def _previous(freshness: str, snapshot: str) -> str:
    yy, mm = int(snapshot[:2]), int(snapshot[2:4])
    if freshness == "yearly":
        return f"{yy - 1:02d}0101"
    return f"{yy - 1:02d}1201" if mm == 1 else f"{yy:02d}{mm - 1:02d}01"


def _url(region: str, snapshot: str) -> str:
    return f"{BASE}/{region}-{snapshot}.osm.pbf"


def _md5(probe: Probe, url: str) -> str:
    body = probe.text(url + ".md5").strip()
    match = _MD5.fullmatch(body)
    if match is None:
        raise GeofabrikError(f"{url}.md5 is not an md5 line: {body[:60]!r}")
    return match.group(1)


def resolve(
    region: str,
    freshness: str,
    *,
    today: date,
    pins: Mapping[tuple[str, str], Pin],
    probe: Probe,
) -> RegionFile:
    if freshness == "latest":
        status, _, location = probe.head(f"{BASE}/{region}-latest.osm.pbf")
        found = re.search(r"-(\d{6})\.osm\.pbf$", location or "")
        if status not in (301, 302, 303, 307, 308) or found is None:
            raise GeofabrikError(
                f"{region}-latest.osm.pbf did not redirect to a dated file (HTTP {status}); "
                f"is {region!r} a Geofabrik region? `hammunition maps regions` lists them."
            )
        candidates = [found.group(1)]
    else:
        first = snapshot_for(freshness, today)
        candidates = [first, _previous(freshness, first)]

    for snapshot in candidates:
        pin = pins.get((region, snapshot))
        if pin is not None:
            return RegionFile(region, snapshot, _url(region, snapshot), pin.size, pin.sha256, None)
        url = _url(region, snapshot)
        status, size, _ = probe.head(url)
        if status == 200:
            return RegionFile(region, snapshot, url, size, None, _md5(probe, url))
    raise GeofabrikError(
        f"no {freshness} extract for {region!r}: tried "
        + ", ".join(f"{region}-{s}.osm.pbf" for s in candidates)
        + ". Check the region with `hammunition maps regions`, and the machine's clock."
    )


def load_pins(path: Path) -> dict[tuple[str, str], Pin]:
    data = yaml.safe_load(path.read_text()) or {}
    pins: dict[tuple[str, str], Pin] = {}
    for row in data.get("pins", []):
        pin = Pin(str(row["region"]), str(row["snapshot"]), int(row["size"]), str(row["sha256"]))
        pins[(pin.region, pin.snapshot)] = pin
    return pins
```

A pinned region whose current snapshot has no pin yet (a new year before the maintainer regenerated) falls through to the MD5 probe for that snapshot, then to the previous snapshot's pin if the current file is not published. That order is deliberate: the freshest verifiable file wins, and the plan says how it was verified.

- [ ] **Step 4: Run, gates, commit**

Run: `.venv/bin/python -m pytest -q tests/test_geofabrik.py && .venv/bin/mypy --strict`

```bash
git add src/hammunition/geofabrik.py tests/test_geofabrik.py
git commit -m "Geofabrik: resolve a region and freshness mode to a dated, verifiable file

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: The fetcher verifies an MD5-only file, and takes a size-derived cap

**Files:**
- Modify: `src/hammunition/fetch.py`
- Test: `tests/test_fetch.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `Fetcher.fetch_md5(url: str, md5: str, *, expected_size: int) -> FetchResult` (the `FetchResult.sha256` field carries the computed sha256), and `Fetcher.fetch(artifact, *, max_bytes: int | None = None)`.

- [ ] **Step 1: Write the failing tests**

Using the file's existing fake transport (read `tests/test_fetch.py` for its name; it serves bytes for a URL):

```python
import hashlib


def test_fetch_md5_accepts_a_matching_file(tmp_path: Path) -> None:
    body = b"osm" * 1000
    fetcher = Fetcher(tmp_path, transport=_Serve({"https://x/v.osm.pbf": body}))
    result = fetcher.fetch_md5(
        "https://x/v.osm.pbf", hashlib.md5(body).hexdigest(), expected_size=len(body)
    )
    assert result.path.read_bytes() == body
    assert result.sha256 == hashlib.sha256(body).hexdigest()


def test_fetch_md5_refuses_a_mismatch_and_keeps_nothing(tmp_path: Path) -> None:
    fetcher = Fetcher(tmp_path, transport=_Serve({"https://x/v.osm.pbf": b"evil"}))
    with pytest.raises(VerificationError, match="md5"):
        fetcher.fetch_md5("https://x/v.osm.pbf", "0" * 32, expected_size=4)
    assert list(tmp_path.iterdir()) == [] or all(".part." not in p.name for p in tmp_path.iterdir())


def test_fetch_md5_refuses_a_size_that_is_not_the_published_one(tmp_path: Path) -> None:
    body = b"x" * 10
    fetcher = Fetcher(tmp_path, transport=_Serve({"https://x/v.osm.pbf": body}))
    with pytest.raises(VerificationError, match="size"):
        fetcher.fetch_md5("https://x/v.osm.pbf", hashlib.md5(body).hexdigest(), expected_size=11)


def test_a_declared_size_above_the_default_cap_raises_the_cap_not_removes_it(tmp_path: Path) -> None:
    body = b"y" * 2048
    fetcher = Fetcher(tmp_path, transport=_Serve({"https://x/big": body}), max_bytes=1024)
    ok = fetcher.fetch_md5("https://x/big", hashlib.md5(body).hexdigest(), expected_size=len(body))
    assert ok.size == len(body)
    liar = Fetcher(tmp_path / "b", transport=_Serve({"https://x/big": body * 3}), max_bytes=1024)
    with pytest.raises(BackendError, match="byte limit"):
        liar.fetch_md5("https://x/big", hashlib.md5(body * 3).hexdigest(), expected_size=len(body))
```

(If the existing fake transport has another name or signature, adapt these four tests to it and ledger the rename.)

- [ ] **Step 2: Run to verify they fail**

Run: `.venv/bin/python -m pytest -q tests/test_fetch.py -k md5`
Expected: AttributeError (`fetch_md5`).

- [ ] **Step 3: Implement**

In `fetch.py`: add `import hashlib` if not present. Change `_download(self, url, destination)` to `_download(self, url, destination, *, max_bytes: int | None = None, md5: bool = False) -> tuple[str, int, str | None]` returning `(sha256, size, md5hex or None)`, using `limit = max_bytes or self.max_bytes` in the size check and updating an `hashlib.md5(usedforsecurity=False)` digest alongside when `md5` is true; update `fetch()`'s call (`actual, size, _ = self._download(...)`). Add:

```python
    def fetch_md5(self, url: str, md5: str, *, expected_size: int) -> FetchResult:
        """A file verified only by its publisher's MD5 (D-057), for map data the
        catalog carries no sha256 pin for. Weaker than :meth:`fetch`, and the plan
        says so beside every region it is used for. The size must match what the
        publisher's server reported, and the cap is that size plus 1 MiB, so a
        server that keeps sending is still stopped."""
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        final = self.cache_dir / f"md5-{md5}-{_safe_name(url)}"
        if final.exists() and final.stat().st_size == expected_size:
            digest = hashlib.md5(usedforsecurity=False)
            with final.open("rb") as handle:
                while chunk := handle.read(_CHUNK):
                    digest.update(chunk)
            if digest.hexdigest() == md5:
                return FetchResult(final, _digest_file(final), True, expected_size)
            final.unlink()
        temporary = final.with_name(final.name + f".part.{os.getpid()}")
        try:
            sha, size, got = self._download(
                url, temporary, max_bytes=expected_size + 1024 * 1024, md5=True
            )
        except BaseException:
            temporary.unlink(missing_ok=True)
            raise
        if size != expected_size:
            temporary.unlink(missing_ok=True)
            raise VerificationError(
                f"{url}: the server reported {expected_size} bytes and sent {size}; the size check failed"
            )
        if got != md5:
            temporary.unlink(missing_ok=True)
            raise VerificationError(
                f"{url} does not match the md5 its publisher lists.\n"
                f"  expected md5: {md5}\n  actually got: {got}\nThe download has been discarded."
            )
        os.replace(temporary, final)
        return FetchResult(final, sha, False, size)
```

(Use `FetchResult`'s actual field names/order; read its definition first. Keyword arguments are safer if it is a dataclass.) Add `max_bytes` to `fetch()` passed through to `_download`.

- [ ] **Step 4: Run, gates, commit**

Run: `.venv/bin/python -m pytest -q tests/test_fetch.py && .venv/bin/python -m pytest -q && .venv/bin/mypy --strict`

```bash
git add src/hammunition/fetch.py tests/test_fetch.py
git commit -m "Fetch: an MD5-verified path for unpinned map data, and a size-derived cap

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: Schema: `osm-regions` and `derived` install methods

**Files:**
- Modify: `src/hammunition/manifest/schema.py` (new classes; the `InstallMethod` union around line 781), `scripts/capability_matrix.py` and `scripts/gen_package_reference.py` (render the new methods)
- Test: `tests/test_schema.py` (the `DataInstall` cases live in `tests/test_data_backend.py`; copy their minimal-manifest shape)

**Interfaces:**
- Produces:
  - `class RegionalDataInstall(Strict)`: `method: Literal["osm-regions"]`, `provider: Literal["geofabrik"]`, `licence: str`, `licence_url: str` (https, as `DataInstall` checks)
  - `class DerivedDataInstall(Strict)`: `method: Literal["derived"]`, `converter: Literal["navit-maptool"]`, `source: str` (a package name), `licence: str`, `licence_url: str`; validator: `source` must also appear in the manifest's `depends` (checked in `PackageManifest`'s validator, where `depends` is visible)
  - Both in `InstallMethod`.

- [ ] **Step 1: Write the failing tests**

```python
def test_osm_regions_block_parses() -> None:
    m = PackageManifest.model_validate(_minimal("osm-regions", {
        "method": "osm-regions", "provider": "geofabrik",
        "licence": "ODbL-1.0", "licence_url": "https://www.openstreetmap.org/copyright",
    }))
    assert m.install[0].install.method == "osm-regions"


def test_derived_block_needs_its_source_in_depends() -> None:
    block = {"method": "derived", "converter": "navit-maptool", "source": "osm-regions",
             "licence": "ODbL-1.0", "licence_url": "https://www.openstreetmap.org/copyright"}
    with pytest.raises(ValidationError, match="depends"):
        PackageManifest.model_validate(_minimal("osm-navit", block))
    ok = _minimal("osm-navit", block)
    ok["depends"] = ["osm-regions", "maptool"]
    assert PackageManifest.model_validate(ok).install[0].install.method == "derived"


def test_a_converter_outside_the_enum_is_refused() -> None:
    block = {"method": "derived", "converter": "sh -c 'rm -rf /'", "source": "osm-regions",
             "licence": "ODbL-1.0", "licence_url": "https://www.openstreetmap.org/copyright"}
    bad = _minimal("osm-navit", block)
    bad["depends"] = ["osm-regions"]
    with pytest.raises(ValidationError):
        PackageManifest.model_validate(bad)
```

`_minimal(name, install_block)` builds the smallest valid manifest dict — copy the shape the existing `DataInstall` test in that file uses (name, version, summary, categories, documentation block, `install: [{"install": install_block}]`).

- [ ] **Step 2: Run to verify they fail**, then **Step 3: implement** the two classes beside `DataInstall`, add them to `InstallMethod`, add the `depends` check to `PackageManifest`'s model validator:

```python
        for entry in self.install:
            block = entry.install
            if isinstance(block, DerivedDataInstall) and block.source not in self.depends:
                raise ManifestError(
                    f"a derived block reads {block.source!r}, which must be in depends "
                    f"so it is installed first"
                )
```

In `capability_matrix.py` and `gen_package_reference.py`, render `osm-regions` as "OpenStreetMap regions from Geofabrik (chosen in station config)" and `derived` as "converted from <source> by <converter>" wherever `DataInstall` is rendered. Regenerate nothing yet (no manifest uses them until Task 8).

- [ ] **Step 4: Run, gates, commit**

```bash
git add src/hammunition/manifest/schema.py scripts tests
git commit -m "Schema: osm-regions and derived install methods; converters are an enum

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 5: `navit_config.py`: Navit's own config, rewritten for our maps and voice

**Files:**
- Create: `src/hammunition/navit_config.py`, `tests/fixtures/navit.xml` (a trimmed copy of the anchors from Debian's `/etc/navit/navit.xml`: the `<speech type="cmdline" …>` element and a `<mapset>` with the `$NAVIT_SHAREDIR/maps/*.xml` include, inside `<config><navit>…</navit></config>`; GPL-2+ like Navit, header comment says so)
- Test: `tests/test_navit_config.py`

**Interfaces:**
- Produces: `def rewrite(stock: str, maps: Sequence[Path]) -> str` raising `NavitConfigError` when an anchor is missing; `STOCK = Path("/etc/navit/navit.xml")`.

- [ ] **Step 1: Write the failing tests**

```python
from pathlib import Path

import pytest

from hammunition.navit_config import NavitConfigError, rewrite

FIXTURE = (Path(__file__).parent / "fixtures" / "navit.xml").read_text()
MAPS = [Path("/usr/local/share/hammunition/data/osm-navit/north-america-us-vermont.bin")]


def test_speech_goes_to_espeak_ng() -> None:
    out = rewrite(FIXTURE, MAPS)
    assert '<speech type="cmdline" data="espeak-ng' in out
    assert "Fix the speech tag" not in out


def test_one_mapset_is_ours_and_enabled_with_each_map() -> None:
    out = rewrite(FIXTURE, MAPS)
    assert f'<map type="binfile" enabled="yes" data="{MAPS[0]}"/>' in out
    assert out.count('<mapset enabled="yes">') == 1


def test_every_other_mapset_is_disabled() -> None:
    out = rewrite(FIXTURE, MAPS)
    assert "$NAVIT_SHAREDIR/maps/*.xml" not in out.split('<mapset enabled="yes">')[1]


def test_no_maps_is_refused() -> None:
    with pytest.raises(NavitConfigError):
        rewrite(FIXTURE, [])


def test_a_stock_file_without_the_anchors_is_refused_by_name() -> None:
    with pytest.raises(NavitConfigError, match="speech"):
        rewrite("<config><navit></navit></config>", MAPS)


def test_the_output_is_well_formed_xml() -> None:
    from xml.etree import ElementTree

    ElementTree.fromstring(rewrite(FIXTURE, MAPS).replace("xi:include", "include"))
```

- [ ] **Step 2: Run to verify they fail**, then **Step 3: implement** with string operations anchored on the two elements (not an XML round-trip, which would drop Navit's comments and XInclude namespace):

```python
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
_ENABLED_MAPSET = re.compile(r'<mapset enabled="yes">')


class NavitConfigError(Exception):
    pass


def rewrite(stock: str, maps: Sequence[Path]) -> str:
    if not maps:
        raise NavitConfigError("no converted maps to point Navit at")
    if not _SPEECH.search(stock):
        raise NavitConfigError(f"{STOCK} has no <speech type=\"cmdline\"> element to replace")
    if not _ENABLED_MAPSET.search(stock):
        raise NavitConfigError(f"{STOCK} has no enabled <mapset> to replace")
    out = _SPEECH.sub('<speech type="cmdline" data="espeak-ng \'%s\'" cps="15"/>', stock, count=1)
    out = _ENABLED_MAPSET.sub('<mapset enabled="no">', out)
    ours = "\n".join(
        f'\t\t\t<map type="binfile" enabled="yes" data={quoteattr(str(p))}/>' for p in maps
    )
    mapset = f'<mapset enabled="yes">\n{ours}\n\t\t</mapset>\n\t\t'
    index = out.index('<mapset enabled="no">')
    return out[:index] + mapset + out[index:]
```

Note the test string for the map line uses `data="…"` with double quotes; `quoteattr` produces double quotes for a path without `"`. Confirm against the real file once: `.venv/bin/python -c "from hammunition.navit_config import rewrite, STOCK; from pathlib import Path; print(rewrite(STOCK.read_text(), [Path('/x.bin')])[:0])"` must not raise on this machine.

- [ ] **Step 4: Run, gates, commit**

```bash
git add src/hammunition/navit_config.py tests/fixtures/navit.xml tests/test_navit_config.py
git commit -m "Navit config: the stock file with our maps and espeak-ng, anchors checked

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 6: Backends, planning and deferral

**Files:**
- Create: `src/hammunition/backends/regions.py` (`RegionsBackend`), `src/hammunition/backends/derived.py` (`DerivedBackend`)
- Modify: `src/hammunition/backends/__init__.py` (export), `src/hammunition/execute.py` (dispatch beside `DataInstall` at ~line 474; construct the backends where `DataBackend` is constructed), `src/hammunition/plan.py` (station deferral; region resolution at plan time and its disclosure), `src/hammunition/cli/main.py` (pass the station and a real `Probe` into planning/backends)
- Test: `tests/test_regions_backend.py`, `tests/test_plan.py` (deferral)

**Interfaces:**
- Consumes: Tasks 1–5.
- Produces:
  - `RegionsBackend(fetcher: Fetcher, prefix: Path, files: Sequence[RegionFile])` with `steps(manifest, block) -> list[Action | Command]`: per region a `fetch` Action (sha256 path via `fetcher.fetch` with a `RemoteArtifact`-shaped object and `max_bytes=size + 1 MiB`; MD5 path via `fetcher.fetch_md5`) whose description ends with `— <verified_by>`, then an `install-data` Action with `detail` = `<data>/osm-regions/<slug>.osm.pbf`; then for every `*.osm.pbf` already in that directory whose slug is not in `files`, an Action `kind="remove-data"`, description `Remove <slug>: no longer in your map regions`, which unlinks it. (`remove-data` is a new kind; add it to uninstall's attribution so a removed path is un-attributed, with a test.)
  - `DerivedBackend(prefix: Path, files: Sequence[RegionFile], stock: Path = navit_config.STOCK)` with `steps(...)`: per region an `install-data` Action running `maptool --protobuf -i <pbf> <bin>` via `subprocess.run` (argv fixed by the enum), skipped when `<bin>` exists and a sidecar `<slug>.bin.source` holds the same snapshot; then removals for dropped regions (as above, for `.bin` and `.bin.source`); then an `install-data` Action writing `<data>/osm-navit/navit.xml` from `navit_config.rewrite(stock.read_text(), bins)`.
  - `plan.resolve(...)`: when `osm-regions` or a `derived` unit sourcing it is in the plan and `station.map_regions` is empty, both get a `Deferral` with why `no map regions set` and fix `hammunition station set --map-regions <region>[,<region>…]` (the shape `_plan_config` uses).
  - The plan output prints, per region: `<region>  <snapshot>  <size>  <verified_by>`. Regions are printed by the CLI to the operator's own terminal; that is not publication.

- [ ] **Step 1: Write the failing tests**

```python
"""The regions and derived backends turn resolved region files into steps."""

from __future__ import annotations

from pathlib import Path

import pytest

from hammunition.backends.derived import DerivedBackend
from hammunition.backends.regions import RegionsBackend
from hammunition.geofabrik import RegionFile

VT = RegionFile("north-america/us/vermont", "260101",
                "https://download.geofabrik.de/north-america/us/vermont-260101.osm.pbf",
                10, "a" * 64, None)
NH = RegionFile("north-america/us/new-hampshire", "260101",
                "https://download.geofabrik.de/north-america/us/new-hampshire-260101.osm.pbf",
                10, None, "b" * 32)


def test_each_region_is_fetched_and_says_how_it_is_verified(tmp_path: Path, manifest_regions, block_regions) -> None:
    steps = RegionsBackend(fetcher=None, prefix=tmp_path, files=[VT, NH]).steps(manifest_regions, block_regions)  # type: ignore[arg-type]
    fetches = [s for s in steps if getattr(s, "kind", None) == "fetch"]
    assert len(fetches) == 2
    assert fetches[0].description.endswith("sha256, pinned by Hammunition")
    assert fetches[1].description.endswith("MD5 from Geofabrik only; not pinned")


def test_a_region_dropped_from_station_config_is_removed(tmp_path: Path, manifest_regions, block_regions) -> None:
    old = tmp_path / "share/hammunition/data/osm-regions/north-america-us-maine.osm.pbf"
    old.parent.mkdir(parents=True)
    old.write_bytes(b"x")
    steps = RegionsBackend(fetcher=None, prefix=tmp_path, files=[VT]).steps(manifest_regions, block_regions)  # type: ignore[arg-type]
    removals = [s for s in steps if getattr(s, "kind", None) == "remove-data"]
    assert [s.detail for s in removals] == [str(old)]
    removals[0].perform()
    assert not old.exists()


def test_derived_skips_a_region_already_converted_from_the_same_snapshot(tmp_path: Path, manifest_navit, block_navit, monkeypatch) -> None:
    out = tmp_path / "share/hammunition/data/osm-navit"
    out.mkdir(parents=True)
    (out / "north-america-us-vermont.bin").write_bytes(b"bin")
    (out / "north-america-us-vermont.bin.source").write_text("260101\n")
    stock = tmp_path / "navit.xml"
    stock.write_text((Path(__file__).parent / "fixtures/navit.xml").read_text())
    steps = DerivedBackend(prefix=tmp_path, files=[VT], stock=stock).steps(manifest_navit, block_navit)
    converts = [s for s in steps if "maptool" in getattr(s, "detail", "")]
    assert converts == []
```

Provide the four fixtures (`manifest_regions`, `block_regions`, `manifest_navit`, `block_navit`) at the top of the file from `PackageManifest.model_validate` of minimal dicts as in Task 4. Add to `tests/test_plan.py`:

```python
def test_map_data_is_deferred_by_name_without_regions(...) -> None:
    # Build a plan for the `navigation` profile with Station() (no regions);
    # assert osm-regions and osm-navit are Deferrals whose fix names
    # `hammunition station set --map-regions`, and navit is planned.
```

written with the existing `resolve()` test helpers in that file (read two existing deferral tests first and copy their setup).

- [ ] **Step 2: Run to verify they fail**, then **Step 3: implement** both backends in the style of `src/hammunition/backends/data.py` (read it first: `Action(kind=..., description=..., detail=..., perform=partial(...), requires_root=needs_root_for(prefix))`). The `maptool` call:

```python
result = subprocess.run(
    ["maptool", "--protobuf", "-i", str(pbf), str(tmp_bin)],
    capture_output=True, text=True, check=False,
)
if result.returncode != 0 or not tmp_bin.exists() or tmp_bin.stat().st_size == 0:
    tmp_bin.unlink(missing_ok=True)
    raise BackendError(f"maptool did not convert {pbf.name}: {result.stderr.strip()[-300:]}")
os.replace(tmp_bin, dest)
source_file.write_text(f"{region.snapshot}\n")
```

Wire planning: in `resolve()`, after catalog expansion, if any planned package's block is `RegionalDataInstall` or a `DerivedDataInstall` whose `source` is such a package, and `station.map_regions` is empty, move both to `deferred` with the `Deferral` described above. Region resolution (`geofabrik.resolve` for each region with `today=date.today()`, the loaded pins from `catalog/data/geofabrik-pins.yaml` via `find_catalog`, and a real `UrllibProbe`) happens in `src/hammunition/cli/main.py` before the backends are built, because it needs the network and the plan's disclosure must print it before the confirmation. Write `UrllibProbe` in `geofabrik.py` using `urllib.request` with a no-redirect handler for `head` (so the 302's `Location` is visible) and a 30 s timeout; it is the one part of Task 2's module that touches the network and has no unit test beyond construction.

Disk space: before confirming, sum the region sizes plus 2× that for Navit output (an estimate until Task 10 measures the real ratio), compare with `shutil.disk_usage(prefix).free`, and refuse with both numbers if short.

- [ ] **Step 4: Run, gates, commit**

```bash
git add src tests
git commit -m "Regions and derived backends: fetch, verify, convert, remove dropped regions; deferral without regions

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 7: `hammunition maps regions` and `update` reporting

**Files:**
- Modify: `src/hammunition/cli/main.py` (new `maps` command group with `regions [FILTER]`; `cmd_update`), `src/hammunition/geofabrik.py` (`index(probe) -> list[str]` from `https://download.geofabrik.de/index-v1.json`)
- Test: `tests/test_geofabrik.py`, `tests/test_cli.py`

**Interfaces:**
- Produces: `geofabrik.region_ids(index_json: str) -> list[str]` (pure: each feature's `properties.urls.pbf`, path between the host and `-latest.osm.pbf`); `hammunition maps regions [FILTER]` prints matching region paths, one per line, sorted; `hammunition update` prints, for `osm-regions`, each installed region's snapshot and, when the pin list has a newer yearly/monthly snapshot for it, `newer map data pinned: <snapshot>`.

- [ ] **Step 1: Failing tests**

```python
def test_region_ids_from_the_index() -> None:
    index = '{"features": [{"properties": {"urls": {"pbf": "https://download.geofabrik.de/north-america/us/vermont-latest.osm.pbf"}}}, {"properties": {"urls": {"pbf": "https://download.geofabrik.de/europe-latest.osm.pbf"}}}]}'
    assert region_ids(index) == ["europe", "north-america/us/vermont"]
```

and a CLI test stubbing the probe's `text` to return that index and asserting `maps regions vermont` prints exactly `north-america/us/vermont`. For `update`: a test with an installed `north-america-us-vermont.osm.pbf` and a `.source`-style record of snapshot `250101`, pins holding `260101`, asserting the line `newer map data pinned: 260101`. (Record the installed snapshot in a sidecar `<slug>.osm.pbf.source` written by Task 6's install step; if Task 6 did not write one, add it here and ledger the ruling.)

- [ ] **Step 2–4:** fail, implement, gates, commit:

```bash
git commit -m "maps regions lists Geofabrik's regions; update reports map data behind its pin

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 8: The pin generator, the catalog units, the profile and the category

**Files:**
- Create: `scripts/gen_geofabrik_pins.py`, `catalog/data/geofabrik-pins.yaml` (generated), `catalog/packages/navit.yaml`, `catalog/packages/osm-regions.yaml`, `catalog/packages/osm-navit.yaml`, `catalog/profiles/navigation.yaml`
- Modify: `catalog/categories.yaml` (new fine tag `navigation-maps`, title "Navigation & Maps", in the group holding `gps-gnss`), `tests/test_docs_generated.py` (the generator takes `--check`), README counts, CLAUDE.md counts
- Regenerate: every page generator `tests/test_docs_generated.py` lists

**Interfaces:**
- Produces: the three manifests and the profile the plan's Task 6 test names.

- [ ] **Step 1: The generator**

`scripts/gen_geofabrik_pins.py [--check] [--region R ...]`: for each of the 51 regions (the 50 states' Geofabrik paths under `north-america/us/` plus `district-of-columbia`, as a literal list in the script) and each of the current yearly and monthly snapshots, stream the file, compute sha256 and size, discard the bytes, and write the YAML (`pins:` rows with `region`, `snapshot`, `size`, `sha256`, `measured` date) with a header saying it is generated and by what. `--check` compares the committed file against a re-probe of each pinned URL's `HEAD` size only (no re-download) and exits 1 naming any pin whose URL no longer answers 200 or whose size changed — that is what the weekly CI job runs, so a monthly pin that aged out goes red. `tests/test_docs_generated.py` gets a case running `--check` that skips (with the reason) when the network is blocked, per the suite's socket rule.

Run it for real once on this machine in the background: `nohup .venv/bin/python scripts/gen_geofabrik_pins.py > /tmp/…/pins.log 2>&1 &`. It downloads about 10 GB per snapshot pass; commit the resulting YAML.

- [ ] **Step 2: The manifests**, each with the full `documentation` block the schema requires (what it does, why, prerequisites, known problems, upstream and support), `categories: [navigation-maps]` (plus `gps-gnss` for `navit`):
  - `navit.yaml`: apt `navit`, `navit-gui-internal`, `navit-graphics-gtk-drawing-area`, `espeak-ng`, `maptool`; `depends: [gpsd]`; launcher `exec: navit /usr/local/share/hammunition/data/osm-navit/navit.xml`, title "Navit (offline navigation)"; known_problems: the internal GUI's touch-first menus; the config is generated from Debian's and rewritten on each install; `~/.navit` keeps bookmarks and is never touched.
  - `osm-regions.yaml`: `method: osm-regions`, `provider: geofabrik`, ODbL; documentation says the regions come from station config, the three freshness modes and what each verifies, and the ODbL attribution obligation.
  - `osm-navit.yaml`: `method: derived`, `converter: navit-maptool`, `source: osm-regions`, `depends: [osm-regions, navit]`.
  - `navigation.yaml` profile: members `gpsd`, `gpsd-clients`, `navit`, `osm-regions`, `osm-navit`, with the profile documentation fields (what it installs, disk footprint "the regions you choose, plus about twice that for Navit" — replaced by Task 10's measured ratio, what it excludes (hiking, piece 2), what to configure by hand: `station set --map-regions`).

- [ ] **Step 3: Regenerate, gates, commit**

Run every generator the docs test names, then the full gates.

```bash
git add scripts catalog docs README.md CLAUDE.md tests
git commit -m "Catalog: navit, osm-regions, osm-navit, the navigation profile and category; US pins

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 9: D-057 and the operator docs

**Files:**
- Modify: `docs/DECISIONS.md` (D-057), `docs/reference/cli.md` (`station set --map-*`, `maps regions`, the plan's per-region lines, `update`'s map line), a new `docs/guides/offline-navigation.md` (daily use and EMCOMM: set regions, install, refresh, the launcher, "where am I" mode, what to do with no network), `docs/SCOPE.md` if it lists post-1.0 tracks
- Test: `.venv/bin/python scripts/check_doc_links.py`

- [ ] **Step 1:** D-057 records: the three freshness modes and why yearly is the default; MD5 as the disclosed weaker path and the maintainer's approval of it; the pin list and its yearly regeneration; derived data with converters as an enum; the `navigation-maps` tag (amending D-055's fixed vocabulary); what is measured and what is not, per Task 10.
- [ ] **Step 2:** The guide is written for a licensed ham with moderate Linux experience, with no region or location of the maintainer's in it — examples use Vermont and New Hampshire.
- [ ] **Step 3:** Link check, commit:

```bash
git commit -m "D-057 and the offline navigation guide

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 10: On the field laptop (the maintainer's regions, never recorded)

- [ ] **Step 1:** The maintainer runs `hammunition station set --map-regions <theirs>` themselves (or the controller runs it with values the maintainer gave in conversation; the values are never written anywhere but station config).
- [ ] **Step 2:** `hammunition install navigation --dry-run`, then for real (sudo for apt; the data lands under `/usr/local`).
- [ ] **Step 3: Measure**, recording only generic facts on the bench page (no region names): download size and time per region, `maptool` time and `.bin` size per region (the ratio replaces the plan's 2× estimate in `navigation.yaml` and the guide), Navit starting from the launcher, position from gpsd, a route between two points **in two different installed regions** (if it fails, implement the §6 fallback: routing through one `osmium merge`d file, and ledger it), voice through espeak-ng, and the whole run with networking off (`nmcli networking off`, then on again).
- [ ] **Step 4:** Update the bench page (a new session), the guide's measured numbers, and D-057's "measured" paragraph. Commit:

```bash
git commit -m "Bench record: offline navigation on the field laptop

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```
