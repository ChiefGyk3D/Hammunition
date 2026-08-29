# Session log — overnight round 6, 2026-08-28 → 29

One instruction: *keep grinding through those manifests, do not stop.*
Twenty-two commits, all pushed. The catalog went from **77 manifests to 217**.

Previous round's log is in git history at `f13055b`.

---

## Headline

**The Debian Blend is complete: 152 of 152.** `SCOPE.md` stages 1.0 by
coverage-per-effort and puts the Blend first, as the cheapest coverage with the
best provenance. That stage is done. It stood at 127 covered when the night
started and the last one, `qlog`, is not in any target's archive but Kali's, so
it is built from source.

**Four upstream sites Debian still points at are dead or no longer the
project's**, covering fourteen packages between them, and every one was found
by requesting the URL before publishing it rather than after.

* `w1hkj.com` — the Homepage for five packages — 301-redirects to an unrelated
  site, and the subpaths Debian cites 404. The project is at `w1hkj.org`.
* `xastir.org` has **no DNS record at all**, while the project's `master`
  moved a month ago. Live project, dead website.
* `wa0eir.bcts.info` covers three packages and does not resolve. Neither does
  the second address `twclock`'s own copyright file names.
* `opendigitalradio.org` resolves and answers nothing on either scheme,
  covering five.

A fifth, `quisk`'s, **could not be checked at all** — it is IPv6-only and this
machine has no IPv6 route. That is not the same as gone and the manifest says
which it is. And `mshv`'s download URL was a 404 while its recorded sha256 was
correct: the file fetched from where MSHV actually publishes hashes to exactly
the digest already in the manifest, which is the mandatory-checksum rule
earning its keep in a way it was not designed for.

**Two AHRL claims measured, opposite answers.** AHRL runs `xastir` and
`svxlink-server` early because it believes their packages create groups.
Installed in a container: svxlink-server does create an `svxlink` user and
group and adds it to `dialout` and `audio`; xastir creates nothing and its
binary is already 0755. Same source, same kind of claim. Measure each.

**ardop is revived, and AHRL's error was not the error.** Its recorded
failure does not happen on Debian 13; the real one is three `-Wint-conversion`
errors GCC 14 promoted. One flag builds it — and that flag silences a genuine
bug in the CM108 push-to-talk path, which the manifest says out loud rather
than reporting a clean build.

**The qmake path had never worked, for either unit that uses it.** Both
`MSHV` and `Coil64` ship a `.pro` with no `INSTALLS`, so the backend's
`make install` step had nothing to run. Found by reading Coil64's project file
before writing its manifest.

---

## What completed

**Catalog: 77 → 217 manifests.** 188 apt, 12 git, 12 source, 4 with a
per-target split, 1 binary. 27 categories, now a controlled vocabulary.

By cluster: Morse and CW (11), logging (8), propagation and antenna (15),
digital modes and NBEMS (14), packet and APRS (11), the SDR layer (19), rig
control and EchoLink (11), the SoapySDR module set completed (6 more, all 12
now), AIS and exam practice and station plumbing (12), the rest of the Blend
(17), the packages our targets disagree about (5), the W1HKJ source suite (5),
ardopcf, coil64, cwwav, xwefax, acarsserv, qlog.

**Engine.**

* `provides_install_target: false` — a build with no install rule installs its
  declared `binaries` instead. The first thing that makes that field mean
  something. The schema refuses it without `binaries`, because otherwise the
  build succeeds and puts nothing on the PATH.
* `qmake6` is its own build system. Debian 13 with only `qt6-base-dev` has no
  `/usr/bin/qmake` at all, and `qt5-qmake` would supply the name with the wrong
  tool.
* `GitInstall` gained `project_file` and `build_args`, which the source path
  had and the git path silently dropped.

**Documentation.**

* `docs/packages/` — 218 generated pages, one per manifest plus an index. The
  layout has called for this since it was written and it did not exist.
* `docs/reference/capability-matrix.md` — every manifest against every target,
  resolution merged with a measured `apt-cache policy` sweep, because
  resolution alone says `apt` for the four targets where `sdrangel` is not.
