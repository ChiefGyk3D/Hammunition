# VM install testing

The container matrix (`containers/targets.yaml`, run by CI and
`scripts/run-targets.sh`) proves what it can prove: the catalog validates on
every target, apt resolves what the manifests claim, and the engine's own
tests pass on each distro's Python. What it measurably cannot prove — and
[install-verification.md](../reference/install-verification.md) documents the
boundary — is everything past dependency resolution: postinst scripts that
need dbus/systemd, GUI applications actually launching, udev rules taking
effect, group membership after re-login, and the engine run end-to-end as a
real operator with sudo.

That is what the VMs are for. This is the runbook.

## The ladder

Full KVM/QEMU desktop VMs, worked in priority order. Parrot is primary
(CLAUDE.md); the rest follow the container matrix, plus one addition:

| Order | OS | Matches CI target | Notes |
|---|---|---|---|
| 1 | Parrot OS 7.x (Security) | `parrot` (priority 1) | Primary. The distro this project exists for. |
| 2 | Debian 13 | `debian-13` | The baseline everything else derives from. |
| 3 | Ubuntu 26.04 | `ubuntu-26.04` | |
| 4 | Ubuntu 24.04 | `ubuntu-24.04` | Declared 2026-09-03 from this VM's full-catalog campaign; the LTS Mint 22.x and Pop!_OS 24.04 install from. |
| 5 | Pop!_OS 24.04 | — none | See the caveat below before reading its results. |
| 6 | Kali rolling | `kali-rolling` | A `Kali` domain already exists on the host. |

**The Pop!_OS caveat.** Pop!_OS is not a declared target. Its os-release says
`ID=pop`, `ID_LIKE="ubuntu debian"`; the engine's family check consults
`ID_LIKE`, so installation is *permitted* — but manifest selectors match on
`ID` only, so any block gated `distro: ubuntu` will not match on Pop. Its
archive is Ubuntu 24.04's, which the matrix has measured as `ubuntu-24.04`
since 2026-09-03 — so an apt gap on Pop that the 24.04 rung also shows is a
fact about the archive, and one the 24.04 rung does not show is Pop's own.
Treat Pop results as evidence for a **decision about declaring `pop` a
target**, not as pass/fail against current claims. Failures unique to Pop are
findings about the gap, not bugs, until that decision is made.

## VM conventions

- **Guest sizing:** 4–8 GB RAM (2 GB is AHRL's own floor; wsjtx/SatDump-class
  source builds want more), 40+ GB disk, qcow2 (internal snapshots require
  it — the snapshot script refuses raw disks by name).
- **Guest account:** an ordinary user in `sudo`. Dev-VM credentials are fine
  *for a NAT-isolated dev VM*; never reuse them on anything bridged, and no
  credentials in this repo either way.
- **Networking:** default NAT. SSH in from the host (`virt-manager`'s console
  is for GUI checks): install `openssh-server` in the guest **before**
  baselining so every reset comes up reachable.
- **These VMs are not the dev machine.** CLAUDE.md forbids testing against
  the dev machine; a VM on the dev machine's hypervisor is a separate,
  disposable system and is exactly the sanctioned shape.

## Provisioning from a cloud image — no ISO, no console, no host root

The Ubuntu guests (24.04 and 26.04, 2026-09-01) were built this way, and it
is the fastest route to a new rung: about ten minutes from download to
`clean-baseline`, entirely from a shell, without ever opening a graphical
installer. It needs `virt-install` 4.0+ and a libvirt account that can talk
to `qemu:///system` — but not write access to the storage pool directory,
because every volume operation goes through the daemon.

1. **Download the cloud image and verify it.** Ubuntu publishes
   `SHA256SUMS` next to every image; check it, and record the digest you
   matched in the campaign notes — a cloud image is executable content and
   the same rule applies to it as to every artifact the catalog pins.
2. **Create the volume through the pool, then upload and grow it.** The
   default pool lives under `/var/lib/libvirt/images/`, which an ordinary
   account cannot write; the daemon can:

   ```sh
   virsh -c qemu:///system vol-create-as default ubuntu2604_dev.qcow2 40G --format qcow2
   virsh -c qemu:///system vol-upload --pool default ubuntu2604_dev.qcow2 resolute-server-cloudimg-amd64.img
   virsh -c qemu:///system vol-resize --pool default ubuntu2604_dev.qcow2 40G
   ```

   `vol-upload` replaces the volume's contents with the image and shrinks
   it to the image's virtual size; the `vol-resize` afterwards is what
   gives the guest its 40 GB, and cloud-init grows the root filesystem
   into it on first boot.
