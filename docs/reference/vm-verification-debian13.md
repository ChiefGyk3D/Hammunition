# VM verification — Debian 13 (campaign 1)

Third rung of the ladder (`docs/contributing/vm-testing.md`); the Parrot
record explains the method. Debian 13 maps onto the `debian-13` CI target,
so these are pass/fail results against current claims.

**Date:** 2026-08-29
**Engine:** commit `cba483e`
**Guest:** Debian GNU/Linux 13 "trixie" (`ID=debian`, `VERSION_ID=13`),
GNOME, x86_64, Python 3.13.5, fully updated at baseline
**Host:** KVM/QEMU domain `debian13_dev`, qcow2, NAT
**Snapshots:** cold `clean-baseline` and cold `station-installed`

## One finding before the ladder could start

**Debian netinst ships no `python3-venv`** — `python3 -m venv` fails with
ensurepip missing, so the engine's git-clone workflow cannot bootstrap at
all. Parrot and Kali both ship it. It is now baseline prep item 7 in the
runbook, baked into this image's `clean-baseline`. The planned `.deb` with a
vendored virtualenv (DESIGN.md §5) is the real answer for end users; until
it exists, getting-started documentation must name this prerequisite.

## Results

| Test | Result |
|---|---|
| `hammunition status` | Detects `ID=debian, version=13, arch=x86_64`, Debian family yes. **223 of 225** resolve — the two Kali-gated manifests correctly absent, matching Parrot. |
| `install station --yes --refresh` | Both commands completed and confirmed. |
| Idempotency — same command again | `Nothing to do.` |
| `uninstall twclock --yes` | Completed and confirmed; dpkg shows `rc`. |
| Reinstall + final verify | All 10 station packages `ii`. |

No engine defects. Same clean transfer as Kali.

## Not yet run

GUI launch checks (this guest runs GNOME — it is also where D-036's
app-folders mechanism gets measured first), hardware passthrough, linbpq
per-target repeat, the M5 re-verification list.
