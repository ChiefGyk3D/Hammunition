# VM verification — Kali (campaign 1)

Second target of the VM ladder (`docs/contributing/vm-testing.md`); the
Parrot record explains the method. Kali maps onto the `kali-rolling` CI
target, so these are pass/fail results against current claims.

**Date:** 2026-08-29
**Engine:** commit `4020d73`
**Guest:** Kali GNU/Linux Rolling (`ID=kali`, `VERSION_ID=2026.3`), x86_64,
Python 3.14.6, fully updated at baseline
**Host:** KVM/QEMU domain `Kali_Dev_Box`, qcow2, NAT
**Snapshots:** cold `clean-baseline` and cold `station-installed`, both
taken with the six-item prep checklist applied (the maintainer had applied
the NOPASSWD drop-in and enabled sshd before handoff; sleep-mask, final
updates and the cold shutdown were done over SSH)

## Results

| Test | Result |
|---|---|
| `hammunition status` | Detects `ID=kali, version=2026.3, arch=x86_64`, Debian family yes. **225 of 225 manifests resolve** — the two Kali-gated blocks (`arduino-cli`, `soapysdr-module-plutosdr`) that are deliberate gaps on Parrot light up here, exactly as the capability matrix claims. |
| `install station --yes --refresh` | Both commands completed and confirmed; all 10 packages independently verified `ii`. |
| Idempotency — same command again | `Nothing to do.` |
| `uninstall twclock --yes` | Completed and confirmed; dpkg shows `rc` afterwards. Reinstalled before the checkpoint. |
| `install sdrpp --dry-run` | The Kali-only manifest resolves to a one-command apt install — the first target where `sdrpp` arrives by apt rather than a source build. |

No defects found. The engine work hardened on Parrot (uninstall,
staged root configs, the station prompt) transferred without a change.

## Not yet run

GUI launch checks, hardware passthrough, the linbpq configuration build
(exercised on Parrot; repeating it per-target is M5 work), and the M5
re-verification list.
