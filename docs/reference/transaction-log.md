# Transaction log format

**Path:** `$XDG_STATE_HOME/hammunition/transactions.jsonl`, defaulting to
`~/.local/state/hammunition/transactions.jsonl`.

**Format:** JSON Lines — one JSON object per line, append-only. It is rotated
(below), never pruned.

JSONL rather than a single JSON document because a killed or crashed install
must leave every completed event intact and readable. A partially-written array
is not parseable; a partially-written last line costs you that line and nothing
else. Readers skip malformed lines rather than refusing the file.

**Why it exists:** **D-004** — true rollback is not achievable and this project
does not promise it. `hammunition uninstall` works from this log. What was done
is recorded so it can be undone by hand if it cannot be undone by us.

## Archives

A long-lived station's log has no natural end, and every reader walks all of
it. When a `transaction_begin` is about to be written and `transactions.jsonl`
is larger than 1 MiB, every **whole transaction older than the newest 20** is
moved into `transactions-<NNNNNN>-<UTC>.jsonl` in the same directory (**D-077**). A
transaction is never split, and one still open stays in the live file.

Readers lose nothing: `TransactionLog.read()` yields the archives in name
order (the leading sequence number, not the clock, orders them: a machine whose clock steps back before a GPS fix still reads its history in the order it was written) and then
the live file, the same events in the same order as before the move. `status`,
`update` and `uninstall`, and the replays they stand on, call only that, and a
test compares their output before and after a rotation. `hammunition transactions`
uses the same reader to display that history. **Nothing is deleted**: what
`uninstall` attributes to Hammunition is history. An archive that exists
and cannot be read stops the reader with an error rather than being skipped,
since skipping it would report installed units as not installed.

Appends take a shared lock on `transactions.jsonl.lock` and a rotation an
exclusive one, so a line is never written to the file a rotation is replacing.
A rotation killed halfway is recovered from `transactions.jsonl.rotating`,
which names the archive and how many lines it took; readers skip those lines
only when the live file really still begins with them. All of these files are
mode 0600 and, under `sudo`, handed to the operator like the log itself. The
thresholds (1 MiB, 20 transactions) are constants in `src/hammunition/state/log.py`.

---

## Common fields

Every entry carries these. Readers **must** tolerate unknown `event` values and
unknown extra keys, so a newer engine's log stays readable by an older one.

| Field | Type | Meaning |
|---|---|---|
| `event` | string | Event type. Required. |
| `version` | integer | Schema version of *this event type*, not of the log. |
| `timestamp` | string | ISO 8601, UTC, timezone-aware. |

## Never in the log

The writer **refuses** an entry containing a key whose name suggests a
credential — `password`, `secret`, `token`, `api_key`, `private_key` and
similar — and raises rather than writing it. CLAUDE.md forbids credentials in
generated files, and a log that records rendered configuration is the obvious
place for one to leak in. Refusing loudly is the only safe behaviour: a log is
written once and read later, so a silent redaction would be discovered by
somebody who needed the data.

---

## The transaction lifecycle

A run writes these in order. Each step is logged **before** it runs and its
outcome after, so a run killed mid-`apt-get` leaves a `command_begin` with no
matching end — which is exactly the state an operator needs to see, and the
state a log written only on success would hide.

Steps come in two kinds and are logged on the same contract. A **command** is a
process; an **action** is something the engine does itself, in process — today
verifying a download's digest and unpacking an archive, neither of which has an
honest `argv`. An action that fails ends the transaction exactly as a non-zero
exit does.

| `event` | Written | Carries |
|---|---|---|
| `transaction_begin` | Once, first | `target`, the manifest `packages` requested, the `apt_packages` the whole set resolved to. **Version 2** (2026-09-03) adds `deferred`: one `{kind, subject, what, why}` per thing the plan chose not to do — `kind: package` for a profile member the target does not offer (**D-039**), `kind: config` for a file a station value was missing for (**D-035**). `status` prints them; a version 1 entry has no key and nothing is inferred from its absence. When a D-077 run log is active, `run_log` records its path; older or unlogged transactions omit it. |
| `command_begin` | Before each command | `argv`, `requires_root`, `description`. |
| `command_end` | After each command that ran | `argv`, `returncode`. |
| `action_begin` | Before each in-process step | `kind` (`fetch`, `extract`, `config`, `requirements`, `wrapper`, `desktop-entry`, `patch`, `prepare`, `install-binary`, `verify-pin`, `remove-venv`, `remove-wrapper`, `remove-desktop-entry`), `detail`, `description`. |
| `action_end` | After each in-process step | `kind`, `detail`, `outcome` — one line saying what actually happened. `detail` (added 2026-08-31) is what uninstall's file-attribution replay reads back for `install-binary`; older entries without it leave those installs unattributed, reported and left in place. A step's own facts follow, never over one of those keys: a data download (a `data` unit's file, a map region, a terrain tile) adds `source` (`cache`, `mirror` or `publisher`), `fetched_from` (the URL the bytes came from, absent for `cache`) and, when a LAN mirror was passed over for the publisher, `mirror_failure` saying why (**D-070**). |
| `unit_end` | When a unit's last owned step exits 0, inside the transaction (#272, #279) | `unit`, `ok` (`true`), `run` (the `timestamp` of this run's `transaction_begin`), `catalog_version`, and either `pin` for a source, git or non-deb binary unit, or opaque SHA-256 `state` for regional, derived, DEM, topo and CoMaps data. Shared map-ledger checks belong to the units they validate. A later failure does not erase finished units; on success, records follow `verify_effects` and are omitted if verification fails. A reader that does not know the event ignores it. |
| `transaction_failed` | Instead of the rest, on the first failure | the failing `argv`, its `returncode` (or `error` for a missing binary), and how many commands `completed` before it. For an in-process step, `kind` and `detail` in place of `argv`. |
| `transaction_end` | Once, on the success path | `completed`, and the effect check below. |

