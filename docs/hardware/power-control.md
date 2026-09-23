# Device power control

**Parking a catalogued device tells the kernel to drop its interfaces and
lets its USB port suspend.** It is the reversible equivalent of unplugging
something you are not using right now — a GPS receiver that draws power on
battery whether anything is reading it or not, a device you want off until
the next session. This page covers what it does to a machine, per CLAUDE.md's
rule that every system modification says what changes, why, how to inspect it
afterwards, and how to reverse it.

**What follows is a mix of two kinds of claim, and they are kept visibly
apart.** What the engine writes to sysfs, and reads back to confirm, is
measured — it is exercised by this branch's own test suite on every run.
What a device is expected to *look like* to the rest of the system while
parked — `lsusb`, `dmesg`, gpsd's own hot-unplug handling — is not: **no
park or wake has been run against real hardware yet**, on the field laptop
or anywhere else. `docs/reference/bench-verification-5430.md` gets a line
only once that has actually happened; until then, treat every claim below
about consumer-visible behaviour as an expectation from reading the kernel's
own sysfs documentation, not a measurement, the same way
`catalog/hardware/classes/gps-receiver.yaml`'s `power_control.note` already
hedges it for the one device that carries this block today.

## What parking is, and what it is not

Parking writes `0` to a device's own `authorized` file under
`/sys/bus/usb/devices/<address>/` and `auto` to its `power/control`. The
kernel drops every interface the device presented, the same as an ordinary
unplug — but **the sysfs node itself stays**: `authorized` is a file on the
*device*, not on any one interface, so it is still there to read and to
write back to `1`, which is the whole mechanism `wake` and
`hammunition hardware state` depend on. If the node disappeared along with
the interfaces, `state` could never report a device as parked and `wake`
would have nothing to write to — parking a device does not remove it from
the bus, it deauthorizes it on the bus.

What a parked device is expected to look like elsewhere is not measured:
`dmesg` logging a disconnect, `lsusb` no longer listing it, a serial
consumer like `cgps` losing its port. Every interface really is gone, so
that is the expected shape, but it has not been checked against a real
device here. Waking writes `1` back to `authorized`; the kernel
re-enumerates the device as if it had just been plugged in — expected to
produce a fresh `dmesg` attach and `lsusb` entry, again unmeasured.
`power/control` is left alone on wake, deliberately — restoring it to `on`
would undo a runtime power-management setting a udev rule or the operator
already owns.

It is **not** a low-power mode the device itself enters, not a driver unload,
and not anything that survives past the device being physically unplugged and
replugged — a park is a statement about the port, not the hardware. It is
**not persisted** anywhere: there is no state file recording which devices are
parked. `/sys` itself is the only record, a reboot wakes every device the
kernel re-probes, and `hammunition hardware state` reads the live answer back
from the bus on every call rather than trusting a cache that could go stale.
That is a deliberate simplification (**D-056**): sysfs is already the truth,
so there is nothing to reconcile at boot.

Two things the catalog can schema-validate but that are **refused at runtime**
until hardware proves them:

- **`pci_runtime`** — the power-control method for an MHI/PCIe card such as a
  WWAN modem, as opposed to `usb_deauthorize`'s USB path. No manifest in the
  catalog uses it yet; when a card that needs it is bench-verified, it ships.
- **`networkmanager_autoconnect`** — a "quiet verb" meant to stop
  NetworkManager racing to reconnect a WWAN modem's interface the instant it
  reappears on wake. It ships refused because the honest implementation binds
  it to *the device's own interface*, and `Parkable` carries no interface — a
  USB GPS receiver has none to bind to in the first place. The only device
  that would actually need this verb is a WWAN modem, and that method is
  itself refused above. An earlier draft implemented it by listing *every*
  NetworkManager profile on the machine and forcing `autoconnect yes` on all
  of them on wake, including ones the operator had deliberately set to `no` —
  a park/wake cycle would silently undo an unrelated setting. That is worse
  than doing nothing, so nothing is what it does until the filter can be
  built honestly.

Neither refusal blocks anything else: a device that declares `pci_runtime` or
a non-empty `quiet` list is simply refused *with a reason* the moment you try
to park it, the same way any other unbuilt capability in this project is
carried as a documented gap rather than dropped.

## Which devices are parkable, and why the catalog decides that

A device is parkable when, and only when, its catalog entry — a device or a
device **class** — carries a `power_control` block. There is no flag that
makes an arbitrary attached device parkable and no "parkable by default":
parking a rig cable mid-QSO because it happened to match a generic USB-serial
identifier is not a thing this project wants anyone to discover by accident.
The manifest author has to state, per device, that parking is safe and what an
operator should expect while it is parked.

