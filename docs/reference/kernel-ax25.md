<!--
SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
SPDX-License-Identifier: GPL-3.0-or-later
-->

# Kernel AX.25 — what Linux 7.1 removed, and what the plan does about it

**Measured 2026-09-04.** This page is the evidence behind `requires_kernel`
(**D-041**) and the reason `packet`'s kernel-side members refuse or defer on
some machines and not others.

## What happened upstream

Linux 7.1 removed the amateur-radio networking subsystem in one merge:
`64edfa65062dc4509ba75978116b2f6d392346f5` (2026-04-24, Jakub Kicinski,
"net-deletions"). Gone are `net/ax25`, `net/netrom`, `net/rose`, every
driver in `drivers/net/hamradio` — `mkiss`, `6pack`, `bpqether`, `baycom`,
`scc`, `yam`, `hdlcdrv` — and the uapi headers that went with them.

Two consequences follow for a Debian-family machine:

- **A 7.1 or newer kernel has no `ax25` module and cannot be given one.**
  `socket(AF_AX25, SOCK_SEQPACKET)` fails with *Address family not supported
  by protocol* (errno 97), and `modprobe ax25` reports that the module was
  not found. There is nothing for `kissattach` to attach a TNC to.
- **Debian removed `ax25-tools` from testing on 2026-09-01** (bug #1143282:
  it no longer builds, because `linux/hdlcdrv.h` left with the drivers).
  Kali inherits testing, so Kali's archive lacks the package as well. That
  archive gap is the symptom the Kali campaign reported; the kernel is the
  cause, and it reaches machines whose archives are untouched.

## The out-of-tree module, measured

The removed code did not vanish. The netdev maintainer who removed it
published it the same week as an out-of-tree tree,
<https://github.com/linux-netdev/mod-orphan> (created 2026-04-20,
description: *"Linux networking modules removed from the kernel due to
lack of maintenance and high bug count"*). Read on **2026-09-10**:

| What | Measured |
|---|---|
| Contents | `net/ax25`, `net/netrom`, `net/rose`, `drivers/net/hamradio`, and the other orphans of the same merge — ATM, ISDN/mISDN, CAPI, Bluetooth CMTP, AppleTalk — under one `Kbuild` |
| Build | `make` against `/lib/modules/$(uname -r)/build`; `make install` is `modules_install`. A compatibility header (`include/hamradio_compat.h`) is force-included, which is how it builds against a kernel whose headers no longer know it |
| Licence | no top-level `LICENSE`; every source keeps its kernel SPDX header (`af_ax25.c`: GPL-2.0-or-later, Alan Cox GW4PTS and the G4KLX-era authors) |
| Releases | **no tags, no releases, no README** |
| Head commit | 2026-06-16, Jakub Kicinski, importing AppleTalk. The last AX.25-family change is 2026-06-01, two ROSE fixes by Bernard Pidoux |
| Packaged by | **nobody.** Not in Debian (`packages.debian.org`, all suites), not in Ubuntu, not in the AUR, on the date above |
| Builds against 7.1? | **Partly, and not as shipped.** On the maintainer's laptop (`7.1.1-76070101-generic`, its own `linux-headers`), the tree's `make` fails: `net/rose/rose_in.c` calls `sk_filter_trim_cap` with an argument count 7.1 no longer accepts, and `net/atm/clip.c` includes `net/atmclip.h`, which 7.1 does not ship. With `Kbuild` cut to `net/ax25`, `net/netrom` and `drivers/net/hamradio`, **`ax25.ko`, `netrom.ko` and all ten drivers — `mkiss`, `6pack`, `bpqether`, `baycom_*`, `hdlcdrv`, `scc`, `yam` — compile and link** with `vermagic: 7.1.1-76070101-generic`. Nothing was loaded; no `AF_AX25` socket was opened. A compile is not a test |

So "add it back as a module" is technically possible on a 7.1 machine
with its kernel headers installed, the maintainer of the removal is the one
keeping the code buildable, and on the one machine it was tried the AX.25
half built only after the `Kbuild` was edited to leave ROSE and ATM out. Hammunition still does not build it,
for the reasons **D-041** and **D-045** record: a kernel module is the one
artefact this project has said it will never build, it has to be rebuilt
for every kernel the machine boots (a DKMS wrapper would be *our* packaging
of code nobody else packages, the thing **D-024** exists to refuse), and
`ax25-tools` is leaving the archives regardless — the module would bring
back the sockets and not the tools. **What would change the answer** is a
distribution packaging it, a `-dkms` package in Debian being the obvious
shape: that is the review signal D-024 asks for, and the day it exists the
`requires_kernel` refusal gains a third remedy. Until then the userspace
path below is the packet core (**D-045**).

## What was measured

Every row is `uname -r` plus a look at `/lib/modules/<release>/kernel/net/ax25/`
on the machine named, followed by `socket(AF_AX25, SOCK_SEQPACKET)` from
Python. Machine labels are the dev VMs and the maintainer's laptop; no
hostnames.

