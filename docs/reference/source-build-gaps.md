# What the source backend still cannot build, and which unit proves it

**D-014** says a backend is justified by measurement and every backend names
the unit requiring it. This applies the same rule one level down, to *features*
of the source and git backends: each gap below is named by a real unit that hits
it, and each was found by attempting the build rather than by reading the code.

Measured **2026-08-28** in Debian 13 containers unless stated otherwise.

---

## Closed this round

| Gap | Unit that proved it | Resolution |
|---|---|---|
| Build system with no install rule | `coil64`, `cwwav`, `ardopcf` | `provides_install_target: false` installs the declared `binaries` instead. |
| Qt6 projects | `qlog` | `qmake6` is its own build system. Debian 13 with only `qt6-base-dev` has no `/usr/bin/qmake`. |
| Compiler-flag-fragile builds | `cwwav`, `ardopcf`, `glfer` | `compiler_flags` — already present, now exercised by three units. |

## Open

### 1. A custom `make` target — `linrad` — **CLOSED 2026-08-30**

`build_args` now reach `make` on the autotools path too; linrad's
`make xlinrad64` built and installed on the Parrot VM.

The autotools path runs `make` with no target. Linrad's build is
`./configure` followed by `make xlinrad64`; a bare `make` prints usage and
stops. Nothing in the schema can say which target to build for an autotools
project. (`build_args` exists on `SourceInstall` but is only passed by the
`make` build system, which has no configure step.)

### 2. In-tree patching — `linrad`, and nearly `Fl_MoxGen` — **CLOSED 2026-08-30**

Declared unified diffs stage and apply with patch(1) before configure;
linrad ships with its six baked-in -Werror occurrences patched out, VM-built.
A patch with only a description is still refused by name.

`patches` is in the schema and is a **measured zero**: the backend refuses it
by name rather than implementing it speculatively. Linrad ends that.

Its `Makefile` hardcodes `-Werror` inside its own `FLAGS` variable, and on
Debian 13 the build stops at `hid.c:1340` with
`error: 'strncpy' specified bound depends on the length of the source argument
[-Werror=stringop-truncation]`. Passing `CFLAGS` does not reach it — measured,
`make xlinrad64 CFLAGS="-Wno-stringop-truncation"` still fails at the same
line — because the Makefile builds its own flag string and never consults
`CFLAGS`. Removing `-Werror` from the Makefile builds cleanly and produces
`xlinrad64`.

So our existing `compiler_flags` mechanism, which sets `CFLAGS`/`CXXFLAGS` in
the environment, **cannot fix a build whose Makefile ignores them**. That is
the first thing a patch feature would exist for. AHRL independently patches
`gsmc`'s Makefile in place for what looks like the same reason — and that turned
out to be avoidable: at gsmc's own tag v1.2.1 the build is clean with no flags
at all, and AHRL only needs the patch because it builds an unversioned `master`
snapshot instead.

`Fl_MoxGen` is the same illness with a cure. Its rule is
`@$(CC) -c -o write_pdf.o write_pdf.c`, which never mentions `$(CFLAGS)` —
but it does mention `$(CC)`, so `build_args: ["CC=cc -Wno-implicit-function-declaration"]`
reaches it. That works and is expressible today. It is worth recording as the
cheaper answer to try first: a Makefile that ignores `CFLAGS` may still honour
an override of whatever variable it *does* use, and only when nothing is
overridable does a patch become necessary. Linrad's `-Werror` is baked into a
literal flag string with no variable to override, which is why it is the one
that forces the feature.

### 3. `autoreconf` before `configure` — `kalibrate-rtl` (and gsmc-from-git) — **CLOSED 2026-08-30**

`autoreconf: true` on a source/git block runs `autoreconf -fi` before
configure and the planner injects autoconf/automake/libtool. kalibrate-rtl
was the first manifest to actually hit the gap — the Parrot grind failed it
at './configure is not on PATH'.

Not a gap that blocks anything today, because there is a way round it, but the
shape is worth recording.

Git does not preserve timestamps. A checkout of an autotools project therefore
has `configure` and `aclocal.m4` looking older than `configure.ac`, so make
enters maintainer mode and tries to regenerate them — which needs the exact
autotools version the project was released with and fails as
`Makefile:357: aclocal.m4 Error 127` when it is absent. `autoreconf -fi` first
fixes it, and this backend does not run one.

**The tarball of the same tag builds cleanly**, because its timestamps are
uniform and maintainer mode never triggers. So `gsmc` is a `source` manifest
pointing at the tag's archive rather than a `git` manifest pointing at the
tag — and the rule that produces is a useful one: for an autotools project,
prefer the tarball; the git route needs a bootstrap step nothing here performs.

### 4. Architecture-dependent `configure` arguments — `linrad` — **CLOSED 2026-08-30**