3. **Write the cloud-init seed.** A `user-data` declaring the dev account
   (in `sudo`, `dialout`, `plugdev`; `NOPASSWD` sudo is what the campaign
   script's `--yes` runs rely on), its SSH public key, `ssh_pwauth`,
   `package_update`/`package_upgrade`, and `packages:
   [openssh-server, python3-venv, git, rsync]`; a `meta-data` with an
   `instance-id` and `local-hostname`. Keep the seed **outside the repo**
   — it carries a password hash. Two more lines earn their place in
   `runcmd`: mask `sleep.target suspend.target hibernate.target
   hybrid-sleep.target` so a campaign that runs overnight is not suspended
   halfway, and `touch` a sentinel file so a poll can tell "booted" from
   "cloud-init finished".
4. **Import, then wait on the sentinel, not the boot.**

   ```sh
   virt-install --connect qemu:///system --name ubuntu2604_dev \
       --memory 4096 --vcpus 4 --import \
       --disk vol=default/ubuntu2604_dev.qcow2,format=qcow2,bus=virtio \
       --osinfo ubuntu24.04 --network network=default,model=virtio \
       --cloud-init user-data=./user-data,meta-data=./meta-data \
       --graphics none --noautoconsole
   ```

   `--osinfo ubuntu24.04` is the newest Ubuntu the host's osinfo database
   knew about; it only tunes virtual hardware defaults, and the guest is
   still 26.04. `--graphics none`: the console lane is a later, separate
   check, and a cloud image has no desktop yet anyway. The first boot runs
   `package_upgrade`, which on a fresh image is a few minutes; the sentinel
   from step 3 is what to wait for.
5. **Detach the seed before baselining.** `virt-install` attaches the
   cloud-init seed as a CD-ROM, and `scripts/vm-snapshot.sh baseline`
   refuses a domain with an ISO attached by design (an attached image is
   state the snapshot would silently depend on):

   ```sh
   virsh -c qemu:///system detach-disk ubuntu2604_dev sda --persistent
   ```

   Then the ordinary baseline checklist below — engine venv, SSH alias,
   `clean-baseline` — applies unchanged.

**Sizing note, measured.** A 4 GB guest with **no swap** is what a cloud
image gives you, and a four-job C++ build of a Qt application was OOM-killed
on one (js8call, 2026-09-01) while passing on a 4 GB Debian guest with 3 GB
of swap. The engine now sizes parallelism to memory plus swap; a guest for
build campaigns still wants either 8 GB or a swap file.

## The snapshot discipline

`scripts/vm-snapshot.sh` wraps virsh; `docs` here, mechanism there. The loop
that keeps install testing honest is **every campaign starts from the same
frozen state**.

### Baseline prep — the per-image checklist

Every item below must be *inside* `clean-baseline`, or every reset silently
loses it. Each one was learned by losing it on the first Parrot image:

1. Install the OS. Update it (`apt update && apt full-upgrade`).
2. `sudo apt install openssh-server && sudo systemctl enable --now ssh` —
   Parrot ships it installed but **disabled**; a baseline without it comes
   up unreachable on every reset.
3. Passwordless sudo for the test account (dev VMs only, never a bridged
   machine — the engine invokes `sudo apt-get` itself, and driving that over
   non-interactive SSH needs it):
   `echo 'USER ALL=(ALL) NOPASSWD: ALL' | sudo tee /etc/sudoers.d/90-dev-nopasswd`
   then `sudo chmod 440 /etc/sudoers.d/90-dev-nopasswd && sudo visudo -c`.
4. `sudo systemctl mask sleep.target suspend.target hibernate.target
   hybrid-sleep.target` — a **desktop guest suspends itself on idle**. The
   symptom is nasty: the domain says `running`, CPU time freezes, the network
   drops, `virsh dompmwakeup` refuses (`s2idle` never looks suspended to
   QEMU), and the console says "Display output is not active". One
   `virsh send-key DOMAIN KEY_LEFTSHIFT` wakes it; the mask prevents it.
5. `sudo apt install python3-venv` where the image does not ship it —
   Debian netinst does not, and without it the engine's git-clone workflow
   cannot even create its virtualenv. (Parrot and Kali ship it.)
6. **Detach the install ISO** — the script refuses to baseline while one is
   attached.
7. Shut the guest down, then take the baseline (a cold baseline boots fresh;
   a live one resumes mid-session — fine for quick loops, worse as a
   months-later known state):

   ```sh
   scripts/vm-snapshot.sh baseline ParrotOS_Dev
   ```

   The name is always `clean-baseline`, taken once, **before the first
   hammunition run**. The script refuses to overwrite it.

### The campaign loop

Test. Break things. Install profiles. Then back to fresh in one command:

```sh
scripts/vm-snapshot.sh reset ParrotOS_Dev
```

Mid-campaign checkpoints when a long setup shouldn't be repeated:

```sh
scripts/vm-snapshot.sh save ParrotOS_Dev station-installed
scripts/vm-snapshot.sh restore ParrotOS_Dev station-installed
```

Idempotency claims get tested *without* resetting: run the same install
twice from the post-install state and diff the transaction log. Uninstall
claims get tested against a `save` checkpoint, not the baseline, so what
uninstall missed is visible instead of being wiped by the revert. Take
checkpoints **cold** (shut down first) — they double as known states months
later, and a cold snapshot cannot capture a guest mid-anything.

## What to test, in order

Each step produces evidence for a specific standing claim. Record results
with **date, hammunition commit, distro + version, and the actual failure
text** — M5 requires verdicts to be tested, never inherited, and an
unrecorded test result rots into an inherited verdict within weeks.

1. **The walking skeleton, end to end.** `hammunition install station
   --dry-run` as the ordinary user; read every printed command; then the real
   run. This is the first execution of the engine on the primary target
   outside a container.
2. **Idempotency.** Run it again. The second run should change nothing and
   say so.
3. **The six configure-blocked packages.** `direwolf`, `gpredict`, `gpsd`,
   `cubicsdr`, `gnuradio`, `gr-gsm` — install-verification.md proved
   resolve+unpack only; the VM answers whether their postinsts configure
   cleanly on a real init system.
4. **One source build.** `direwolf` or `fldigi` — the source backend's first
   run on Parrot with real memory limits and wall-clock.
5. **GUI launch checks.** The container matrix can never do this. fldigi,
   gqrx, and whatever step 1 installed: launch, reach the main window, note
   any Wayland/X11 misbehaviour (AHRL's accumulated X11 guidance is a
   documentation obligation for us, not folklore).
6. **Hardware, on Parrot only at first.** USB-passthrough a real device
   (HackRF, Proxmark3, T-Deck), run detection, apply udev rules, replug,
   check group membership after re-login. This exercises the M4 code that
   cannot be exercised anywhere else.
7. **Uninstall.** From a `save` checkpoint: uninstall, then compare against
   the transaction log's claims.
8. **The M5 re-verification list.** `ardopcf` (CM108 PTT caveat), the
   compiler-flag-fragile set, and every `broken` candidate — each verdict
   recorded with its evidence.

## Campaigns at scale

`scripts/vm_campaign.py` is the ladder's loop, automated: it expands
profiles (or takes explicit units), runs `hammunition install <unit> --yes`
per unit over SSH against a prepared VM, and emits the evidence table —
outcome, seconds, and the actual tail text for every failure and plan-time
refusal. The engine's own exit codes do the classifying: 0 is
completed-and-confirmed, 2 is an honest refusal naming what is missing.

```sh
scripts/vm-snapshot.sh reset debian13_dev        # when you want isolation
scripts/vm_campaign.py --host user@GUEST_IP \
    --identity ~/.ssh/hammunition_vm_ed25519 \
    --profile packet --out campaign-packet.md
```

`--timeout` is a per-unit budget enforced **on the VM** by `timeout`, so a
unit that exceeds it is actually stopped and filed as `STOPPED (budget)` —
a separate bucket from failures, because it is not a verdict. It was
enforced locally once, which only killed the ssh client: Ubuntu 26.04's
single-job `qlog` compile was written off at 900 s and finished, verified,
at 1032 s with the next units running on top of it (2026-09-02). The
default of 1800 s covers every compile measured so far; a no-swap VM that
`default_jobs()` sizes to one job is the case that needs it.

No reset between units, deliberately: a campaign is one accumulating
machine-state, like a real operator's machine. This is the mechanism the M5
report will be generated from — one campaign per target, every unit, and
the exit-criterion fraction falls out as arithmetic. `--reset-first DOMAIN`
restores `clean-baseline` and prepares the guest once before the first unit,
so a whole-catalog campaign starts from the known state without a separate
`reset` and a by-hand sync.

**Prepare refreshes the apt lists.** A snapshot freezes them at the day it
was taken and the archive moves on: Parrot's `clean-baseline` was four days
old when its lists still named `glib2.0 2.84.4-3~deb13u3`, the pool no
longer had it, and six of fifteen profiles failed at their first fetch with
a 404 — four commands into a transaction, on a catalog that was fine
(2026-09-03). Every prepare now runs `apt-get update` before building the
venv, which is also why a guest without passwordless sudo fails at prepare
rather than at unit 1. The update is retried for up to five minutes,
because Pop!_OS 24.04 runs its own `apt-get` at boot and held the lists
lock against a prepare that started 30 s after the restore (2026-09-04);
`DPkg::Lock::Timeout` looks like the fix and is not — measured at a 0 s
wait against a held lists lock on apt 3.0.3, it covers the dpkg frontend
lock only. A prepare that fails prints the guest's output and is
retried once, because the Kali campaign died at profile 5 of 15 with a bare
`CalledProcessError` and no text — a PyPI hiccup and a broken guest were
the same verdict. The report file is rewritten after every unit, so a
campaign that dies keeps what it measured.

**Then install the profiles whole.** Per-unit success does not prove
profile success: twenty of `digital-modes`' twenty-one members were
confirmed by name on Parrot and Debian and the twenty-first carried a
measured verdict, yet the profile could not install as a whole anywhere —
that member's vendor `.deb` collided with a package another member pulled
in, and the plan only saw it once it was asked for the transaction an
operator actually types (clean Kali VM, 2026-09-02, forty-four commands in).
`--whole-profiles` installs each name as one transaction, and
`--reset-each DOMAIN` restores the guest to `clean-baseline` and re-prepares
it before each, so every profile is measured from the state a new operator
starts from:

```sh
scripts/vm_campaign.py --host user@GUEST_IP \
    --identity ~/.ssh/hammunition_vm_ed25519 \
    --whole-profiles --reset-each debian13_dev \
    --units station digital-modes packet --timeout 3600 --out campaign-profiles.md
```

The budget is per profile here, and the source-heavy ones need it —
`digital-modes` builds fldigi, WSJT-X and MSHV in one run.

### What a report has to carry to be believed

Six unit passes on 2026-09-04 filed `installed+confirmed` 1,375 times, and
not one row could say *what* had confirmed it without a shell on the guest.
`yaac` on Parrot rested on a single check — `libjssc-java 2.8.0-4`, a
dependency. `wsjtx-improved` was refused on every target for colliding
with a `wsjtx-data` that `jtdx` had pulled in hours earlier, an honest
refusal that hid the unit's own failure on a clean Kali (#24). The report
now carries the evidence rather than the verdict alone:

- **Confirmed by** — per unit, every check the engine's D-031 re-probe
  made (`package jtdx installed 2.2.159`; `binary fldigi:fldigi executable
  at …`; `group user:dialout …`), read from the transaction-log lines the
  unit appended. `no effect checks` means the re-probe had nothing to ask,
  and the summary counts those units separately: not failures, but exit
  codes rather than evidence. An engine that probes launchers and
  installed trees would empty that list; until then it is the stated blind
  spot.
- **Provenance** — the engine commit *and whether the synced tree matched
  it* (the guest gets the working tree, not the commit), the libvirt domain
  and snapshot with the snapshot's creation time, when prepare ran, and the
  `Date:` of every InRelease in the guest's apt lists after prepare. A
  reader can put the same tree on the same snapshot against lists of the
  same age. The guest's address is never in the report.
- **Cumulative refusals** — the guest reports what dpkg gained during each
  unit, dependencies included, and a later plan-time refusal that names one
  of those packages is labelled *cumulative* with the package and the unit
  that brought it. It is a fact about the pass, not the unit, so with
  `--reset-first DOMAIN` the campaign re-runs each such unit **alone on the
  restored snapshot** after the pass and files both verdicts side by side.
  `--reset-each` passes label nothing: no unit sees another's state.
- **`<out>.evidence.jsonl`** — the machine-readable record beside the
  markdown: the provenance, then one line per unit with exit code, tail,
  every transaction-log entry it appended and every package it added, then
  the isolated re-runs. Rewritten with the report after every unit, so a
  campaign that dies keeps what it measured, and the markdown can be
  reconstructed from it.

`tests/test_vm_campaign.py` holds one test per claim above, each first run
against a report that lacked the field to watch it fail.

## Maintenance sweeps

`scripts/check_artifact_urls.py` asks every pinned artifact URL in the
catalog whether it still exists — HEAD with a ranged-GET fallback, hard 4xx
verdicts kept apart from hosts that merely flaked today. Run it before a
release and after campaigns; it exists because four manifests carried URLs
constructed from AHRL's bundled filenames that nothing had ever fetched.
Deliberately not per-push CI: it needs the live internet, and a red job
nobody trusts is worse than none.

## Recording results

One file per campaign under `docs/reference/` once results exist (shape to be
settled by the first campaign — likely `vm-verification-<target>.md`,
mirroring install-verification.md). Raw logs stay out of git; conclusions,
versions and failure text go in.