| Machine | Kernel | `ax25.ko` | `AF_AX25` socket, unprivileged | After `sudo modprobe ax25` |
|---|---|---|---|---|
| Debian 13 VM | 6.12.107 | module | errno 97 (not autoloaded) | opens |
| Parrot 7.3 VM | 7.0.13 | module | errno 97 (not autoloaded) | opens |
| Ubuntu 24.04 VM | 6.8.0 | module | errno 97 (not autoloaded) | opens |
| Ubuntu 26.04 VM | 7.0.0 | module | errno 97 (not autoloaded) | opens |
| Kali rolling 2026.3 VM | 7.1.5+kali-amd64 | **absent** | errno 97 | `modprobe: FATAL: Module ax25 not found in directory /lib/modules/7.1.5+kali-amd64` |
| Pop!_OS 24.04 VM | 7.1.5-76070105-generic | **absent** | errno 97 | `modprobe: FATAL: Module ax25 not found in directory …` |
| Pop!_OS 22.04 laptop | 7.1.1-76070101-generic | **absent** | errno 97 | module not found |

Two things the table shows that the archive alone does not:

1. **The kernel is a fact about the machine, not the distribution.** The
   Pop!_OS 24.04 VM still has its previous kernel installed, and the two
   module trees side by side are the whole finding:

   ```
   /lib/modules/7.0.11-76070011-generic/kernel/net/ax25/ax25.ko.zst
   /lib/modules/7.1.5-76070105-generic/kernel/net/ax25/            (absent)
   ```

   The laptop shows the same: `ax25.ko` under its 6.17.4, 6.17.9, 7.0.9 and
   7.0.11 trees, nothing under 7.1.1. Same distribution, same release, same
   archive; one reboot apart. Ubuntu 24.04's 6.8 has it today and loses it
   the day its HWE kernel crosses 7.1. This is why the check reads the
   running kernel at plan time and is **never written into the capability
   matrix**, which is per target.
2. **The overnight campaign's "packet installs whole on Pop!_OS" was true of
   packages and false of capability.** Every package arrived; `kissattach`
   could never have worked. Confirming an install by its packages is
   necessary and not sufficient — the same shape as issue #27.

The unprivileged errno 97 on every row is expected and is not the finding:
on a kernel that carries `ax25` as a module, nothing autoloads it until a
root `kissattach` or `modprobe` does. That is why the probe reads the module
tree rather than `lsmod` or `/proc/net/ax25` — an unloaded module is not a
missing one.

## What the engine does

A manifest declares `requires_kernel: [ax25]` when the software opens
`AF_AX25` sockets or configures the kernel stack and cannot do anything else.
`hammunition.kernel.KernelProbe` reads `/lib/modules/<uname -r>/` at plan
time:

| The probe finds | The plan does |
|---|---|
| `kernel/net/ax25/ax25.ko*`, or the path in `modules.builtin` | nothing; the unit plans as usual |
| a module tree for the running kernel that lacks it | **refuses the unit by name** if you typed it, naming the kernel release and the merge; **defers it** with the same reason if it reached the plan through a profile, and the rest of the profile installs (the **D-039** shape) |
| no module tree for the running kernel at all | plans the unit and adds a note that the requirement *cannot be checked on this machine*. This is a container on the host's kernel — the CI targets — and is not evidence either way |
| a profile member the target had already deferred — Kali's archive has no `ax25-tools` *and* its kernel has no `ax25` | keeps the reason already recorded. The first live `packet` dry-run on Kali replaced it with the kernel's, and the deferral's "a release that carries it needs no change here" was then false of Kali's archive. `hammunition install ax25-tools` by name shows both |

The refusal's remedies are the ones that exist: a distribution kernel that
still carries the stack (Debian 13's 6.12, Parrot 7.3's and Ubuntu 26.04's
7.0), or the userspace packet path below. It never offers to build the module.

## Which units this touches

**Declare `requires_kernel: [ax25]`** — they configure or speak to the
kernel stack and have no other mode:

`ax25-tools`, `ax25-apps`, `ax25-xtools`, `ax25mail-utils`, `axmail`,
`aprsdigi`, `fbb`, `linpac`, `uronode`, and `z8530-utils2` (whose `scc`
driver left in the same merge; **retired** on that evidence, **D-045**).

**Unaffected, and their manifests say so** — the userspace packet path,
which is most of what an operator actually runs:

