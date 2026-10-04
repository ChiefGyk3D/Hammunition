# Fixtures

Documents the console reads, one file per command, plus `<name>.exit` where the exit code is not 0.

Recorded from engine 0.19.0 on their original dates. On 2026-10-03 the `engine` field of every JSON file here
was edited by hand to `0.20.0` and nothing else was changed; a container recapture is pending. Since the console
moved into the engine (#302) nothing reads that field: there is no version floor, so it is a record of the
recording, never compared. The statements below about the engine version describe the original captures.

Recorded from a real engine by `capture_fixtures.py` (this directory's parent) on a throwaway HOME with the
station set to `N0TST` / `FN31pr` (the engine's callsign check rejects `N0CALL`), scrubbed and scanned
(`fixture_scan.py`). That script refuses to run unless its HOME is a temporary directory it created itself, and
is never run on a maintainer's machine, only in a container or a throwaway VM. Review every file by eye for
identifiers before committing: the scan is a net.

Hand-authored, because the engine cannot produce the shape today, each validated against the engine's own
JSON Schema (`schemas/`) by `test_fixtures.py`:

- `regions.json`: the engine's documented example; recording it fetches Geofabrik's index.
- `logs.json`: a fresh machine has no runs; this carries every `result` word the schema documents.
- `update-all.json`: the E2 shape (issue #239): a retired unit as a row and exit 0. The `retired` state word
  is the proposal in that issue. Replace with a recording when #239 lands.
- `update-all-without.json` + `.exit`: engine 0.19.0 refusing `update` with exit 2 when the log names retired
  units. The message text is representative, not recorded.
- `plan-station-size-consent.json`: `plan-station` with a hand-authored `maps.terrain.topo.size_consent` (engine PR #260, topo-bound,
  not yet recorded); the published schema predates it, so `test_fixtures.py` exempts it (`AHEAD_OF_SCHEMA`).

`list-all.json` carries the E1 fields (`members`, `installed`, `installed_size_bytes`), recorded from the
engine's `profile-state` branch (PR #259); `list-all-without.json` is the engine without them (recorded from
`main`). `schemas/<kind>[-without].json` are extracted from the engine's `docs/reference/json-interface.md`.
