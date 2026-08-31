<!--
SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
SPDX-License-Identifier: GPL-3.0-or-later
-->

# CLI reference

The `hammunition` command, at **v0.2.0 (alpha)**. Five backends are
implemented: **apt**, **source**, **git**, **binary** and **venv** (per-user
virtualenvs, hash-pinned end to end with `pip --require-hashes`). pipx and
CPAN re-measured to zero users and left the 1.0 list (D-014 amendment,
2026-08-30); a package declaring one is still **refused by name**. The
install/configure/remove cycle is VM-verified on Parrot, Kali and Debian 13
(`docs/reference/vm-verification-parrot.md` and siblings).

The source backend is the expensive half of the parity target: **57 of AHRL's
95 units cannot be satisfied by apt**, and 35 of those are source builds from
bundled tarballs.

## Installing the engine

A git clone is the supported install. The wheel carries the engine; the catalog
is a separate tree, and the CLI finds `catalog/` by walking up from its own
location, so running it from a checkout needs no configuration.

```
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
.venv/bin/hammunition status
```

Override the catalog location with `--catalog DIR` or `HAMMUNITION_CATALOG`.
A directory with no `packages/` inside it is an error rather than an empty
catalog, because an empty catalog makes `list` print nothing and look like an
answer.

## Global flags

`--version` prints the engine version and exits. `--catalog DIR` points at a
catalog other than the checkout's own.

## Verbs

### `hammunition status`

What this machine is, what the catalog holds, and what has been done here.

```
Target: Debian GNU/Linux 13 (trixie) (ID=debian, version=13, arch=x86_64)
Debian family: yes
Catalog: /home/op/Hammunition/catalog
  58 packages, 56 of which resolve on this target
  4 profiles
Transaction log: /home/op/.local/state/hammunition/transactions.jsonl
  no transactions recorded
```

The target line reports what `/etc/os-release` said, not what we concluded from
it. A system that declares no `ID` is an error, never a guess — see
`docs/DESIGN.md` §8.

### `hammunition list [all|packages|profiles]`

Everything in the catalog, with each package's install method **on this
machine**. A package that does not resolve here says `unsupported here` rather
than being hidden; a package with a recorded `broken` or `retired` status is
flagged with it.

### `hammunition show PROFILE`

A profile's documentation, its package list, and — for a gated profile — the
full consent disclosure, printed without installing anything. This is how an
operator reads a disclosure before deciding, rather than while being asked.

### `hammunition install NAME... [--dry-run] [--yes] [--refresh] [--user NAME]`

Names may be packages or profiles, mixed freely.

| Flag | Effect |
|---|---|
| `--dry-run` | Resolve everything, print exactly what would run, change nothing |
| `--yes` | Skip the confirmation. **Does not satisfy a consent gate** (D-021). Also suppresses the station prompt |
| `--refresh` | Run `apt-get update` as the transaction's first command |
| `--user NAME` | Who to add to groups. Defaults to `$SUDO_USER`, then `$USER` |
| `--callsign CALL` | Station callsign for this run. Overrides the saved value |
| `--grid-square LOC` | Maidenhead locator, four or six characters |
| `--node-alias NAME` | Short packet node alias, up to six characters |