| Unit | Why it still works on 7.1 |
|---|---|
| `direwolf`, `qtsoundmodem` | userspace modems; their KISS and AGW TCP ports are what everything else talks to. Only `kissattach`-ing them to the kernel needs `ax25` |
| `pat` | engines `agwpe` and `serial-tnc` (`ax25+agwpe://`, `ax25+serial-tnc://`) never open an `AF_AX25` socket. Engine `linux` (`ax25+linux://`) does and fails on 7.1. Read from `app/connect.go` and wl2k-go's `transport/ax25/ax25_linux.go` |
| `linbpq` | carries its own AX.25 implementation; drives Direwolf over KISS or AGW |
| `yaac` | KISS and AGW to Direwolf directly |
| `xastir` | Serial KISS TNC and AGWPE interface types need no kernel stack; only the "AX.25 TNC" type (`DEVICE_AX25_TNC` in `src/interface.c`) opens `AF_AX25` |

So on a 7.1 kernel `packet` still installs a working Direwolf–pat–APRS
station. What it cannot give you is a kernel port: no `axports`, no
`kissattach`, no `ax25d`, no `listen`, no NET/ROM. The profile page and
**D-008**'s packet-core statement both said "kernel AX.25 stack"; since
**D-045** both say userspace-primary, with the kernel stack the fuller
station where the kernel carries it.

## Reproducing the measurement

On any machine:

```
uname -r
ls /lib/modules/$(uname -r)/kernel/net/ax25/ 2>&1
python3 -c 'import socket; socket.socket(3, socket.SOCK_SEQPACKET)'
hammunition install ax25-tools --dry-run
```

The last line is the engine's own answer. On a kernel without the module it
exits 2 with the refusal; on one with it, it prints the plan (and, under
`--dry-run`, executes nothing).

## The engine, measured

Engine commit 383cf27, 2026-09-04, through `scripts/vm_campaign.py` with
each VM restored to its clean snapshot before the run. Reports are
`kernel-ax25-kali-units-2026-09-04.md` and
`kernel-ax25-debian13-units-2026-09-04.md` under
`~/.local/state/hammunition-campaigns/` on the maintainer's machine; the
harness stamps the engine commit and the guest's InRelease dates into each.

| Machine | Unit | Outcome |
|---|---|---|
| Kali 2026.3, `7.1.5+kali-amd64` | `ax25-tools` | **refused (plan)**, two blockers: *apt has no candidate for ax25-tools*, and *needs the kernel's AX.25 stack (module ax25), which kernel 7.1.5+kali-amd64 does not carry — Linux 7.1 removed net/ax25 and the hamradio drivers (merge 64edfa65, 2026-04-24)*, with the remedy naming Debian 13's 6.12, Parrot 7.3's and Ubuntu 26.04's 7.0, the userspace path, and that no module is built (D-024) |
| Kali 2026.3 | `linpac` | **refused (plan)** on the kernel blocker alone. `linpac` is still in Kali's archive: the archive check passes it and the kernel check is what catches it |
| Kali 2026.3 | `direwolf` | **installed, confirmed** in 5 s — the userspace modem is untouched |
| Debian 13, `6.12.107+deb13-amd64` | `ax25-tools` | **installed, confirmed** in 4 s |
| Debian 13 | `linpac` | **installed, confirmed** in 2 s |

The whole `packet` profile, installed for real on 2026-09-05 with engine
commit 6b8c080 (the fix included), each VM restored to its clean snapshot
first — `scripts/vm_campaign.py --reset-each <domain> --whole-profiles
--units packet`, reports `kernel-ax25-kali-packet-whole-2026-09-05.md` and
`kernel-ax25-debian13-packet-whole-2026-09-05.md`, each with an
`.evidence.jsonl` beside it holding the guest's transaction log:

| Machine | Result | Deferred by name | Confirmed by re-probe |
|---|---|---|---|
| Kali 2026.3, `7.1.5+kali-amd64` | exit 0, 39 s | **eight.** `ax25-tools` and `ax25-xtools` on the archive — *apt on Kali GNU/Linux Rolling has no candidate*; both build from the `ax25-tools` source package Debian removed from testing on 2026-09-01. `linpac`, `aprsdigi`, `ax25-apps`, `ax25mail-utils`, `axmail`, `uronode` on the kernel | 29 checks: 24 apt packages installed, `ardopcf`, `linbpq`, `qtsoundmodem` and `qttermtcp` executable under `/usr/local/bin`, `dialout` membership present |
| Debian 13, `6.12.107+deb13-amd64` | exit 0, 61 s | none | 40 checks, the same four builds and every member above it, `ax25-tools 0.0.10-rc5+git20230513+d3e6d4f-3` and `linpac 0.28-3` included |

Both runs also deferred `linbpq`'s `/etc/bpq32.cfg` for the station values
the VM does not set (D-035); that is a config deferral, not a member one.
The two declaring units outside `packet`, `fbb` and `z8530-utils2`, were
not run.

An earlier `--dry-run` of the same profile on Kali, before the fix, had
`ax25-xtools` deferred on the kernel; that was the overwrite at work, and
the fresh run shows the archive reason it keeps.

What is **not** measured here: any of this on real packet hardware, and
nothing on the maintainer's Parrot laptop yet — its 7.0.13 row above is the
Parrot VM's.
