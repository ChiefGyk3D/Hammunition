# `hammunition artifacts` and a LAN mirror — design (D-070)

Status: the engine half of Hammunition Bunker, approved in conversation
2026-09-29 as the section "The engine side" of
the Bunker repository's design spec, 2026-09-29
(<https://github.com/Renegade-Penguin/hammunition-bunker>).
This document restates that section in this repository's terms: the modules
it touches, the names it adds, and the rulings taken where the Bunker spec
left a choice. Decision number assigned: **D-070**.

## What the Bunker needs from the engine

1. A way to ask, with no station and no install, *which remote artifacts
   would the engine fetch for this selection* — `hammunition artifacts
   --json`.
2. A way for a field machine to take those artifacts from the Bunker on the
   LAN instead of the publisher, verified exactly as before — a `mirror`
   station key.

Nothing else. The Bunker carries no pins and no verifier; the engine stays
the one place either lives.

## 1. `hammunition artifacts`

```
hammunition artifacts [--json] [--map-regions R[,R…]] [--map-freshness yearly|monthly|latest] [--units U[,U…]]
```

**Selection is explicit.** No station file is read; nothing in the output
is the operator's. `--map-regions` is validated by the same `REGION` shape
`station set` uses. `--map-freshness` defaults to `yearly`, the station's
own default.

**Units.** `--units` defaults to every catalog unit with a `data`,
`osm-regions` or `dem-tiles` install block — the three install methods that
fetch data (D-049, D-057, D-061). A `derived` unit fetches nothing and is
not listed. A name given to `--units` that is not in the catalog, or that
fetches no data artifact, refuses the command with exit 2, naming it (the
name the operator typed refuses, D-039).

**Per unit:**

| method | one entry per | `name` | `check` | `digest` | `checksum_url` |
|---|---|---|---|---|---|
| `data` | artifact, across every install block | `install_as`, else the URL's file name | `sha256` | the pin | null |
| `osm-regions` | region | the region path | `sha256` if the resolved snapshot is pinned, else `md5-publisher` | the pin, or Geofabrik's MD5 read at resolution | null, or `<url>.md5` |
| `dem-tiles` | tile any region's outline touches | the tile name | `sha256` if pinned, else `etag-md5` | the pin, or the ETag's MD5 | null, or the tile URL (its `HEAD`) |

Regions resolve through `geofabrik.resolve` with the same pins, freshness
and fallback the plan uses, so freshness changes the URL and the check
exactly as it does in the plan. Tiles resolve through the same outline,
tile list, pins and `copernicus.resolve_tile` as `terrain_plan`, but never
read the local install records: the listing is the same on every machine.

**Deferred, never dropped.** Map units with no `--map-regions`: one entry
per unit, `name` null, `deferred` saying so and naming the flag. A region
Geofabrik cannot resolve (offline, 404): an entry named for the region with
the reason. A region whose outline cannot be read: a `dem-tiles` entry named
for the region. A tile that cannot be resolved: an entry named for the
tile. Deferred entries do not change the exit code; the document is the
answer.

**The document**, `ArtifactsDocument`, kind `artifacts`:
`map_regions`, `map_freshness`, `units` (the selection), and `artifacts`, a
list of `ArtifactEntry`: `unit`, `name`, `url`, `check`, `digest`,
`checksum_url`, `size`, `licence`, `deferred`. `check` is one of `sha256`,
`md5-publisher`, `etag-md5`, `sha256-publisher`; the last is in the Bunker
contract and no catalog unit produces it today.

**Ruling A1 — `digest` is always a digest.** The Bunker spec lets `digest`
be "the URL of the publisher's checksum, and the digest itself once read".
One field holding either a URL or a hex string is a parse ambiguity a
contract should not have. The engine reads the publisher's checksum during
resolution anyway, so `digest` is the digest, and the URL it was read from
is the added `checksum_url` field. A checksum that cannot be read makes the
entry deferred, never a half-filled one.

**Text form.** One line per artifact: unit, name, size, check and URL, then
the deferred entries with their reasons.

## 2. The mirror

**Station.** `station set --mirror URL` stores `mirror:`;
`station set --clear-mirror` removes it (a key that can be set must be
removable without editing the file). Validated: `http` or `https`, a host,
no user or password (no credentials in a station file), no query or
fragment. It is not a template variable. `station show` prints it;
`station show --json` carries it.

**Ruling M1 — LAN-only is documented, not enforced.** A hostname cannot be
proved private without resolving it, and the check that makes a mirror safe
is the hash, not the address. The docs say a mirror URL is a LAN address and
never something reachable from the internet.

**Fetch.** `Fetcher` gains `mirror`. `fetch()` and `fetch_md5()` take an
optional `MirrorPath(unit, name)`; with a mirror set, the first source is
`<mirror>/<unit>/<name>` (each path segment percent-quoted, `..` and empty
segments refused) and the second the publisher URL. Any failure at the
mirror — unreachable, an HTTP error, the size cap, a wrong size, a wrong
hash — discards what it sent and tries the publisher, verifying the same
digest. `FetchResult` gains `source` (`cache`, `mirror` or `publisher`),
`url` (where the bytes came from) and `mirror_failure` (why the mirror was
passed over).

**Ruling M2 — a mirror found unreachable is not asked again that run.** One
fetcher serves the whole transaction; a mirror that refused a connection
would otherwise cost a timeout per tile, and a region of 90 tiles is 90
timeouts. After a connection-level failure (not an HTTP status), later
fetches go straight to the publisher and record why. The mirror transport
uses a 10-second timeout.

**Ruling M3 — only data is mirrored.** The artifacts `artifacts` lists —
`data`, `osm-regions` and `dem-tiles` — are the ones the mirror is asked for.
Source tarballs, prebuilt binaries, wheels and npm packages are not in the
Bunker's contract and keep one source.

**Plan.** Each mirrored fetch step says, in its description, that the LAN
mirror is tried first and the publisher second, and that the hash is checked
either way; its detail names both URLs in order. `StepView` gains `sources`,
the URLs a step fetches from in the order tried (empty for any other step).
The plan gains a `mirror` section (`InstallPlanView.mirror`, printed as
*Data mirror (D-070)*) when a mirror is set: the URL, or that `--no-mirror`
ignores it this run. With no mirror set, the text is byte-identical to
today's.

**Install.** `--no-mirror` ignores the station key for one run.

**Log.** An `Action` gains `facts`, a small mapping the step fills while it
runs; `action_end` carries it when non-empty. A mirrored fetch records
`source`, `fetched_from` and, when the mirror was passed over,
`mirror_failure`. The outcome line says the same in words.

## Docs

D-070 at the end of `docs/DECISIONS.md`; a CLAUDE.md table row; CHANGELOG
under Unreleased; `docs/reference/cli.md` (a new `artifacts` section, the
station and install flags); `docs/reference/transaction-log.md` (the
`action_end` facts); `docs/reference/json-interface.md` regenerated;
`docs/guides/lan-mirror.md`, pointing at
<https://github.com/Renegade-Penguin/hammunition-bunker> for the server side.

## Testing

No test touches the internet: the suite already refuses non-loopback
sockets. Unit tests inject fake transports and probes. One end-to-end test
runs two `http.server` instances on 127.0.0.1, a publisher and a mirror,
through the real `UrllibTransport`: mirror hit, mirror 404, mirror wrong
bytes, mirror down, and publisher failure after a mirror failure. Examples
use Vermont and Delaware.