**Suggestion groups.** A profile may suggest one-of-several optional
companions (the packet profile's mail client is the first): the run
*detects* first — any of the group's known commands on PATH means the
system's own choice is respected and nothing is offered — and only an
interactive run without `--yes` gets the selection, every option an
open-source catalog manifest, with skip always an answer. Non-interactive
runs note the skip and never block (the D-035 shape). Nothing from a
suggestion group is ever installed silently.

### `hammunition uninstall NAME... [--dry-run] [--yes] [--user NAME]`

Removes what Hammunition itself installed, and only that (**D-004**). Names
may be packages or profiles, mixed freely.

| Flag | Effect |
|---|---|
| `--dry-run` | Resolve the removal, print exactly what would run, change nothing |
| `--yes` | Skip the confirmation |
| `--user NAME` | Whose transaction log to read. Defaults to `$SUDO_USER`, then `$USER` |

"Installed by Hammunition" is read from the transaction log, by replaying the
recorded `apt-get` commands that actually exited 0 — not from what a run
*intended*. The plan then partitions honestly, and prints every part:

- **Removing** — attributed to Hammunition and currently installed. These
  become one `apt-get remove` (never `purge`: configuration a user may have
  edited stays on disk).
- **Left in place** — installed, but not installed by Hammunition. It was
  there before us or arrived by another road; removing it would exceed the
  promise.
- **Already absent** — attributed but no longer installed.

What it deliberately does not reverse, and says so in every plan:
dependencies apt pulled in (`sudo apt autoremove` clears orphans), group
memberships, and any configuration files written — all recorded in the log.
A unit whose install on this target is not apt is refused with the backend
named: the engine does not yet know how to reverse a `make install`, and a
file sweep pretending otherwise is the shim CLAUDE.md forbids.

After the commands complete, the removal is **verified** the same way an
install is (**D-031**): apt is re-probed and the run is only reported clean
when every package is confirmed absent. A removal apt quietly declined exits
1 with `verified: false` in the log.

### `hammunition menus apply [--gnome]`

Writes the curated **Ham Radio** desktop-menu layer (**D-036**), generated
from the catalog's own category vocabulary — one taxonomy, no second list.
Two mechanisms, both per-user and unprivileged:

- **Menu-spec DEs (Xfce and friends):** a merged `.menu` tree with one
  submenu per catalog category, each populated by the
  `X-Hammunition-<category>` markers every generated desktop entry already
  carries, plus the `.directory` entries naming them. Honours
  `$XDG_MENU_PREFIX`, because a merged file that does not match the root
  menu's name merges nothing, silently.
- **GNOME:** an app-folder named *Ham Radio* populated by
  `categories=['HamRadio']` — no app list to maintain. Applied only when
  `XDG_CURRENT_DESKTOP` says GNOME (or `--gnome` forces it), and it needs
  your desktop session's bus: over bare SSH it fails loudly rather than
  pretending. The folder-children list is appended to, never replaced.

Run it once after installing launcher-carrying packages; menus refresh on
next login. COSMIC is the measured-later third mechanism (D-036 addendum).

### `hammunition station show` / `hammunition station set`

The values only you can supply — callsign, grid square, packet node alias. Some
manifests write configuration files templated with them: `linbpq` needs a node
callsign, AX.25 needs one in `/etc/ax25/axports`, Direwolf needs one in its
own configuration.

```
hammunition station set --callsign M0ABC --grid-square IO91wm
hammunition station show
```

Saved to `$XDG_CONFIG_HOME/hammunition/station.yml`, mode 0600, resolved
owner-aware so that running under `sudo` still writes to the invoking user's
home rather than root's.

**A value you have not supplied does not block an install.** The package is
installed and the file that needed the value is reported under *Will NOT
happen*, with the command that would let it be written. That is deliberate
(**D-035**): a nineteen-package profile refusing entirely because one file
needed a callsign got an operator nowhere.

**Nothing is invented.** There is no default callsign and no placeholder,
because a configuration file written with a made-up callsign would transmit
it. An interactive run offers to prompt for what the request actually needs;
`--yes`, a pipe, or a value that is already known all skip the question.

## Launchers and menu entries

A manifest may declare `launchers` — programs that need a working directory,
a service-endpoint argument, or that simply have no `.desktop` of their own
(Java jars, run-in-place trees; 14 units measured). For each one the run
generates two per-user artifacts, unprivileged, printed like every other
step: a wrapper script in `~/.local/bin` with `{endpoint:NAME}` substituted
from the manifest's `service_endpoints` (the repointable-backend rule — a
dead upstream is fixed by editing the catalog, not launchers), and a desktop
entry in `~/.local/share/applications` whose `Categories=` are mapped from
the manifest's own category tags, `HamRadio` first (**D-036**). Entries
carry `X-Hammunition-Package` so later tooling can find its own work. The
curated per-DE submenu layer (Xfce `.menu`, GNOME app-folders, COSMIC) is
D-036's next, measured step.

## How a run is ordered

Resolution is a distinct phase that finishes before anything is executed
(**D-016**). In order:

1. **Detect the target** from `/etc/os-release`. A non-Debian-family system is
   refused here; there is no shim that makes it appear to work.