Arch-gated install blocks carry per-arch `build_args`; linrad's manifest
gates x86_64 and leaves ARM unmeasured rather than guessed.

Linrad's `configure` looks for `libX11.so` and `libasound.so` at paths that do
not match Debian's multiarch layout, and **says so without failing**:

```
Not present: libX11.so (64bit) or headers  (./configure --with-x11-64)
Not present: libasound.so (64bit)  (./configure --with-ALSA-64)
...
Normal End. You can now run make
```

`configure` exits 0 and the compile line then carries `-DHAVE_X11=0`. The
result is a Linrad with **no graphical interface and no sound**, built
successfully. AHRL runs a bare `./configure` here and checks no exit status, so
this is what its users get, silently.

Passing `--with-x11-64=/usr/lib/x86_64-linux-gnu/libX11.so` and the ALSA
equivalent fixes detection — and those paths carry the architecture triplet, so
expressing them needs either per-arch install blocks or a substitution the
schema does not have.

### 5. No build step at all — `wordsworth` — **CLOSED 2026-08-30**

The binary backend's tarball format installs the two scripts; reading the
code softened the 'data file' half — the word lists are embedded, the txt is
sample input. VM-verified emitting practice words.

`wordsworth_0.3.tar.gz` contains two Perl scripts, a README, a COPYING and a
5000-word list. There is nothing to compile and no Makefile, so the `make`
build system — the only one that skips `configure` — fails immediately with
"No targets specified and no makefile found".

Two things are missing, not one. A build system that builds nothing, and a way
to install a **data file**: `binaries` puts executables in `<prefix>/bin` and
`QSO_Words_5000.txt` is not one. AHRL copies the two scripts to
`/usr/local/bin` and leaves the word list in the source tree.

### 6. Installing a tree, not a binary — `mshv` — **CLOSED 2026-08-30**

`install_tree` lands the whole build under
`/usr/local/share/hammunition/<name>`; MSHV built and runs from its tree via
the generated launcher, after two build-deps AHRL only had by install-order
accident (libpulse-dev, libfftw3-dev) were measured in.

`provides_install_target: false` copies declared binaries into the prefix. MSHV
reads settings, resources and logs from directories beside its executable in
`bin/`, so copying the executable alone produces a program that starts and
cannot find its own data. It needs the tree installed somewhere and a launcher
that runs it from there — which is M3's launcher-generation work, and MSHV is
one of its 14 units.

### 7. A JavaScript build — `openhamclock` — **MEASURED 2026-09-01, awaiting Q-016**

**This one blocks a decision that has already been made.** Q-006 resolved on
2026-08-29 to default to `accius/openhamclock`, on the strength of its activity
and community — 456 stars, head `47d4ac14ccc4` dated 2026-08-27, MIT by its
LICENSE file even though GitHub's licence field reports NOASSERTION.

Nobody checked how it builds. It is not the C++ program the original HamClock
was: at tag v26.6.0 the tree carries `package.json`, `package-lock.json`,
`vite.config.mjs`, `server.js`, an `electron/` directory, a `Dockerfile` and a
`wasm-build/`. It is a Node and Vite web application, and its latest release
publishes no binary assets.

So it needs `npm`, which is not a backend this project has, has never measured
a need for, and would be the first one justified by a single unit. Until then
`hamclock-next` is what the `propagation` profile ships — a cmake build we can
actually perform — and the profile says why rather than silently substituting.

This is the D-018 and D-025 shape a third time: a decision resting on a
property nobody verified, which only became decisive when someone tried to act
on it. Activity and community size were measured correctly. Buildability was
not measured at all.

**Measured 2026-09-01, on the Debian 13 VM, tag v26.7.0** (tarball sha256
`0c179ab1cf1e42bddda53933fc0417d18c5b3ff5c09ae9ffa747714670d2c943`), using
Debian's own `nodejs` 20.19.2 and `npm` 9.2.0 — nothing from NodeSource:

| Step | Result |
|---|---|
| `npm ci --ignore-scripts --no-audit --no-fund` | 728 packages, **8 s**, 534 MB. Every one is pinned by a sha512 `integrity` field in `package-lock.json` (797 entries, one per `resolved` URL), and the lock file lives inside the sha256-pinned tarball — so the whole dependency closure is transitively verified from one manifest hash. |
| `npm run build --ignore-scripts` | Vite 6.4.3 build, **6 s**, `dist/` 11 MB. |
| `npm prune --omit=dev --ignore-scripts` | Runtime tree **142 MB, 200 packages**. |
| `node server.js` | HTTP 200 on `:3001` three seconds after start, serving the built dashboard. |
| Native modules | **None** — no `.node` files, no `binding.gyp` — so `--ignore-scripts` (no third-party lifecycle code ever runs) costs nothing. |
| Node floor | Vite 6.4 declares `^18 \|\| ^20 \|\| >=22`; every target's archive Node qualifies: Ubuntu 24.04 ships 18.19, Debian 13 and Parrot 20.19, Ubuntu 26.04 22.22, Kali 24.19. |