Today that is one class: [`gps-receiver`](gps-receiver-class.md). Its
`power_control.note` is the model for how an unmeasured expectation is
written into a manifest — it says plainly that gpsd's own hot-unplug handling
means nothing further needs quieting, and that **nobody has run a park/wake
cycle against a receiver on the field laptop yet**, so what the operator
should expect is stated as an expectation, not a measurement, until
`docs/reference/bench-verification-5430.md` records one.

A device is only ever offered for parking while it is actually attached.
`hammunition hardware state`, the CLI verbs, and the generated menu entries
all read the USB bus fresh on every call — never a cached list — because
between one check and the next a device can be unplugged, or a USB address
reused by something else entirely.

## The two files `hardware apply` installs

Parking and waking write to sysfs as root, and everything that can ask for
that write is unprivileged: the CLI, a generated menu entry, and the Plasma
applet in `hammunition-tray`. `hammunition hardware apply` installs the one
thing that bridges the two, behind one polkit action, so there is a single
privileged path to review rather than three.

| File | Path | Mode | What it is |
|---|---|---|---|
| The helper wrapper | `/usr/local/libexec/hammunition-devctl` | `0755`, owned by root | A small POSIX shell script |
| The polkit action | `/usr/share/polkit-1/actions/com.chiefgyk3d.hammunition.devctl.policy` | `0644`, owned by root | XML, one `<action>` |

**The helper wrapper** is a fixed path under the shared prefix — polkit
annotates an *absolute executable path*, and a venv's own path changes across
an upgrade, so the wrapper is the stable thing the policy names. Its content
is short enough to read in full:

```sh
#!/bin/sh
# Installed by `hammunition hardware apply` (D-056). Do not edit: the
# polkit action at /usr/share/polkit-1/actions/com.chiefgyk3d.hammunition.devctl.policy
# authorises this exact path, and the next apply rewrites this file.
cd /
exec /path/to/your/interpreter -I -m hammunition.cli.devctl "$@"
```

The interpreter path is whichever Python ran `hardware apply` — normally the
venv's own `.venv/bin/python`, since that is the documented install
(`docs/getting-started/install.md`). It is disclosed in the plan before it is
ever written, and re-baked every time `apply` runs, so reinstalling the
engine into a new venv updates what root actually executes.

**The `-I` is load-bearing, not tidiness.** `python -m <pkg>` inserts
`os.getcwd()` at `sys.path[0]`. `pkexec` normally masks that by `chdir()`-ing
to the target user's home before it execs the authorised program — but
`pkexec --keep-cwd` does not, and the polkit action above pins an *executable
path*, not an argument list, so nothing stops a caller from adding that flag.
Without `-I`, a local user with an active session could `cd` to a directory
holding their own `src/hammunition/cli/devctl.py`, run `pkexec --keep-cwd
/usr/local/libexec/hammunition-devctl state`, authenticate with their own
password (`auth_self_keep`), and have their module imported and run as root
instead of the real one. `-I` drops `sys.path[0]`, `PYTHONPATH`, `PYTHONHOME`
and user site-packages while still resolving `hammunition` from the
interpreter's own venv, so the hijack import fails instead of succeeding. The
`cd /` above it is defence in depth on top of that.

**The polkit action** authorises exactly that one path, for exactly the
`com.chiefgyk3d.hammunition.devctl` action id, nothing wider:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE policyconfig PUBLIC
 "-//freedesktop//DTD PolicyKit Policy Configuration 1.0//EN"
 "http://www.freedesktop.org/standards/PolicyKit/1.0/policyconfig.dtd">
<policyconfig>
  <vendor>Hammunition</vendor>
  <vendor_url>https://github.com/ChiefGyk3D/Hammunition</vendor_url>
  <action id="com.chiefgyk3d.hammunition.devctl">
    <description>Park or wake a radio device</description>
    <message>Authentication is required to change a device's power state</message>
    <icon_name>preferences-system-power</icon_name>
    <defaults>
      <allow_any>auth_admin</allow_any>
      <allow_inactive>auth_admin</allow_inactive>
      <allow_active>auth_self_keep</allow_active>
    </defaults>
    <annotate key="org.freedesktop.policykit.exec.path">/usr/local/libexec/hammunition-devctl</annotate>
    <annotate key="org.freedesktop.policykit.exec.allow_gui">true</annotate>
  </action>