2. **Expand** the requested names — profiles into their packages, and any
   `depends` that names another manifest.
3. **Order** by `after`, which is sequencing rather than dependency. A cycle is
   reported; it does not hang.
4. **Resolve** each manifest against `(distro, version, arch)`. No matching
   install block means this target is genuinely unsupported for that package.
5. **Check what this engine can actually do** — see below.
6. **Ask apt once**, about every distro package the whole transaction needs —
   the manifests' own packages, their `depends`, and the `build_depends` of any
   source build, together. This is how a stale build dependency is caught before
   a compiler is installed rather than after `./configure` fails: glfer's
   `build_depends` name `fftw2` and `libgtk2.0-dev`, two of the four AHRL
   dependency lines **D-016** records as suspected-stale, and nothing in AHRL
   ever asked apt whether they still exist.
7. **Print the plan**, in full, for every run and not only for `--dry-run`.
8. **Present any consent gate**, then confirm, then execute.

If anything in steps 2–6 fails, **every** failure is printed together and
nothing is changed. Reporting only the first would have the same shape as the
defect this is built against: fix one, re-run, meet the next.

## What it refuses

Each of these is a named refusal with a remedy, never a silent skip. A
capability matrix that reports coverage the engine does not have is the shim
`CLAUDE.md` forbids.

| Situation | What you see |
|---|---|
| A `pipx` install block | the backend named — re-measured to zero users (D-014 amendment) and unwritten |
| A `source` or `git` block whose `build_system` is `custom` | the build system named. No manifest uses it, so it is an unimplemented gap rather than a regression (**D-014**) |
| A `patches` entry with no `unified_diff` | a description alone cannot be applied — building unpatched source would produce a binary the manifest does not describe. (Declared diffs stage and apply with patch(1) since v0.4.0.) |
| A `build_depends` package apt has no candidate for | which name, marked `build_depends`, **before** the toolchain is installed |
| A manifest declaring third-party `apt_repos` | that adding a repository with a pinned key is a disclosed modification of its own |
| A vendor `.deb` whose declared `conflicts_with_repo_package` is installed | the colliding packages by name, with the removal command — a dpkg file collision mid-transaction is the refused alternative |
| A `system_modifications` kind other than `group_membership` | the kind, by name |
| A package whose status is `broken` or `retired` | the recorded reason, verdict and date |
| A dependency apt has no candidate for | which name, and whether it came from `install` or `depends` |
| No apt package lists at all | that this is a stale-lists problem, with `--refresh` as the remedy |
| A group membership with no identifiable operator | that `--user` is needed |

The dependency check is the one that earns its keep. **D-016** names four AHRL
dependency lines suspected of failing silently for years — `fftw2` (FFTW
version 2), `libgtk2.0-dev` (EOL), `python3-tksnack`, and an OCaml binding
fldigi does not use. The only reason nobody knows is that nothing ever asked
apt. This asks.

## Privilege

`requires_root` is a property of each command, not of the run. Unprivileged
commands stay unprivileged, `sudo` is added in exactly one place, and
resolution never asks for it at all — so `--dry-run` works as a normal user.

Three kinds of privileged command exist today: `apt-get`, `gpasswd --add` for a
manifest's declared `group_membership`, and the final install step of a source
build (`make install`, `cmake --install`). Each is printed before it runs and
recorded in the transaction log.

**A source build compiles as the operator, not as root.** Only the install into
`/usr/local` is escalated. A build run wholly as root would leave a tree of
root-owned object files in the operator's own cache for no benefit.

## How a source build works

A `source` install block becomes six steps, all of them printed before any of
them happens.

```
  # Install 3 package(s) with apt
  $ sudo env DEBIAN_FRONTEND=noninteractive apt-get install --yes -- fftw2 libgdk-pixbuf-2.0-dev libgtk2.0-dev
  # Download and verify the glfer source archive
  $ [fetch] https://www.qsl.net/in3otd/glfer-0.4.2.tar.gz -> ~/.cache/hammunition/artifacts/06aad6fa…-glfer-0.4.2.tar.gz (sha256 verified)
  # Unpack the glfer source
  $ [extract] ~/.cache/hammunition/artifacts/06aad6fa…-glfer-0.4.2.tar.gz -> ~/.cache/hammunition/build/glfer-06aad6fa/src
  # Configure glfer
  $ cd ~/.cache/hammunition/build/glfer-06aad6fa/src && CFLAGS='-Wno-incompatible-pointer-types …' ./configure --prefix=/usr/local
  # Compile glfer
  $ cd ~/.cache/hammunition/build/glfer-06aad6fa/src && CFLAGS='…' make -j 8
  # Install glfer into /usr/local
  $ cd ~/.cache/hammunition/build/glfer-06aad6fa/src && sudo make install
```

