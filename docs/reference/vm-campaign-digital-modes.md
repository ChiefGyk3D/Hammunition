# VM campaign — digital-modes profile, Parrot and Debian 13

Second campaign of the automated ladder (`scripts/vm_campaign.py`), run
2026-08-30 on `ParrotOS_Dev` and `debian13_dev`. First passes scored 15/21
and 17/21; every failure was diagnosed, fixed or verdict-filed, and re-run.
**Final standing: 20 of 21 units verified installing on both targets; the
21st carries a measured cross-target verdict.**

## What the failures were, and what each one taught

| Unit | Diagnosis | Resolution |
|---|---|---|
| `fldigi` | The pinned URL had been **constructed from AHRL's bundled filename and never fetched** — it 404s, and upstream had moved on. The fetch-verified 4.2.13 then exposed a missing `libpng-dev` build-dep. | Bumped to 4.2.13, dep added. **Confirmed on Parrot (51s) and Debian (71s).** |
| `js8call` | Same never-fetched-URL shape — and upstream (JS8Call-improved) is at **3.0.3 with no source tarballs at all**; Linux release assets are AppImages. | Converted to a pinned git build of `v3.0.3`. **Confirmed on Parrot (103s) and Debian (119s).** |
| `wsjtx` | Same shape again: the GitHub asset URL never existed. Upstream v3.0.2 publishes no Linux source asset. Separately, AHRL's `libboost-all-dev` drags an OpenMPI/hwloc chain that conflicts outright on a backports-enabled Parrot desktop. | Converted to a pinned git build of `v3.0.2` with Boost narrowed to the three pieces CMake wants. **Confirmed on Parrot (116s) and Debian (142s).** |
| `wsjtx-improved` | The flat SF URL was never real either; 3.2.0's Linux artifacts are **vendor .debs**. The PLUS deb then failed honestly on both targets: it ships `/usr/share/pixmaps/wsjtx_icon.png` with no `Replaces:`, and the distribution's `wsjtx-data` (a jtdx dependency) owns that file. | **Verdict, not a fix:** cannot coexist with `wsjtx-data`/jtdx until the catalog can declare package conflicts. Recorded in the manifest; the engine's refusal text says what to remove. Tested on both targets, same failure. |
| `glfer`, `xwefax` | **Target finding, not manifest defect** — both installed cleanly on Debian. On a Parrot desktop with backports-updated GNOME libraries, the *base* GTK dev stacks are unresolvable (`gir1.2-atk-1.0` downgrade conflict). | Remedy measured and applied: install the GTK dev packages from `echo-backports`. Both then **confirmed on Parrot** (glfer needs `fftw2`, which survived). Same skew class as the earlier libcurl-dev finding. |

## The pattern worth keeping

Four of six failures were **URLs constructed from AHRL's bundled tarball
names and never fetched** — sha256s of local copies attached to guessed
remote paths, exactly the unverified-claim shape D-018 and D-025 exist for.
The campaign machine is what caught them, and the fix in every case began
with fetching reality: two upstreams had stopped publishing source archives
entirely since AHRL v27 shipped.

**Parrot image note for the runbook:** a Parrot Security desktop with
backports-updated runtime libraries cannot install several *base* -dev
chains (libcurl, GTK). `apt-get install -t echo-backports <dev packages>`
is the remedy, and any source build on stock Parrot may need it. Worth
revisiting whether the engine should learn a per-target release hint;
recorded here as measurement first.