</policyconfig>
```

`allow_active=auth_self_keep` means an active local session authenticates
once and stays authorised for a few minutes afterwards — polkit's own manual
page documents the interval as "a brief period (e.g. five minutes)" without
committing to an exact number, so read it as "a few minutes", not as "the
session". A park followed by a wake a few minutes later is one password; one
at breakfast and the next at lunch is two. It is still the shape a tray
switch needs, because one that demands a password on *every* flip is a
switch nobody uses — it just does not remove the prompt for good. A remote
or inactive session (SSH, a login on another virtual terminal) always needs
`auth_admin`: parking someone else's device over SSH is not a thing a single
password prompt should make easy.

`hardware apply` is idempotent here exactly as it is for the udev rules: if
both files already match what it would write, it reports that and does
nothing. Before writing either one, it checks who could tamper with what
root is about to run — the interpreter path and the `hammunition` package
directory it imports from, both as given and resolved through any symlink.
Two things make it refuse outright, before anything is written: either
component being writable by more than its own owner (any local account, not
just the one that created it, could then replace what root runs), or either
component failing to `stat` at all, which is treated as unsafe rather than
assumed safe. A component that is merely owned by one non-root account — the
ordinary shape of a venv under `$HOME` — is not refused; `apply` discloses it
and asks you to type the path back before proceeding, a confirmation `--yes`
cannot satisfy. See **D-056** for the reasoning behind the distinction.

## The verbs and their exit codes

### `hammunition hardware park NAME [--dry-run]`

Detaches the named device and lets its port suspend. `NAME` is the catalog
name (`gps-receiver`), or `NAME@ADDRESS` (`gps-receiver@1-4`) when two of the
same kind are attached and the plain name would be a guess. `--dry-run`
prints the writes and the `pkexec` call it would make, then stops — nothing
is executed.

| Exit code | Meaning |
|---|---|
| 0 | Parked and verified, or a `--dry-run` that printed the plan |
| 1 | The helper ran but a write did not verify, or the command otherwise failed to run |
| 2 | Unplannable: the helper is not installed, `pkexec` is not on `PATH`, or `NAME` does not resolve to a parkable attached device |
| 3 | The authentication prompt was declined or denied; nothing was changed |

### `hammunition hardware wake NAME [--dry-run]`

The reverse of `park`, same `NAME` syntax, same flags, same exit codes. Also
reversed by a reboot: every parked device wakes on its own once the kernel
re-probes the bus.

### `hammunition hardware state`

Read-only, needs no privilege: lists every catalogued device that is both
attached now and parkable, and whether each one is parked. Always exits `0`
— it is a report, and an empty report ("no parkable device is attached") is
not a failure.

### `hammunition hardware unapply [--dry-run] [--yes] [--user NAME]`

Removes the helper wrapper and the polkit action — **and only those two
files**. It is not part of `uninstall` and is invoked separately for a
reason recorded in **D-056**: `uninstall` resolves the names it is given
against the package and profile catalogs, and there is no unit named
`hardware` to give it.

`unapply` removes exactly what the transaction log records `hardware apply`
put there for the given operator — never a path it merely expects to exist,
and never anything the log names that is not the helper or the policy path,
even if a hand-edited log claimed otherwise. **It deliberately never touches
the udev rules file.** Those rules are declarative, harmless for a device
that is not attached, and removing them would take away device access you are
still using — power control is the reversible part of this feature; device
permissions are not.

| Exit code | Meaning |
|---|---|
| 0 | Removed and verified, nothing recorded to remove, everything already absent, a `--dry-run`, or the operator declined the confirmation prompt |
| 1 | The operator could not be determined, a removal command failed, or a file the run tried to remove is still present afterwards |

## How to inspect it afterwards

- **`cat /sys/bus/usb/devices/<address>/authorized`** — the ground truth for
  one device: `0` means parked, `1` means not. This is the exact file
  `park`/`wake` write and read back to confirm their own effect (D-031), so
  in the moment either command ran it agrees with what it reported — asked
  again later, the address may now name a different device entirely if
  something was unplugged and replugged in between, which is exactly why
  the verbs re-resolve `NAME` fresh from the bus on every call rather than
  trusting an address from a previous run.
- **`hammunition hardware state`** — the read-only, no-privilege summary of
  what is parkable and what is parked right now, reading the same file above
  for every catalogued, attached device in one pass.
- **`pkaction --action-id com.chiefgyk3d.hammunition.devctl --verbose`** —
  prints the polkit action as the system currently sees it: the
  `allow_active`/`allow_inactive`/`allow_any` defaults above, and confirms
  the action is actually registered (an `apply` that was never run, or one
  whose policy file failed verification, leaves this command reporting
  nothing for that action id).
- **`lsusb`** — expected, not yet confirmed here, to no longer list a parked
  device (every interface really is dropped) and to list a woken one again
  under a fresh enumeration. Useful as a second, independent view once it
  has been checked against `authorized` at least once; not a substitute for
  reading `authorized` directly, which is the file the engine itself trusts.

## How to reverse it

- **`hammunition hardware wake NAME`** brings one parked device back.
- **A reboot** wakes every device on the machine — nothing is persisted, so
  there is nothing for a reboot to leave behind.
- **`hammunition hardware unapply`** removes the helper and the polkit action
  themselves, so no CLI verb, menu entry or tray switch can park or wake
  anything on this machine until `hammunition hardware apply` reinstalls
  them. It does not wake anything that is currently parked — do that with
  `wake` or a reboot first if you want a clean state.

## Removing the authentication prompt for the active session (optional, never installed by us)

`allow_active=auth_self_keep` already means one password covers a park and a
wake done a few minutes apart, but the grant lapses well before a session
does — a flip at breakfast and another at lunch are two separate prompts. If
even the recurring prompt is unwelcome — for a single-user field laptop
where the active session *is* the operator — polkit supports a local
authorization rule that grants the action to the active session with no
prompt at all, for as long as that session stays active. **Hammunition never
installs this file.** It is root-owned
policy that widens what an unattended process can do without a password, and
this project's own rule is that a security posture like that is the
operator's decision alone, made in full, not something an install script
nudges toward with a default. If you want it, create it yourself:

```js
// /etc/polkit-1/rules.d/49-hammunition-devctl.rules
polkit.addRule(function(action, subject) {
    if (action.id == "com.chiefgyk3d.hammunition.devctl" &&
        subject.active && subject.local) {
        return polkit.Result.YES;
    }
});
```

Save it at `/etc/polkit-1/rules.d/49-hammunition-devctl.rules`, mode `0644`,
owned by root; `polkitd` picks up rules files automatically, no reload
command needed. `subject.active && subject.local` is the same pair of
conditions the shipped action's `auth_self_keep` already narrows to a local,
active session — this rule only removes the password on top of that, it does
not widen who qualifies. Deleting the file (or reverting to the packaged
default, since nothing under `/etc/polkit-1/rules.d/` is ours to manage) puts
the prompt back.

## The tray applet

A Plasma system-tray toggle that parks and wakes a device with one click lives
in a separate repository, [`hammunition-tray`](https://github.com/ChiefGyk3D/hammunition-tray)
— not in this one. It is a client of the engine exactly as the CLI and the
generated menu entries are: it calls the same `pkexec
/usr/local/libexec/hammunition-devctl park|wake|state` that `hardware apply`
installs, through the same one polkit action, and needs nothing of its own
installed as root. See its own README for setup; a non-Hammunition user who
only wants the tray switch can be pointed straight at it.

## Troubleshooting

**`pkexec` exiting 126 or 127 does not only mean the dialog was dismissed.**
`hammunition hardware park`/`wake` report "the authentication prompt was
dismissed; nothing was changed" for any `pkexec` exit of 126 or 127. Per
`pkexec`'s own manual page, that pair of codes is not only "you clicked
Cancel": 126 is specifically the dialog being dismissed, and 127 covers
every other way authorisation did not happen.

**The likeliest 127 on a real ham's machine is not a denial at all — it is
no authentication agent being available to show a dialog in the first
place.** That is the ordinary state of a bare SSH session or a plain TTY
with no desktop session behind it, and it is the first thing anyone running
this headless will hit. `pkexec` falls back to registering its own textual
agent only when nothing else offers one, and on some setups that fallback
still isn't enough. If `park`/`wake` reports the prompt was "dismissed" and
you were never on a graphical session (or a terminal a graphical session's
own polkit agent is attached to) to dismiss anything, install `policykit-1`
— the same package `hammunition hardware park`/`wake` already names in
their own error message when `pkexec` is missing outright — and make sure a
polkit authentication agent is actually running for that session.

127 also covers the calling process being outright denied (a policy
decision, not merely "not yet given") and authentication failing, and folds
in **any other error**, which is the bucket a target that exists but is not
marked executable falls into — the state `/usr/local/libexec/hammunition-devctl`
would be in if its permissions were altered by hand after `apply` wrote it
`0755`. Nothing is written to the device in any of these cases, so this is a
message-accuracy issue rather than a correctness one — but if the dialog
never appeared at all and an authentication agent genuinely is running,
check `ls -l /usr/local/libexec/hammunition-devctl` before assuming you
dismissed a prompt you never saw.