A `[fetch]` or `[extract]` line is a step the engine performs **itself**, in
process, rather than a command you could paste — which is why it is bracketed
rather than rendered as a shell line. Both could have been shelled out to
`sha256sum` and `tar`, and both are safer here: the file handle and the
extraction filter are ours, so a redirect to `file://` and an archive member
named `../../etc/cron.d/x` are refused by construction rather than by whatever
the local tool happens to default to.

Everything else is an ordinary `Command` with a working directory, rendered as a
leading `cd` so the line stays copy-pasteable and an operator reproducing the
plan by hand runs it in the right place.

**Where things go.** Verified archives land in
`$XDG_CACHE_HOME/hammunition/artifacts`, named by their own sha256 — the path
encodes the expectation, so a file at that path can only be content that matched
it. Build trees go in `$XDG_CACHE_HOME/hammunition/build`. Both are caches in
the real sense: deleting them costs a re-download and a rebuild and nothing else.
Under `sudo` they follow the operator, not root, for the same reason the
transaction log does.

**Verification is not optional and cannot be skipped.** The schema requires
`sha256` on every remote artifact, so an unverified download cannot be expressed
in the catalog; the fetcher streams to a temporary file, hashes as it writes, and
moves the result into place only on a match. A mismatch deletes the download and
stops the run. A cached artifact is re-hashed on every use rather than trusted
for having been verified once.

Signature verification is **not** implemented. `signature_url` and
`signing_key_fingerprint` are carried in the catalog and are not checked, so an
artifact declaring them is digest-pinned rather than signed, and the plan says so.

**Build systems:** `cmake`, `autotools`, `qmake` and `make`, which is what the
catalog uses (6 / 2 / 2 / 2). `custom` is a measured zero and is refused by name
(**D-014**).

## How a prebuilt binary is installed

Eight units in the dispositions wait on this and nothing else — QtTermTCP,
QtSoundModem and Pi-APRS from D-008's packet core, GARIM, ARDOPGUI, AntScope2,
GridTracker2, and `sdrangel` on the five targets that do not package it.

Four formats, and the differences are the design:

| Format | What happens |
|---|---|
| `deb` | Fetched, verified, then **`apt-get install ./file.deb`** |
| `tarball`, `zip` | Fetched, verified, unpacked, and the files named in `binaries` installed |
| `executable` | Fetched, verified, installed under the one name `binaries` gives it |
| `appimage` | **Refused by name.** Post-1.0 per `docs/SCOPE.md` |

**A `.deb` goes through apt, never `dpkg -i`.** apt resolves the package's
dependencies; dpkg installs it and leaves them broken, which is the classic way
a vendor package wedges a machine. It also means the result is an ordinary
installed package apt knows about, so removing it later is `apt remove` rather
than archaeology. If apt refuses — usually a `.deb` built for a different
release — that is the correct outcome and the transaction stops there.

**Nothing here is unverified.** `sha256` is mandatory in the schema and the
fetcher refuses a mismatch, leaving nothing usable behind. That matters more
than for a source build, because nobody is going to read a `.deb`.

**An archive naming no `binaries` is refused at plan time**, because unpacking
it would leave a directory in a cache and install nothing while reporting
success. The unpack directory is keyed by the artifact's digest, so a vendor
who republishes under the same URL does not get their new files layered over
the old ones.

## How a git build works

A `git` block builds the same way once the tree is there; only how it *arrives*
differs, and so does the question that has to be answered about it.