### `unit_end` — what a rerun may trust (#272, #279)

```json
{"event": "unit_end", "version": 1, "timestamp": "2026-10-03T15:02:11+00:00",
 "unit": "osm-pmtiles", "ok": true, "run": "2026-10-03T14:31:07+00:00",
 "catalog_version": "1.0", "state": "…sha256…"}
```

`status` reads it: a unit with a `unit_end` in an install that then failed, or
was killed, reports `last_outcome: completed`, with `completed_in_failed_run`
naming that install; a unit whose steps only partly ran keeps the run's own
word (`failed`, or `interrupted` with no ending). The plan trusts a build only
when its declared outputs are on disk and its `pin` is exactly this manifest's
build directory. Map and terrain units require both a matching opaque `state`
fingerprint over resolved input pins/digests and selection, and an on-disk
check by their own backend (regional attribution, derived outputs, or DEM/topo
records and files). Changing a region set, input digest or topo bound, or
losing an output, replans the unit. The fingerprint does not store raw station
region selections. A later `uninstall_begin` naming the unit voids it. On
success, `unit_end` follows `verify_effects`; failed verification writes no
completion records. `uninstall` replays commands and actions and is
unaffected; `update` reads the same attribution as the plan. Logs written
before this event read as before, and the event reads across rotation, since
every reader walks the archives in order.

### `transaction_end` — version 2, the effect check (D-031)

Every command exiting 0 is **not** taken as evidence the machine changed:
`apt-get install` can exit 0 having installed nothing a held or broken package
quietly refused, and `gpasswd` exits 0 whether or not the membership took. So
after the last command completes, the run re-reads each claimed effect from the
same source resolution used — `apt-cache policy` for a package, the group
database for a membership, the filesystem for a build's declared binary — and
records the confirmed state here.

```json
{
  "event": "transaction_end",
  "version": 2,
  "timestamp": "2026-08-28T12:00:00+00:00",
  "completed": 2,
  "verified": true,
  "checks": [
    {"kind": "package", "subject": "js8call", "confirmed": true, "detail": "installed 2.2.0+ds1-1"},
    {"kind": "group", "subject": "op:dialout", "confirmed": true, "detail": "membership present in the group database"},
    {"kind": "binary", "subject": "fldigi:fldigi", "confirmed": true, "detail": "executable at /usr/local/bin/fldigi"},
    {"kind": "tree", "subject": "yaac:YAAC.jar", "confirmed": true, "detail": "tree marker present at /usr/local/share/hammunition/yaac/YAAC.jar"},
    {"kind": "launcher", "subject": "yaac:yaac", "confirmed": true, "detail": "executable wrapper at /home/op/.local/bin/yaac, runs in /usr/local/share/hammunition/yaac"}
  ]
}
```

| Field | Meaning |
|---|---|
| `verified` | `true` only when every check is confirmed. A completed run with `verified: false` exited 1 and named what did not take. |
| `checks[].kind` | `package`, `group`, `binary`, `tree`, `launcher`, or `verification` (the last when the re-probe itself could not run). |
| `checks[].subject` | The package name, `user:group`, `unit:install_as` for a binary a source, git or non-deb binary unit declares, `unit:tree_marker` for an installed tree, or `unit:launcher` for a generated wrapper. |
| `checks[].confirmed` | Whether the effect is actually present now, not whether the command exited 0. |
| `checks[].detail` | What was found — the installed version, or why it could not be confirmed. |

A `binary` check exists because a build's install step is the exit code that
lies most quietly: js8call v3.0.3's `CMakeLists.txt` has no install rule for
its executable, so `cmake --install` exits 0, writes an empty
`install_manifest.txt`, and installs nothing — and four targets had recorded the
unit `verified: true` on the strength of its build dependencies alone
(2026-09-02). The check is `<prefix>/bin/<install_as>` existing and being
executable, for every entry in the manifest's `binaries`.

