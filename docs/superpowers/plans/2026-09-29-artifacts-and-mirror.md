# `artifacts` and the LAN mirror Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `hammunition artifacts --json` lists every remote data artifact for an explicit selection, and a `mirror` station key lets the verified fetch try a LAN mirror first, verified the same either way.

**Architecture:** A pure `hammunition.artifacts` module resolves the selection through the existing `geofabrik`/`copernicus` resolvers (probes injected); `interface/artifacts.py` is its D-059 document; `cli.main.cmd_artifacts` wires the real probes. The mirror lives in `Fetcher`: an ordered source list, fallback on any mirror failure, the same digest checked. Backends pass `MirrorPath(unit, name)` and disclose the order; `Action.facts` carries the actual source into `action_end`.

**Tech Stack:** Python 3.11+, stdlib `urllib`/`http.server`, pydantic dataclass schemas, pytest, mypy --strict, ruff.

**Spec:** `docs/superpowers/specs/2026-09-29-artifacts-and-mirror-design.md`

## Global Constraints

- No real network in tests; `tests/conftest.py` already refuses non-loopback sockets and stays that way.
- Examples and tests use public example regions only: Vermont, Delaware (`north-america/us/vermont`, `north-america/us/delaware`).
- With no mirror set, the plan text is byte-identical to today's (the golden text tests hold it).
- `digest` is always a hex digest; the checksum's location is `checksum_url` (ruling A1).
- Mirror path contract: `<mirror>/<unit>/<name>`, segments percent-quoted, `..`/empty refused.
- `--yes` changes nothing here; `artifacts` reads no station file.
- `make check` exit 0, captured to a log, `$?` tested.

## Review Focus

1. A mirror URL with a path prefix and/or trailing slash (`http://nas.lan:8080/bunker/`) — expected `http://nas.lan:8080/bunker/osm-regions/north-america/us/vermont`. Test in Task 2.
2. A mirror that is down (connection refused) for a 90-tile run — expected one failed attempt, then publisher-only with the reason recorded. Test in Task 2.
3. A mirror that answers 200 with the wrong bytes — expected discard, publisher fetch, same digest, `mirror_failure` names the hash mismatch. Tests in Tasks 2 and 6.
4. `--units osm-navit` (a derived unit that fetches nothing) or a typo — expected exit 2 naming it. Test in Task 5.
5. `--no-mirror` with no mirror set — expected no mirror section, no error. Test in Task 4.

---

### Task 1: The `mirror` station key

**Files:** Modify `src/hammunition/station.py`, `src/hammunition/interface/station.py`, `src/hammunition/cli/main.py` (`cmd_station_set`, parser). Test `tests/test_station.py`, `tests/test_json_station_hardware.py` (golden).

**Interfaces — Produces:** `Station.mirror: str | None`; `station.MIRROR_SCHEMES`; `StationDocument.mirror`; CLI `station set --mirror URL`, `--clear-mirror`.

- [ ] Write failing tests: `Station(mirror="http://nas.lan:8080/")` keeps the value; `ftp://`, `http://user:pw@h/`, `http://h/?q`, `http://` (no host) each raise `StationError`; `as_dict()`/`save_station`/`load_station` round-trip it; `"mirror" not in STATION_FIELDS`; `prompt_for` carries it through; `station set --mirror` saves it and `--clear-mirror` removes it; `station show` text prints it.
- [ ] Run, see them fail.
- [ ] Implement: `_NOT_TEMPLATES = _MAP_FIELDS | {"mirror"}`; validation with `urllib.parse.urlsplit`; `as_dict` adds `mirror`; `load_station` reads it; `prompt_for` passes it; CLI flags.
- [ ] Run tests; update the station golden with `HAMMUNITION_UPDATE_GOLDEN=1`, read the diff.
- [ ] Commit.

### Task 2: The verified fetch tries the mirror first

**Files:** Modify `src/hammunition/fetch.py`. Test `tests/test_fetch_mirror.py`.

**Interfaces — Produces:**

```python
@dataclass(frozen=True)
class MirrorPath:
    unit: str
    name: str

def mirror_url(mirror: str, path: MirrorPath) -> str: ...
class TransportUnreachable(BackendError): ...     # raised by UrllibTransport for URLError/OSError
MIRROR_TIMEOUT = 10.0
Fetcher(..., mirror: str | None = None, mirror_transport: Transport | None = None)
Fetcher.sources_for(url: str, path: MirrorPath | None) -> tuple[tuple[str, str], ...]   # (("mirror", u), ("publisher", u))
Fetcher.fetch(artifact, *, max_bytes=None, mirror: MirrorPath | None = None) -> FetchResult
Fetcher.fetch_md5(url, md5, *, expected_size, mirror: MirrorPath | None = None) -> FetchResult
FetchResult.source: str = "publisher"   # "cache" | "mirror" | "publisher"
FetchResult.url: str | None = None
FetchResult.mirror_failure: str | None = None
```

- [ ] Failing tests with a fake transport keyed by URL: mirror hit (publisher never asked, `source == "mirror"`); mirror 404 / wrong bytes / wrong size (md5 path) / over the cap → publisher, `mirror_failure` says why, nothing left in the cache but the verified file; mirror unreachable → publisher, and a second fetch on the same `Fetcher` never asks the mirror; both fail → `BackendError` naming both; no mirror set or no `MirrorPath` → publisher only; cache hit → `source == "cache"`, nothing asked; `mirror_url` with a prefix and trailing slash, quoting, and refusing `..`.
- [ ] Run, see them fail.
- [ ] Implement one `_attempt` loop shared by `fetch` and `fetch_md5`.
- [ ] Run tests, including `tests/test_fetch.py` unchanged.
- [ ] Commit.