```
  # Clear any previous ais-catcher checkout
  $ [prepare] ~/.cache/hammunition/build/ais-catcher-v0.70/src (removed if present, then recreated)
  # Start an empty repository for ais-catcher
  $ git init --quiet ~/.cache/hammunition/build/ais-catcher-v0.70/src
  # Point it at https://github.com/jvde-github/AIS-catcher
  $ git -C … remote add origin https://github.com/jvde-github/AIS-catcher
  # Fetch ais-catcher at v0.70
  $ git -C … fetch --depth 1 origin v0.70
  # Check out v0.70
  $ git -C … checkout --quiet FETCH_HEAD
  # Confirm ais-catcher is at the pinned revision
  $ [verify-pin] git rev-parse HEAD in … must be v0.70
```

**The archive backend asks *are these the right bytes*; this one asks *is this
the right revision*.** A sha256 answers the first. Nothing about a successful
clone answers the second: `git` can exit 0 having handed over a different commit
than the catalog was written against — a re-cut tag, a moved branch, a server
that ignored what was asked for. So the pin is **checked after the checkout and
before the build** (**D-031**). A commit pin must match exactly or the run stops;
a tag has nothing to compare against, so the revision it resolved to is recorded
instead — which is the raw material of the pin database, because the day a tag is
re-cut the log says what it used to be.

**A moving ref cannot be expressed.** The schema refuses `master`, `main`,
`HEAD`, `trunk` and `develop`, and a bare commit SHA requires a `pin_review`
naming who reviewed it, when, and why that commit (**D-024**). A tag carries an
upstream signal that somebody thought a revision worth naming; a SHA carries
none, so pinning one moves a judgement upstream stopped making onto us, and it is
recorded beside the pin rather than implied by it.

The fetch is shallow and by ref, so a pinned commit costs one object walk rather
than a project's whole history.

## Consent gates

A gated profile presents its disclosure before anything runs. `--yes` is
accepted by the call and deliberately never read: a gate a convenience flag
walks through is not a gate (**D-021**). In a script, set the profile's own
`HAMMUNITION_ACCEPT_*` variable to `1`. With no terminal and no variable, the
run stops — silence is not consent, and "nobody was asked" is recorded
differently from "somebody said no".

## Exit codes

| Code | Meaning |
|---|---|
| 0 | Success — every command ran **and** its effect was confirmed afterwards |
| 1 | A command failed while running, a completed command's effect could not be confirmed (D-031), or the system is unsupported |
| 2 | The transaction could not be planned — every blocker is printed |
| 3 | A consent gate was declined, or could not be presented |

## What is recorded

Every run appends to the transaction log — format in
`docs/reference/transaction-log.md`. Each command is logged **before** it runs
and its outcome after, so a run killed mid-`apt-get` leaves a record that the
command was started. That is the state an operator needs to see, and a log
written only on success would hide it.

The log is itself a modification, so the plan discloses it: a **Records**
section names the destination path, and under `sudo` — where root writes into
the operator's home — it says the log and the directories created for it are
handed back to that operator (`chown`). The path shown is the path the run
uses, so if the operator cannot be resolved and it falls back to root's home,
the plan says so rather than redirecting in silence.

**A command exiting 0 is not recorded as an effect.** `apt-get install` can
exit 0 having installed nothing a held or broken package quietly refused, and
`gpasswd` exits 0 whether or not the membership took (**D-031**). So after every
command has completed the run **re-reads** what it claimed to change — from the
same sources resolution used pre-flight, `apt-cache policy` for a package and
the group database for a membership — and records the confirmed state, not the
exit code, in `transaction_end`. That is the record `uninstall` will trust, and
it must not say "installed" on the strength of a return value. A completed run
whose effect cannot be confirmed prints exactly what did not take and exits 1;
its log entry carries `verified: false`.

`hammunition status` reads that log back and reports how the **most recent
transaction ended** — completed, failed after N commands, or interrupted with
no ending recorded — never just what it set out to do, and for a completed run
whether its effects were **confirmed afterwards** or came back unverified. A run
that died partway is not reported as if it finished.

Hammunition does not roll back. It tells you what it did (**D-004**). On a
failure the run stops at that command, and the count that completed is printed
along with the log's location.

## What is not here yet

`uninstall` covers the apt backend only. Reversing a source, git or binary
install — files placed by `make install`, wrappers, udev rules — is refused
by name; what those installs wrote is in the transaction log, which is the
part that could not have been added retroactively.
