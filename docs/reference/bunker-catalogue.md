# Bunker catalogue

The engine and Bunker share `hammunition.catalogue.parse(raw: bytes)` and
`hammunition.keystrength.classify(public_key_line: str)`. The reader accepts
UTF-8 JSON version 3, refuses duplicate JSON fields and invalid required fields
by name, and allows extra fields within version 3. Typed models are frozen;
wire lists become tuples. This wire format has no CLI JSON envelope.

## Fields

| Field | Type | Rule |
|---|---|---|
| `kind` | str | exactly `bunker-index` |
| `version` | int | `3`; a reader refuses a higher version by name |
| `serial` | int | ≥ 1, strictly greater on every change |
| `generated` | str | RFC 3339 UTC, `Z` suffix |
| `bunker.name` | str | `[a-z0-9][a-z0-9-]{0,62}`; the signing principal is `bunker:<name>` |
| `bunker.mode` | str | `personal` or `group` |
| `signers` | list | 1–16 entries; larger lists are refused before key classification; `signature` is a relative path under `catalogue.sig.d/` |
| `signers[].algorithm` | str | the OpenSSH key type string of `public_key` |
| `signers[].bits` | int | key size as `ssh-keygen -l` reports it |
| `signers[].hardware` | bool | the Bunker's claim; provable only for `sk-*` types |
| `signers[].no_touch_required` | bool | true only for an `sk-*` key created with `-O no-touch-required`; **display only**: OpenSSH's allowed-signers format has no touch option (measured 2026-10-07 on OpenSSH 10.3: `bad options: unknown key option`), so the engine shows it at enrolment and in status and never writes it. Whether `-Y verify` accepts a signature made without touch is a bench item |
| `artifacts` | list | may be empty (`[]`) on a fresh Bunker |
| `inputs` | list | may be empty (`[]`) on a fresh Bunker; `signers` still requires ≥ 1 |
| `artifacts[]` | object | the v2 entry fields unchanged, plus `publisher_name` (str or null), `publisher_size` (int or null), `share` (`all` or `owner:<enrolment id>`) |
| `inputs[].kind` | str | one of `region-outline`, `tile-selection`, `sheet-selection`, `dem3dep-selection`, `fstopo-selection` |
| `inputs[].region` | str | an OSM region name as the engine spells it |

All declared fields are required, including nullable fields. `engine_version`
is a string or null; `deferred` and `declined` are JSON lists and `last_run`
is any JSON value. Artifact fields are `unit`, `name`, `path`, `sha256`, `size`,
`publisher_check`, `publisher_digest`, `publisher_url`, `publisher_name`,
`publisher_size`, `licence`, `fetched`, `verified`, `status`, `reason`,
`previous` and `share`. Input fields are `kind`, `region`, `name`, `path`,
`sha256`, `size` and `fetched`. Signers also require `id` (the SHA256 OpenSSH
fingerprint), `public_key` and `signature`.

Held-byte fields (`path`, `sha256`, `size`, `fetched`, `verified`) may be null
for failed or unheld artifacts. Such entries remain in the catalogue, but
artifact lookup refuses entries without path, digest or size. Status and reason
retain the writer's vocabulary. `publisher_digest`, `reason` and `previous`
are also nullable. `publisher_url` is always a string.

Paths and names are safe relative paths without empty, dot or parent segments,
backslashes or CR/LF/NUL. Units have one segment. Digests are 64 lowercase hex
digits; sizes are strict nonnegative integers. Publisher name and size must be
set or null together, with positive size and a safe name. Timestamps must have
valid calendar dates and the RFC 3339 UTC `Z` form. Duplicate signer ids,
signature paths, artifact `(unit, name)` pairs and input `(kind, region)` pairs
are refused. Input paths equal `inputs/<kind>/<name>`; artifact paths may differ
from request names (for example, dated OSM files).

## Key strength

| rank | Types | weak |
|---|---|---|
| 1 | `ssh-ed25519`, `sk-ssh-ed25519@openssh.com` | no |
| 2 | `ecdsa-sha2-nistp256/384/521`, `sk-ecdsa-sha2-nistp256@openssh.com` | no |
| 3 | `ssh-rsa` ≥ 3072 bits | no |
| 4 | `ssh-rsa` 2049–3071 bits | no, but below the recommended 3072 |
| 5 | `ssh-rsa` ≤ 2048 bits | **yes**: warning text "RSA <bits>-bit is weak: replace with Ed25519, ECDSA or RSA 3072+" |

Other types, including DSA, are refused. RSA weak-key warning text is exactly
`RSA <bits>-bit is weak: replace with Ed25519, ECDSA or RSA 3072+`.
`KeyStrength` also carries `fingerprint` metadata. The embedded key type must
match the public line's type; OpenSSH supplies size and fingerprint. `sk-*`
keys must claim hardware; other hardware claims require operator affirmation
at enrolment. `no_touch_required=true` is refused on a non-`sk` type and is
display metadata only, never an allowed-signers option.

## Signatures and trust

Signatures cover exactly the served `catalogue.json` bytes, without reencoding.
Namespace: `hammunition-bunker-catalogue`; principal: `bunker:<bunker.name>`.
Each signer names its file under `catalogue.sig.d/`. The local enrolment store
is `~/.config/hammunition/mirror.json` (0600), carrying URL, Bunker name,
enrolment id, enrolled public lines, algorithm, bits, hardware affirmation and
accepted serial. Verification uses an ephemeral OpenSSH allowed-signers file:

```text
bunker:<name> namespaces="hammunition-bunker-catalogue" <public key>
```

Any enrolled signer that verifies may satisfy trust; hardware-required mode
counts only an enrolled hardware key. An equal serial is accepted; a lower
serial is rollback and requires explicit `mirror accept-older`. The writer
increments serial on every change. A generated timestamp older than 30 days
warns. Parsing alone performs no signature, freshness or cross-run serial check.

Trust tiers remain distinct: a repository-pinned sha256 is publisher-byte
trust; a publisher digest records the publisher's check; a Bunker signature
and stored sha256 authenticate what the enrolled Bunker held, and do not turn
an unverified publisher download into verified publisher bytes.

## Routes and sharing

Catalogue: `<mirror>/catalogue.json`; signatures:
`<mirror>/catalogue.sig.d/<n>.sig`; artifacts: `<mirror>/<unit>/<name>`;
inputs: `<mirror>/inputs/<kind>/<name>`. Git bundles use unit `git-bundles`,
name `<unit>@<commit>`; submodule artifacts use
`<unit>@<commit>/<submodule path>@<commit>`. File mirrors read these same paths
from a directory and use no headers.

A missing catalogue refuses with:
`no catalogue at <url>/catalogue.json: <reason>. Enrol a Bunker that serves one, or run without --offline.`
Here `<url>` has no trailing slash.

In group mode requests carry `X-Hammunition-Enrolment: <enrolment id>`.
The id is nonempty printable ASCII without whitespace or controls. All entries
are parsed and retained; lookup selects `all` or matching `owner:<id>` entries.
Personal mode ignores this sharing filter. The Bunker answers 404 for another
owner's bytes. This is a sharing filter, not access control: the header is sent
in clear over plain HTTP.
