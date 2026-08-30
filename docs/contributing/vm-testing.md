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
| 4 | Pop!_OS 24.04 | — none | See the caveat below before reading its results. |
| 5 | Kali rolling | `kali-rolling` | A `Kali` domain already exists on the host. |

**The Pop!_OS caveat.** Pop!_OS is not a declared target. Its os-release says
`ID=pop`, `ID_LIKE="ubuntu debian"`; the engine's family check consults
`ID_LIKE`, so installation is *permitted* — but manifest selectors match on
`ID` only, so any block gated `distro: ubuntu` will not match on Pop, and
Pop 24.04 sits on Ubuntu 24.04-era archives while the matrix measures 26.04.
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

No reset between units, deliberately: a campaign is one accumulating
machine-state, like a real operator's machine. This is the mechanism the M5
report will be generated from — one campaign per target, every unit, and
the exit-criterion fraction falls out as arithmetic.

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
