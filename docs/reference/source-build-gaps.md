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

### 1. A custom `make` target — `linrad`

The autotools path runs `make` with no target. Linrad's build is
`./configure` followed by `make xlinrad64`; a bare `make` prints usage and
stops. Nothing in the schema can say which target to build for an autotools
project. (`build_args` exists on `SourceInstall` but is only passed by the
`make` build system, which has no configure step.)

### 2. In-tree patching — `linrad`; nearly `Fl_MoxGen`, and `gsmc` on AHRL's evidence

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
the first thing a patch feature would exist for, and AHRL independently
patches `gsmc`'s Makefile in place for the same class of reason.

`Fl_MoxGen` is the same illness with a cure. Its rule is
`@$(CC) -c -o write_pdf.o write_pdf.c`, which never mentions `$(CFLAGS)` —
but it does mention `$(CC)`, so `build_args: ["CC=cc -Wno-implicit-function-declaration"]`
reaches it. That works and is expressible today. It is worth recording as the
cheaper answer to try first: a Makefile that ignores `CFLAGS` may still honour
an override of whatever variable it *does* use, and only when nothing is
overridable does a patch become necessary. Linrad's `-Werror` is baked into a
literal flag string with no variable to override, which is why it is the one
that forces the feature.

### 3. Architecture-dependent `configure` arguments — `linrad`

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

### 4. Installing a tree, not a binary — `mshv`

`provides_install_target: false` copies declared binaries into the prefix. MSHV
reads settings, resources and logs from directories beside its executable in
`bin/`, so copying the executable alone produces a program that starts and
cannot find its own data. It needs the tree installed somewhere and a launcher
that runs it from there — which is M3's launcher-generation work, and MSHV is
one of its 14 units.

---

## What this list is for

Each entry is a feature request with its evidence attached, so that when one is
built the argument for its shape is already written down and the unit to test
it against is already named. Nothing here should be implemented because it
sounds useful; it should be implemented because `linrad` or `mshv` needs it and
the manifest is waiting.