A `tree` check covers the units that declare no `binaries` because they are
installed whole — yaac's zip, mshv's built directory, js8spotter, and the
two venv payloads — and had therefore ended `verified: true` with no check at
all (issue #27, 2026-09-05). `cp -aT` exits 0 on any directory, so each such
block names a `tree_marker`, one file the launcher depends on, and the check
is `<prefix>/share/hammunition/<unit>/<tree_marker>` existing. A `launcher`
check reads back every wrapper the run generated: `<~/.local/bin>/<name>`
must be an executable file, and where the launcher sets a
`working_directory`, that directory must exist — a wrapper that `cd`s into
a directory no install step created fails on every click. Both are unasked
questions, not failures, when the run has no prefix or no per-user bin
directory to look in.

Measured on Debian 13 from the clean snapshot, engine 4c83e11, 2026-09-05:
`js8spotter`, `yaac` and `supersdr` each ended with a `tree` and a
`launcher` check beside their packages -- `yaac` went from one check on a
dependency (`libjssc-java`) to four, one of them `YAAC.jar` itself. The
falsification the issue asked for was run on the same guest: with the
installed `YAAC.jar` removed, `verify_effects` against the live prefix went
`verified: false` on `tree yaac:YAAC.jar` naming the missing path, and green
again once it was put back. The two remaining tree units ran on the same
snapshot afterwards: `mshv` (89 s, an actual qmake build) confirmed
`tree mshv:bin/MSHV_x86_64` and a wrapper running in `.../mshv/bin`, and
`radiosonde-auto-rx` confirmed `tree radiosonde-auto-rx:auto_rx/auto_rx.py`
and a wrapper running in `.../radiosonde-auto-rx/auto_rx` -- so every marker
in the catalog has been read back from a real install, not only inferred
from the archive listing.

`uninstall` will trust this record over an exit code: a package recorded
`confirmed: false` was never actually installed and must not be "removed". A
version-1 `transaction_end` (written before this check existed) carries no
`verified` key, and a reader treats its absence as *not recorded* rather than as
a passing verdict.

---

## `consent_affirmed`

Written when an operator affirms a consent gate (**D-021**). This is the record
that a human took responsibility, which is the point of the gate — `--dry-run`
already prints what will change, and the log already records what changed;
neither records who authorized it.

```json
{
  "event": "consent_affirmed",
  "version": 1,
  "timestamp": "2026-08-26T12:00:00+00:00",
  "profile": "rf-research",
  "decision": "environment",
  "risk_categories": ["unlicensed_transmission", "spectrum_disruption"],
  "env_var": "HAMMUNITION_ACCEPT_RF_RESEARCH",
  "disclosure_sha256": "4073052978cc...",
  "disclosure_text": "Profile 'rf-research' is consent-gated.\n\n…",
  "actor": "chiefgyk3d"
}
```

| Field | Meaning |
|---|---|
| `profile` | The gated profile. Gates attach to profiles, not packages (**D-021**). |
| `decision` | `interactive` — a person answered a prompt. `environment` — the profile's declared variable was set. Never anything else; `--yes` cannot produce this event. |
| `risk_categories` | Every category the profile declared. Capability, never legality. |
| `env_var` | The profile's own variable, recorded whether or not it was the path used, so the log shows what *would* have worked. |
| `disclosure_text` | The exact text shown, verbatim. |
| `disclosure_sha256` | Digest of that text. |
| `actor` | Whoever the engine believes ran it, or `null`. Best-effort and not an identity claim. |

**Why the full text and not just the digest.** A digest proves the text did not
change; it does not tell a reader six months later what the operator was
actually told. Both are recorded, and they come from one function
(`render_disclosure`) so the prompt and the record cannot drift apart.

**Absence is meaningful.** No `consent_affirmed` entry for a gated profile means
no affirmation was given. There is no path that installs a gated profile without
writing this, and `--yes` is not such a path — that is asserted by test, not
just intended.

**A third-party apt repository writes the same event** (**D-040**), one per
repository added, with `profile` set to `apt-repo:<name>`, an empty
`risk_categories` (a repository is not an RF capability), and an `extra`
object that says what was trusted:

```json
{
  "event": "consent_affirmed",
  "version": 1,
  "profile": "apt-repo:microsoft-vscode",
  "decision": "environment",
  "risk_categories": [],
  "env_var": "HAMMUNITION_ACCEPT_APT_REPO_MICROSOFT_VSCODE",
  "extra": {
    "kind": "apt_repo",
    "unit": "code",
    "repository": "microsoft-vscode",
    "uri": "https://packages.microsoft.com/repos/code",
    "key_fingerprint": "BC528686B50D79E339D3721CEB3E94ADBE1229CF"
  }
}
```

`decision: environment` here means the variable held the **fingerprint**,
not `1` — a `1` is refused, and `--yes` cannot produce this event either. The
files the repository added are attributed the same way as any other
`install -D` (see the uninstall lifecycle), so the log says both who trusted
the key and where it was written.

---

## `sudo_keepalive_begin` and `sudo_keepalive_end`

Written by an `install` run as a user whose plan mixes root steps with steps
that are not, unless `--no-sudo-keepalive` was given (**D-062**): the run
asks sudo's password once and keeps sudo's ticket valid until it ends.
Neither is written by a dry run, by a run as root, or with the flag.

`sudo_keepalive_begin` comes after the confirmation and before
`transaction_begin`, once `sudo -v` has returned:

| Field | Meaning |
|---|---|
| `validated` | Whether `sudo -v` succeeded. `false` means nothing is refreshed and each root step asks for itself; no `sudo_keepalive_end` follows. |
| `interval_seconds` | Seconds between `sudo -n -v` refreshes: 240 by default. |

`sudo_keepalive_end` comes after the transaction's own last entry, whether it
ended in `transaction_end` or `transaction_failed`, when the refreshing stops:

| Field | Meaning |
|---|---|
| `refreshes` | How many `sudo -n -v` refreshes succeeded. |
| `failed` | `null`, or the refresh that failed and stopped it: `argv`, `returncode`, and its own `timestamp`. After it, a root step may have prompted. |

Nothing about the password is ever in the log: the engine never sees it.
A `sudo_keepalive_begin` with no `sudo_keepalive_end` is a run that was
killed; the refreshing died with it.

---

## The uninstall lifecycle

Written by `hammunition uninstall`. Same before/after ordering, same
first-failure stop, and the same shared `command_begin` / `command_end` events
as an install — that sharing is deliberate, because **attribution replays
`command_end` alone**: an `apt-get install` that exited 0 attributes the
packages after its `--`, an `apt-get remove` that exited 0 un-attributes
them, chronologically. The apt command's own recorded outcome is the source
of truth, not the surrounding transaction — a run that died on command 3 of 5
still installed whatever command 2 installed.

| `event` | Written | Carries |
|---|---|---|
| `uninstall_begin` | Once, first | `target`, the unit `packages` being removed, the `apt_packages` the single `apt-get remove` will name. |
| `command_begin` / `command_end` | Around each command | Identical shape to the install lifecycle's. |
| `uninstall_failed` | Instead of the rest, on the first failure | the failing `argv`, its `returncode` (or `error` for a missing binary), and how many commands `completed`. |
| `uninstall_end` | Once, on the success path | `completed`, `verified`, and `checks[]` with `kind: "package_removed"` — confirmed means apt was re-probed and the package is **absent** (**D-031**), because `apt-get remove` exits 0 for a package a held dependency kept installed. |

---

## Hardware events

Written by `hammunition hardware apply` (**D-056**, **D-058**, **D-069**,
issue #177), one entry per privileged command that succeeded, as soon as it
succeeded. `hardware unapply` reads `hardware_artifacts` only; the others are
a record, and every removal is by file content rather than by this log.

| `event` | Written | Carries |
|---|---|---|
| `hardware_artifacts` | After the helper's wrapper or the polkit action is installed | `files[]`: `path` and `mode`. `unapply` removes only the two exact paths it owns, and none where the installed helper is hammunition-tray's. |
| `time_grants` | Per GPS-time step | `description`, `argv`. |
| `geoclue_files` | Per GeoClue step | `description`, `argv`. |
| `gps_resume` | Per GPS resume step | `description`, `argv`. |
| `devctl_export` | Per list written (**D-056**, amended 2026-10-02) | `description`, `argv`: the `install -D` of `/etc/hammunition/devctl-devices.yaml` or `/etc/hammunition/devctl-services.yaml`. Never the lists' contents (`docs/reference/devctl-lists.md`). |

---

## Planned events

Not yet implemented. Listed so the format is designed once rather than grown.

| `event` | Records |
|---|---|
| `install_begin` / `install_end` | A run: profiles and packages requested, resolved target, dry-run flag, outcome. |
| `package_installed` | One package: name, manifest version, backend used, resolved upstream version. |
| `system_modification` | One change from a manifest's `system_modifications` — udev rule, group, repo — with its `reversible` flag and `reverse_hint`. |
| `apt_repo_added` | Third-party repo: URI, suites, key fingerprint, and that the rationale was shown. |
| `config_file_written` | Path, whether an existing file was backed up, and where the backup went. Never the rendered contents, which may hold station-local data. |
| `conflict_resolved` | A `conflicts_with_repo_package` decision: what was displaced, whether it was removed or coexists, and how to restore it. |
