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