### Task 3: `action_end` records what a step learned

**Files:** Modify `src/hammunition/backends/base.py` (`Action.facts`, `Action.sources`), `src/hammunition/execute.py` (both action_end sites). Test `tests/test_backends.py` or a new `tests/test_action_facts.py`.

**Interfaces — Produces:** `Action.facts: dict[str, str]` (default empty, not compared); `Action.sources: tuple[str, ...] = ()`; `action_end` gains the facts' keys when non-empty.

- [ ] Failing test: an Action whose perform writes `facts["source"] = "mirror"` produces an `action_end` entry with `"source": "mirror"`; an Action with no facts produces exactly today's keys.
- [ ] Implement; run; commit.

### Task 4: Backends, the plan and `install --no-mirror`

**Files:** Modify `src/hammunition/backends/{data,regions,dem}.py`, `src/hammunition/interface/plan.py` (`StepView.sources`, `MirrorSection`, `InstallPlanView.mirror`, rendering), `src/hammunition/cli/main.py` (`cmd_install`, parser). Tests `tests/test_data_backend.py`, `tests/test_regions_backend.py`, `tests/test_dem_backend.py`, `tests/test_json_plan.py`; plan goldens regenerated.

**Interfaces — Consumes:** Task 2's `MirrorPath`, `Fetcher.sources_for`, `FetchResult.source/url/mirror_failure`; Task 3's `Action.facts/sources`. **Produces:** `data_name(artifact) -> str` in `backends/data.py`; `fetch_outcome(result) -> str` and `fetch_facts(result, facts)` helpers in `fetch.py`; `MirrorSection(url: str, ignored: bool, text: str)`.

- [ ] Failing tests: with a mirror set, each backend's fetch step description says the LAN mirror is tried first and the digest is checked either way, `sources == (mirror_url, publisher_url)`, and running it records `facts["source"]`; without one, descriptions and details are today's. Plan view: `mirror` section present with a mirror, `ignored=True` under `--no-mirror`, absent otherwise; text byte-identical with no mirror.
- [ ] Implement; regenerate goldens; read the diffs.
- [ ] Commit.

### Task 5: `hammunition artifacts`

**Files:** Create `src/hammunition/artifacts.py`, `src/hammunition/interface/artifacts.py`. Modify `src/hammunition/cli/main.py`. Test `tests/test_artifacts.py`, golden `tests/fixtures/json/artifacts.json`.

**Interfaces — Produces:**

```python
@dataclass(frozen=True)
class Selection:
    regions: tuple[str, ...]
    freshness: str
    units: tuple[str, ...]

class SelectionError(Exception): ...
def select_units(catalog: Mapping[str, PackageManifest], requested: Sequence[str]) -> tuple[str, ...]
def list_artifacts(selection, catalog, catalog_root, *, today, region_probe, tile_probe) -> tuple[ArtifactEntry, ...]
# interface/artifacts.py
ArtifactEntry(unit, name, url, check, digest, checksum_url, size, licence, deferred)
ArtifactsDocument(map_regions, map_freshness, units, artifacts)   # KIND = "artifacts"
render_artifacts(doc) -> list[str]
```

- [ ] Failing tests against a fake Geofabrik probe and tile probe: data units listed with `sha256`; Vermont pinned vs Delaware unpinned (`md5-publisher`, digest the MD5, `checksum_url` `<url>.md5`); freshness `monthly` changes the URL; `latest` follows the redirect; no regions → one deferred entry per map unit; a 404 region deferred by name; tiles from an outline, a pinned one `sha256`, an unpinned one `etag-md5`; an unreadable outline deferred; `--units` unknown or derived → exit 2; the CLI reads no station (a station file with other regions is ignored); JSON validates and matches the golden; text lists the same values.
- [ ] Implement; run; commit.

### Task 6: End to end over loopback

**Files:** Test `tests/test_mirror_loopback.py`.

- [ ] Two `ThreadingHTTPServer`s on 127.0.0.1 (publisher, mirror) and the real `UrllibTransport`: mirror hit; mirror 404; mirror wrong bytes; mirror stopped (connection refused) then a second fetch skipping it; mirror and publisher both failing. Assert bytes, `source`, which server saw requests.
- [ ] Run; commit.

### Task 7: Documentation

**Files:** `docs/DECISIONS.md` (D-070 at the end), `CLAUDE.md` (table row), `CHANGELOG.md` (Unreleased), `docs/reference/cli.md` (`artifacts` section; station and install flags), `docs/reference/transaction-log.md`, `docs/guides/lan-mirror.md`, `docs/reference/json-interface.md` (regenerated). Test `tests/test_docs_mirror.py`.

- [ ] Failing doc test: D-070 recorded with its title; the guide exists, links the Bunker repository and says a mirror is a LAN address never reachable from the internet; cli.md documents `--mirror`, `--clear-mirror`, `--no-mirror` and the `artifacts` document.
- [ ] Write the docs; regenerate the JSON reference; `scripts/check_doc_links.py`.
- [ ] `make check` to a log; test `$?`; commit.