* `docs/reference/source-build-gaps.md` — what the source backend cannot yet
  build, each gap named by the unit whose build proved it.
* `docs/contributing/manifests.md` — the conventions this round established.
* The REVIVE table in `dispositions.md` now has a verification log beside it.

**Tooling.**

* `scripts/apt-policy-sweep.sh` — what each target's archive offers, for a list
  of names. Its own first result was false and it now fails loudly on a short
  sweep.
* `scripts/gen_package_reference.py` and `scripts/gen_capability_matrix.py`.
* The link checker no longer reports `/etc/bpq32.cfg` as a broken repo path.

---

## Mistakes worth keeping

**Four versions filled in from memory, all four wrong.** `aldo` 0.7.7 for
0.7.8, `morse` 2.5 for 2.6, `morse2ascii` 0.1.4 for 0.2.1, `xdemorse` 3.3 for
3.6.7. Every one would have validated and shipped. The sweep found them in
forty seconds, which is the whole argument for running it first.

**`uhd-soapysdr` was described as the exact opposite of what it does.** It is a
libuhd plugin that presents a dongle to UHD software; I wrote it as a SoapySDR
plugin for USRPs, which is `soapysdr-module-uhd`. Same source package, near
anagram names. Found by reading `apt-cache show` while writing the sibling —
nothing in the schema can tell a fluent description from a true one.

**The arm64 sweep reported "0 offered, 0 absent" and exited 0.** No
qemu-user-static on this machine, so the container never ran. That is a
measurement, and a false one. The script counts its rows now, and the fix was
not emulation but asking the archive: `dpkg --add-architecture arm64` and
`apt-cache policy pkg:arm64` — which has its own trap, since an
`Architecture: all` package has no `:arm64` binary and would read as absent.

**A test regex matched its own documentation.** The capability-matrix
staleness check parsed every `| \`name\` |` row and reported `apt` as a package
the catalog had lost — the legend explaining what `apt` means.

**mypy was red on `main` for four commits and I did not notice**, because I ran
`mypy --strict src/hammunition` and CI runs the bare `mypy --strict`, which
covers `scripts/` and `tests/` too. Two errors in the docs generator, both
real. Fixed in the same round; the lesson is to run the command CI runs, not a
narrower one that passes.

---

## What I could not do

**No hardware was attached to anything.** Unchanged.

**Nothing was installed outside a container**, and the local harness is still
degraded — no `/etc/subuid` ranges. One root command fixes it:

```
sudo usermod --add-subuids 100000-165535 --add-subgids 100000-165535 chiefgyk3d
podman system migrate
```

**`linrad` defeated the source backend, four ways**, and that is written up in
`source-build-gaps.md` rather than bodged. Its Makefile hardcodes `-Werror` and
ignores `CFLAGS`, so patching is the only route and `patches` is still a
refused-by-name zero. Its `configure` also fails to find X11 and ALSA on
Debian's multiarch layout **without failing** — it prints "Not present", then
"Normal End", exits 0, and compiles `-DHAVE_X11=0`. AHRL runs a bare
`./configure` here and checks no exit status, so that is what its users get.

**`mvoice` and `dream` stay blocked** and their reasons are now measured rather
than inherited: `libopendht-dev` and `libqt5webkit5-dev` have no candidate on
Debian 13.

**65 manifests have no `upstream_support` field** — all of them predate this
round. The schema makes it optional and `CLAUDE.md` makes it required, which is
a mismatch worth resolving; filling them in needs verification, not invention.

**Profiles are unchanged at four.** With 217 manifests that is now the largest
usability gap, and `profile-sizing.md` has been waiting on your naming decision
since M1.

---

## Waiting on you

Unchanged from the last round: **Q-006** (which HamClock), **Q-007** (SuperSDR
has no licence — and the recommendation is materially weaker now that its
upstream is measured dormant since 2022-12-31), **Q-008** (does the RF profile
include cellular interception tooling).

New, and cheap to answer: **the starter profile's name and contents**. It is
M1's last open item, everything it would reference now exists, and
`docs/reference/profile-sizing.md` has the sizing ready.
