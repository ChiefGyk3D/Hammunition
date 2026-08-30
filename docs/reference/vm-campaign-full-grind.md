# VM campaign — the full grind, three targets

The whole ungated profile set (`scripts/vm_campaign.py`), run 2026-08-30 on
Parrot, Debian 13 and Kali in parallel, then retried per-fix until every
failure was either converted or filed as a verdict.

## Standing after retries

| Target | First pass | After retries |
|---|---|---|
| Parrot | 122 / 128 | **128 of 128 installable units confirmed** (code/codium correctly refused: third-party apt repos are unimplemented) |
| Debian 13 | 102 / 107 | **105 of 107 confirmed** (same two honest refusals) |
| Kali | 136 / 147 | **143 of 147 confirmed** (four refusals: code, codium, and cqrlog/cwdaemon which have no Kali candidates — archive facts) |

wsjtx-improved remains the one declared-conflict verdict everywhere jtdx is
installed, refused at plan time by design.

## What the grind taught, in fix order

- **cmake children inherited an undefined cwd** — rtlsdr-airband's version
  script ran `git describe` from wherever the engine started. Pinned to the
  source tree; shallow tag fetches now recreate the tag so describe answers
  with the pin.
- **cmake caches outlive the source tree** — a fixed source kept failing on
  the previous source's cached try_run verdict. `--fresh` on every
  configure; idempotent re-runs need fresh configures too.
- **kalibrate-rtl had no configure to run** — `autoreconf: true` closes
  source-build-gaps #3, with the planner injecting the autotools toolchain.
- **Kali's GCC 15 defaults to C23** — `void f()` now means zero parameters,
  which is AHRL's original ardopcf error a compiler generation later, and
  gsmc's and qtsoundmodem's too. `-std=gnu17` pins the dialect old C was
  written in; expect this class on every rolling target from here on.
- **liquid-dsp 1.8 broke dumphfdl's version check twice over** — its header
  needs stdarg.h under GCC 15's tightened includes, and it byte-packs the
  version number the check reads as decimal. The catalog's second real
  patch, two hunks, measured on Kali where 1.8.2 ships while Debian's older
  liquid passes untouched.
- **sdrpp had transcribed libairspyhf-dev out of AHRL's dep list** — the
  first real Debian build put it back.
- **The hybrid units went three-for-three** — supersdr and
  radiosonde-auto-rx installed and confirmed on every target, radiosonde's
  demodulators compiled by upstream's own script run from its own
  directory, its launcher demanding station.cfg exactly as documented.

Raw per-target tables live in the campaign outputs; this file records the
conclusions and the fixes, per the runbook's recording rule.
