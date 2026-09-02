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

### 7. A JavaScript build — `openhamclock` — **CLOSED 2026-09-02** (D-037)

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
| Node floor | Vite 6.4 declares `^18 \|\| ^20 \|\| >=22`, and that number is wrong — see below. **Measured 20.19.** Debian 13 and Parrot ship 20.19, Ubuntu 26.04 22.22, Kali 24.19; **Ubuntu 24.04 ships 18.19 and is refused.** |

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

The shape that fell out is a `node` backend (`src/hammunition/backends/node.py`)
rather than a build system inside the source backend, because none of the
source backend's shape applies — no prefix, no `make install`, no `binaries`
list. `npm ci` → `npm run build` → `npm prune --omit=dev`, every step with
scripts ignored, then the pruned tree copies per-user to
`$XDG_DATA_HOME/hammunition/node/<name>` with `.env` preserved across
rebuilds, and a wrapper on `~/.local/bin` runs `node server.js` from it with
`HOST=127.0.0.1`. The launcher composes that wrapper through a `{node}`
placeholder and opens the browser. What it introduces that no other build
does is **registry access at build time**: 728 tarballs from
`registry.npmjs.org`, verified by the lock file rather than by a manifest
`sha256` each. **Q-016 closed on 2026-09-02 as D-037**: acceptable when
disclosed as a requirement and refused when Node is absent or too old. The
backend does three things the measurement did not: it checks the lock file
really carries an `integrity` for every resolved package before `npm ci`
runs (the property the whole argument rests on, so it is checked rather than
assumed); it gates at plan time on `apt-cache policy`'s `nodejs` version
against the manifest's `node_min_version`, preferring the installed version
over the candidate; and it prints the requirement and the registry fetch in
the plan before anything runs. Carried in `catalog/packages/openhamclock.yaml`
at v26.7.0.

Three more things carrying it found, which the measurement above did not.
Each is the D-025 shape again — a claim re-verified when it became decisive:

- **Point 3's premise was false: the code ignores `HOST` altogether.**
  `server/config.js` reads it and the startup banner prints it, and
  `server.js:364` then calls `app.listen(PORT, '0.0.0.0', ...)` regardless.
  The first real install through the engine, with the wrapper's
  `HOST=127.0.0.1` in force, measured `00000000:0BB9` in `/proc/net/tcp` —
  every interface — and that is the only reason it was caught. Upstream main
  has the same line at 2026-09-02. So `NodeInstall` gained `patches`, the
  same `Patch` model the source backend takes, applied after extraction and
  before the lock-file check; the manifest carries a one-token diff
  (`'0.0.0.0'` → `HOST`) with its evidence in the description, and `patch`
  joins the build dependencies. Re-measured after the patch: tcp4 nothing,
  tcp6 `[::1]:3001` only.
- **`.env` overrides the wrapper, and `localhost` is `::1`.** `config.js`
  writes every key of the `.env` it generates into `process.env` *over* the
  environment, so the operator's file wins and the wrapper's `HOST` is a
  default, not a guarantee. The template says `HOST=localhost`, which Node 20
  binds as `::1` only — `curl http://127.0.0.1:3001` gets nothing and
  `http://localhost:3001` gets 200 — so the launcher opens `localhost`, where
  a browser tries both families. One edit widens the bind and that is the
  operator's to make; `API_WRITE_KEY` is the thing to set alongside it. UDP
  2237 (WSJT-X) binds `0.0.0.0` whatever `HOST` says; only
  `WSJTX_ENABLED=false` stops it.
- **The Node floor is 20.19, not 18, and it is a minor.** On the Ubuntu 24.04
  VM (Node 18.19.1) the build succeeds end to end and the server dies at its
  first start: `server/routes/satellites.js` does `require('axios-cookiejar-support')`,
  version 6.0.5 of which is `"type": "module"`, and `require()` of an ES module
  is Node 20.19+ (`ERR_REQUIRE_ESM` below it). Vite's `engines` range
  described the bundler, not the server, and `package.json` declares none.
  `node_min_major: 18` became `node_min_version: "20.19"` — a `MAJOR.MINOR`
  string, because a major-only floor would admit 20.18 — and the plan-time
  gate compares both numbers. Ubuntu 24.04 is now refused at plan time by
  name, which is exactly the outcome D-037 asks for: the requirement is
  disclosed, and Node is not fetched to meet it.

All three are in the manifest's `known_problems` and the D-037 amendment.