Three properties the manifest and any backend must handle, all measured:

1. **`prebuild` fetches from a moving tag.** `scripts/fetch-wasm.js` downloads
   P.533 WASM from the `wasm-latest` GitHub release with a checksum file *from
   the same release* — self-attested, not a pin. It exits 0 and skips when it
   cannot, and the server then uses its built-in propagation model ("Standalone
   mode"). `npm run build --ignore-scripts` suppresses the pre-script, and the
   build above ran without it. A pinned WASM could be carried later as a
   verified artefact if the P.533 model matters to an operator.
2. **It writes into its own directory.** First start creates `.env` from
   `.env.example` beside `server.js`, and wants a station callsign and
   locator there (D-035's values). So it installs per-user, the way venv units
   and `mshv`'s tree do, never under `/opt` or `/usr/local`.
3. **The code's default bind is `0.0.0.0`.** `server/config.js` falls back to
   all interfaces when `HOST` is unset (`.env.example` says `localhost`, so a
   generated `.env` fixes it); it also opens a WSJT-X UDP listener on
   `0.0.0.0:2237`. A launcher must set `HOST=127.0.0.1` — on a machine that
   also holds security tooling, a dashboard listening on every interface is not
   an acceptable default.

The shape that falls out is a `node` build system in the source backend —
`npm ci` → `npm run build` → `npm prune --omit=dev`, every step with scripts
ignored — installing the tree per-user with a launcher that runs `node
server.js` bound to loopback and opens the browser. What it introduces that no
current build does is **registry access at build time**: 728 tarballs from
`registry.npmjs.org`, verified by the lock file rather than by a manifest
`sha256` each. Whether that trade is acceptable on this project's security
posture is **Q-016**, the maintainer's call, and it is not implemented here.

### 8. Python run in place, with a data tree — `js8spotter` — **CLOSED 2026-08-30** (supersdr moved to #9)

`install_tree` plus a generated launcher; js8spotter 1.20 installed and
launches from its tree on the Parrot VM.

Not a build problem. These are programs that are never installed anywhere:
they run from the directory they were unpacked into, because they read fonts,
databases and configuration from paths relative to themselves.

`supersdr` at tag v3.14 is `supersdr.py` beside `eibi.csv`, two TTF fonts, two
images and two vendored Python packages, with no `setup.py`, no
`requirements.txt` and no install rule. `js8spotter` and `mshv` have the same
shape. `provides_install_target: false` does not help, because what has to be
installed is a tree and what `binaries` installs is an executable.

Two things are needed together and neither exists: installing a directory to a
known location, and generating a launcher that runs the program from it. M3
already counts launcher generation at 14 units; this is what those 14 units
actually need.

Q-007 resolved on 2026-08-29 to carry `supersdr`. It cannot be written yet for
this reason and not for the licence one.

---

### 9. A venv beside a payload tree — `radiosonde_auto_rx` and `supersdr` — **CLOSED 2026-08-30**

The venv method gained a verified `payload` archive (tree-installed under
the shared prefix), an optional `payload_build_script` run inside the
verified tree (auto_rx's C demodulators), and a `{venv}` launcher token
joining the per-operator venv to the shared tree. Both units carry
manifests; VM verification queued behind the campaign grind.

The REVIVE table said "standard venv install from the pinned upstream tag",
and the venv backend now exists — but reading upstream (2026-08-30) shows the
estimate was short: `auto_rx` is a git clone whose `build.sh` compiles a set
of C demodulators in-tree, plus a venv for `requirements.txt`, plus a
`station.cfg` templated from operator values, and it runs in place from the
clone. That is the git backend with a `custom` build step (a measured zero
until now), the venv backend, config templating and launcher generation
composed on one unit. It stays a documented gap rather than getting a
manifest that pretends any single backend covers it.

`supersdr` joined this class on 2026-08-30, from the other direction: its
data tree installs fine (`install_tree` closed #8 the same day), but its
audio dependency does not exist as a Debian package at all —
`python3-sounddevice` has no candidate on Debian 13, measured by the
engine's own D-016 refusal on the first install attempt. Run-in-place with
system python cannot satisfy it; a hash-pinned venv can, but then the app's
tree and the venv are two halves one install block cannot yet express. Two
units now demand the same composition, which is the D-014 bar for building
it.

## What this list is for

Each entry is a feature request with its evidence attached, so that when one is
built the argument for its shape is already written down and the unit to test
it against is already named. Nothing here should be implemented because it
sounds useful; it should be implemented because `linrad` or `mshv` needs it and
the manifest is waiting.
