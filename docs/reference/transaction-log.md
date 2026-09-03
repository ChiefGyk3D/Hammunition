# Transaction log format

**Path:** `$XDG_STATE_HOME/hammunition/transactions.jsonl`, defaulting to
`~/.local/state/hammunition/transactions.jsonl`.

**Format:** JSON Lines — one JSON object per line, append-only, never rewritten.

JSONL rather than a single JSON document because a killed or crashed install
must leave every completed event intact and readable. A partially-written array
is not parseable; a partially-written last line costs you that line and nothing
else. Readers skip malformed lines rather than refusing the file.

**Why it exists:** **D-004** — true rollback is not achievable and this project
does not promise it. `hammunition uninstall` works from this log. What was done
is recorded so it can be undone by hand if it cannot be undone by us.

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
| `transaction_begin` | Once, first | `target`, the manifest `packages` requested, the `apt_packages` the whole set resolved to. **Version 2** (2026-09-03) adds `deferred`: one `{kind, subject, what, why}` per thing the plan chose not to do — `kind: package` for a profile member the target does not offer (**D-039**), `kind: config` for a file a station value was missing for (**D-035**). `status` prints them; a version 1 entry has no key and nothing is inferred from its absence. |
| `command_begin` | Before each command | `argv`, `requires_root`, `description`. |
| `command_end` | After each command that ran | `argv`, `returncode`. |
| `action_begin` | Before each in-process step | `kind` (`fetch`, `extract`, `config`, `requirements`, `wrapper`, `desktop-entry`, `patch`, `prepare`, `install-binary`, `verify-pin`, `remove-venv`, `remove-wrapper`, `remove-desktop-entry`), `detail`, `description`. |
| `action_end` | After each in-process step | `kind`, `detail`, `outcome` — one line saying what actually happened. `detail` (added 2026-08-31) is what uninstall's file-attribution replay reads back for `install-binary`; older entries without it leave those installs unattributed, reported and left in place. |
| `transaction_failed` | Instead of the rest, on the first failure | the failing `argv`, its `returncode` (or `error` for a missing binary), and how many commands `completed` before it. For an in-process step, `kind` and `detail` in place of `argv`. |
| `transaction_end` | Once, on the success path | `completed`, and the effect check below. |

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
    {"kind": "binary", "subject": "fldigi:fldigi", "confirmed": true, "detail": "executable at /usr/local/bin/fldigi"}
  ]
}
```

| Field | Meaning |
|---|---|
| `verified` | `true` only when every check is confirmed. A completed run with `verified: false` exited 1 and named what did not take. |
| `checks[].kind` | `package`, `group`, `binary`, or `verification` (the last when the re-probe itself could not run). |
| `checks[].subject` | The package name, `user:group`, or `unit:install_as` for a binary a source, git or non-deb binary unit declares. |
| `checks[].confirmed` | Whether the effect is actually present now, not whether the command exited 0. |
| `checks[].detail` | What was found — the installed version, or why it could not be confirmed. |

A `binary` check exists because a build's install step is the exit code that
lies most quietly: js8call v3.0.3's `CMakeLists.txt` has no install rule for
its executable, so `cmake --install` exits 0, writes an empty
`install_manifest.txt`, and installs nothing — and four targets had recorded the
unit `verified: true` on the strength of its build dependencies alone
(2026-09-02). The check is `<prefix>/bin/<install_as>` existing and being
executable, for every entry in the manifest's `binaries`.

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
