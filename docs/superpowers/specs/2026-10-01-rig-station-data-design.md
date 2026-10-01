# The rig as station data: one `rigctld` for every program — design (D-073)

**Date:** 2026-10-01. **Status:** proposed, for the maintainer's review.
Nothing here is built, and no implementation plan exists yet; one is written
after this document is ruled on.
**Decision record:** D-073 is reserved for it, status *proposed*, and is
written with the implementation, as D-061 was.
**Answers:** Q-022 #2 in `docs/QUESTIONS.md` (ruled "yes, as a sub-project
with a spec, after #1"), which asks for gap report §A2 in
`docs/reference/catalog-gaps-2026-09.md` and asks one question outright:
*is a systemd user service a `system_modifications` kind you want the schema
to have?* §6 answers it.
**Depends on:** D-020 (resolution consults hardware), D-028 (a chip
identifier never names a `/dev` node), D-029 (the hardware role is
permissions and mapping), D-035 and its 2026-09-29 amendment (a missing
value defers one file; derived values; `~/` is the operator's home), D-042
(ETC's rig model, reimplemented as data; its role symlinks not carried),
D-056 and D-058 (how this project discloses, runs and reverses a service it
manages), D-059 (every new state has a `--json` shape), D-062 (an install run
as the operator).
**Origin:** D-042 rule 2 and sub-project 3: "a radio is data (a `rig`
class), an operator's selection is station configuration, and an
application's rig settings are a templated `config_files` block on the
manifest that already carries its install."

The callsign and grid in examples are placeholders (`N0CALL`, `FN31pr`), and
every serial-port path is the placeholder
`/dev/serial/by-id/usb-Silicon_Labs_CP2105_...-if00-port0`.

## 1. What it delivers

| Need | Answer |
|---|---|
| Say once which radio is on the station, on which port, at what speed | Three station values, `rig`, `rig_device`, `rig_baud`, set with `hammunition station set` and checked against the catalog (§4) |
| Know what a radio needs from Linux and from hamlib | A `rig` hardware class and one device manifest per radio, each with a `rig` block: hamlib model, CAT port, speed range, audio path, PTT (§3) |
| One program owns the serial port; every other program shares it | One `rigctld` per operator, a systemd **user** service on `127.0.0.1:4532`, written from the three values; with any of them unset it is deferred and every unit still installs (§5) |
| Configure each program once | A file where the program does not rewrite it (gpredict's radio, §7); the settings page for the programs that do, with one answer per program: *Hamlib NET rigctl*, `127.0.0.1:4532` |
| flrig instead, for an operator who wants the panel | One more station value, `rig_owner: flrig`, and then no service and every program pointed at flrig (§8) |
| Know it works | `doctor` checks the service, the port, the device, the arguments against the station, and that the radio answers, without ever keying it (§9) |

## 2. What was measured, and on what

Read-only, on the field laptop (Parrot 7.3, systemd 257, hamlib
`4.7.2-1~bpo13+1` from backports), 2026-09-30 and 2026-10-01. No radio was
attached and no program opened a serial port: `rigctl` ran only as
`rigctl -l`, and as `rigctl -m N -r /dev/null -u` and `-L`, which print a
backend's capabilities and configuration and exit. `rigctld` ran only as
`--help` and `--version`. No program's settings file was read, because each
holds the operator's callsign.

- **hamlib's model list** (`rigctl -l`, 323 lines): FT-991/FT-991A is
  `1035`, FT-891 `1036`, FT-710 `1049`, FTX-1 `1051` (*Beta*), IC-7300
  `3073`, IC-705 `3085`, QCX/QDX `2052`; *NET rigctl* is `2`, *FLRig* `4`,
  *Dummy* `1`. **No BTECH and no Baofeng radio is in it**; the only Chinese
  handheld or mobile is AnyTone's D578A (`37001`, *Beta*).
- **The FT-991 backend's needs** (`rigctl -m 1035 -r /dev/null -u` and
  `-L`): serial speed 4800 to 38400, two stop bits, hardware (CTS/RTS)
  handshake, CAT PTT supported, `serial_speed` defaulting to 38400 in the
  backend. The IC-7300, FT-710, FTX-1 and QDX backends want no handshake and
  go to 115200; the IC-705's stops at 19200.
- **`rigctld`'s options** (`--help`): `-t` port, default 4532; `-T` listen
  address, **default ANY**; `-A` password, **"NOT IMPLEMENTED"**; `-R`
  closes the radio while no client is connected. hamlib's per-rig multicast
  publishing is off by default (`multicast_data_addr` and
  `multicast_cmd_addr` both `0.0.0.0` in `-L`).
- **No socket activation.** Neither `rigctld` nor `libhamlib.so.4` contains
  `LISTEN_FDS`, `sd_listen_fds` or `NOTIFY_SOCKET` (`strings`), and
  `rigctld` binds its own socket rather than serving a connection on
  standard input, so neither systemd socket form (`Accept=no` passing a
  listening socket, `Accept=yes` inetd-style) can start it. A plain service
  is the shape (§5).
- **The user manager sees serial devices.** `systemctl --user list-units
  --type=device` lists `dev-serial-by\x2did-….device` units, because
  systemd's `99-systemd.rules` tags every `tty[a-zA-Z]*` node `systemd`; a
  user unit can therefore name the radio's device unit (§5). The user
  manager (`user@1000.service`) runs with the same supplementary groups as
  the login shell, `dialout` (20) among them; linger is off.
- **Which programs link hamlib** (`ldd`): WSJT-X, JTDX, JS8Call, fldigi,
  tlf, QLog, KLog, xlog, QSSTV, FreeDV and Direwolf do. gpredict and CQRLOG
  do not: they speak `rigctld`'s TCP protocol themselves. flrig has its own
  backends. Xastir does not link hamlib, and YAAC's jars carry no hamlib or
  rig-control class: neither speaks CAT at all.
- **Each program's configuration keys**, from the strings in the binaries
  and, for FreeDATA, from the 0.18.2 wheel (sha256 matching the manifest's
  pin): §7 cites them per program.

Not measured, and named where each is used: any radio, any program talking
to `rigctld`, the user service itself, what the FT-991A presents on USB, and
every target other than the field laptop.

## 3. The radios: a `rig` class and one manifest per radio

**A radio is a device manifest; the class carries what every radio shares.**
That is the D-042 wording and the shape the hardware catalog already has: a
device names its `device_class` and inherits the class's groups, packages
and identifiers.

### 3a. The class (catalog/hardware/classes/rig.yaml, new)

- `groups: [dialout]`. Serial nodes are already `dialout` from the
  distribution's own default rules (`50-udev-default.rules`:
  `KERNEL=="tty[A-Z]*[0-9]|…|rfcomm[0-9]*", GROUP="dialout"`, read on the
  laptop), so **no udev rule is written** and no
  symlink is ever emitted (D-028, D-029: what a CAT port needs is access,
  and `/dev/serial/by-id/` already names it).
- `packages: [libhamlib-utils, flrig]`.
- `usb_ids`: the CP2105, `10c4:ea70`, the bridge the FT-991A carries per
  D-042's reading of ETC's rules, with its `ambiguity` block
  (`kernel_generic_driver`, already on the generated list in
  `docs/reference/usb-ambiguity.md`) and `also_used_by` naming the FTX-1 and
  the Digirig cable D-042 names. A class must carry at least one confirmed
  identifier (D-030); this one is confirmed as *a CP2105* by the kernel's
  `cp210x` table, and confirmed as *an FT-991A's* only by the bench (§12).
  Further bridges (CP2102 on Icom radios, FTDI) join when a radio that
  presents them is added, with its evidence, never ahead of it.
- The class's `known_problems` say the D-028 sentence plainly: **the
  chip does not say which radio it is. The operator's selection decides**,
  through `station set --rig`, and nothing in this design reads a radio's
  identity from its USB identifiers. Two radios on one CP2105 identifier are
  told apart by their by-id paths, and the station names one of them.

### 3b. The `rig` block on a radio's manifest (schema, new)

```yaml
rig:
  hamlib_model: 1035          # `rigctl -l`; the plan checks the target's hamlib lists it
  cat:
    kind: usb_cp2105_dual     # usb_cp2105_dual | usb_cp210x | usb_ftdi | usb_cdc_acm |
                              # usb_ch340 | bluetooth_rfcomm | none
    interface: "00"           # which -ifNN- port is CAT, when the chip has several
    baud: [4800, 38400]       # the backend's range, from `rigctl -m N -u`
    factory_baud: null        # the radio's out-of-box CAT rate, only when read from the radio
    handshake: hardware       # from `rigctl -m N -u`
  audio: builtin_usb_codec    # builtin_usb_codec | external_interface | none
  ptt: [cat, rts, dtr, vox]   # what the radio can be keyed by; the first is the default
  ptt_interface: "01"         # the -ifNN- port for RTS/DTR keying, where it differs from CAT
```

Each value cites where it came from, in a comment, as the hardware catalog
already does. `factory_baud` stays `null` until it is read from the radio:
the station never defaults the speed (§4), so the catalog has no reason to
guess it.

### 3c. The first two bench radios

**`yaesu-ft-991a`** (owned): `device_class: rig`, `composite: true` (a
CP2105's two serial ports and a USB audio codec behind one cable), hamlib
`1035`, CAT on `-if00-` (the *Enhanced* port) and RTS/DTR keying on
`-if01-` (the *Standard* port) per Yaesu's documentation as the
digital-modes guide cites it, **not measured**; audio `builtin_usb_codec`
(a TI/Burr-Brown codec per `docs/guides/audio-routing.md`, identifier **not
measured**). `status: untested`, `identification_gap` naming what the bench
records (the two ports' product strings, whether the CP2105 reports a serial
— recorded as `reports_serial`, never the value — and the codec's
identifier), `gap_closure: maintainer_hardware`.

**BTECH UV-50PRO** (owned): **not a `rig` member.** hamlib 4.7.2 has no
BTECH or Baofeng backend (§2), so there is no CAT to share. It is keyed by
VOX or by an interface's RTS line, and its page says so. A PTT-only
`rigctld` — the dummy model with `-p <interface port> -P RTS`, so programs
still select *Hamlib NET rigctl* and key through it — is plausible from
`rigctld --help` and **not measured**; it is question 6 (§15), not part of
this design.

## 4. The station values

```sh
hammunition station set --rig yaesu-ft-991a \
    --rig-device /dev/serial/by-id/usb-Silicon_Labs_CP2105_...-if00-port0 \
    --rig-baud 38400
hammunition station set --clear-rig        # removes all three, and rig_owner
```

Stored in `station.yml` beside the callsign, mode 0600 as now. Checked when
set, against the catalog, by the CLI (the station module stays free of the
hardware catalog, and the plan re-checks at install time so a catalog change
cannot leave a stale value unreported):

| Value | Accepted | Refused | Warned |
|---|---|---|---|
| `rig` | a device id whose `device_class` is `rig` | anything else, naming the rig devices the catalog has | — |
| `rig_device` | an absolute path under `/dev/` of letters, digits and `#+-.:=@_/` (the characters udev leaves in a by-id name) | `..`, whitespace, quotes, `\`, `$`, `%` — each of which systemd would expand or split in `ExecStart=` | not under `/dev/serial/by-id/` ("the number changes with plug order"); a by-id path whose `-ifNN-` differs from the manifest's CAT `interface`; a path that does not exist right now (the radio may simply be off) |
| `rig_baud` | an integer inside the manifest's `cat.baud` range | outside it, naming the range | — |

**Nothing is defaulted** (D-035). The radio's CAT rate is a menu setting the
operator may have changed, and a wrong speed is silence, not an error; so
`station set --rig` prints the backend's range and says to read the radio's
CAT RATE menu, and `rig_baud` stays unset until the operator gives it.

**Privacy.** A by-id path carries the device's serial number, the same class
of identifier as a hostname (`CLAUDE.md`). `station show` prints it, as it
prints the callsign, for the operator's own screen; the plan, `doctor`,
`status` and every `--json` document other than `station`'s print it with
the serial elided (`usb-Silicon_Labs_CP2105_…-if00-port0`), using udev's
`ID_SERIAL_SHORT` for the device to know which part is the serial.

## 5. One shared `rigctld`, as a systemd user service

**A plain user service, not socket activation**: §2 measured that `rigctld`
cannot take a socket from systemd. **A user service, not a system one**:
the station values are the operator's and live in their home; the port
belongs to whoever is logged in at the radio; and nothing here needs root.
It starts at login, runs as the operator, and stops when the radio does.

The unit file, rendered by the engine from §6's block (sample with the
placeholders; the real one carries the full by-id path):

```ini
# Written by Hammunition (catalog unit `rig-service`, D-073).
# Changed by `hammunition station set` then `hammunition install rig-service`;
# removed by `hammunition uninstall rig-service`. Do not edit: a reinstall
# replaces this file whole.
[Unit]
Description=hamlib rigctld for the station's rig (yaesu-ft-991a)
BindsTo=dev-serial-by\x2did-usb\x2dSilicon_Labs_CP2105_...\x2dif00\x2dport0.device
After=dev-serial-by\x2did-usb\x2dSilicon_Labs_CP2105_...\x2dif00\x2dport0.device

[Service]
ExecStart=/usr/bin/rigctld -m 1035 -r /dev/serial/by-id/usb-Silicon_Labs_CP2105_...-if00-port0 -s 38400 -T 127.0.0.1 -t 4532
Restart=on-failure
RestartSec=5
NoNewPrivileges=yes

[Install]
WantedBy=default.target
WantedBy=dev-serial-by\x2did-usb\x2dSilicon_Labs_CP2105_...\x2dif00\x2dport0.device
```

- **`-T 127.0.0.1` always.** The default is ANY (§2), which would put the
  transmitter on whatever network the laptop joins.
- **`BindsTo` the radio's device unit**: the FT-991A's USB chip is powered
  by the radio, so switching the radio off removes the port, and a `rigctld`
  holding a dead descriptor answers every client with an I/O error until
  someone restarts it. Bound, it stops with the port. **`WantedBy` the same
  device unit** is meant to start it again when the radio is switched on:
  whether a user manager honours a `.wants` link on a device unit is **not
  measured**, and if it does not, the fallback is `Restart=on-failure` with
  the operator's `systemctl --user start`, said in the guide.
- **Unit name `hammunition-rigctld.service`**, file
  `~/.config/systemd/user/hammunition-rigctld.service`, through the
  `O_NOFOLLOW` home-path writer D-035's amendment built.
- **The carrying unit is new, `rig-service`**, in the `station` profile,
  depending on `libhamlib-utils`, with no launcher. Putting the service on
  `libhamlib-utils` itself (the report's wording) would print a deferral to
  every operator who installs hamlib for an SDR or for FreeDATA's
  dependency and owns no radio; a unit of its own defers once, by name, in
  `station`. Question 2.
- **D-035, exactly:** with `rig`, `rig_device` or `rig_baud` unset, the
  service is deferred, the plan names the missing values and the
  `station set` command that supplies them, and every other unit in the
  transaction installs. The hamlib model is a value derived from `rig`
  through the catalog — the amendment's derived values, with a catalog
  lookup as the derivation — so a `rig` the catalog no longer has defers
  with that reason rather than templating nothing.
- **Groups.** The service can open the port only if the *user manager* holds
  `dialout`, and a membership added by the same install reaches the user
  manager only after every session of the operator has ended, not at the
  next terminal. The plan says "log out completely", and `doctor` reads the
  manager's own groups (§9).
- **No linger.** The service runs while the operator is logged in. A
  station that must run with nobody logged in needs `loginctl
  enable-linger`, a root-written change to `/var/lib/systemd/linger/`; not in
  this design (question 7).
- **One port per machine.** Two operators logged in at once would each start
  a `rigctld` on 4532 and the second would fail to bind. The service's
  failure says so; the station is one operator's (§11).

## 6. Q-022's question: a `user_services` block, not a `system_modifications` kind

**Recommendation: yes to the schema change, but as a block of its own,
`user_services`, beside `config_files`, not as a kind inside
`system_modifications`.**

Why not a `system_modifications` kind: those entries are *descriptions* —
`description`, `detail`, `reversible`, `reverse_hint` — and the engine acts
on only two kinds of them (`group_membership`, `apt_pin`; every other kind
is a blocker by name). A user service is not a description of something the
operator does by hand; it is a file the engine renders from station values,
which defers when a value is missing (the `config_files` property D-035 said
no modification kind has), plus three `systemctl --user` commands, plus a
reversal. It is also not a *system* modification: it lives in one
operator's home and needs no root. A block of its own keeps the D-035
deferral, the `~/` writer and the plan's "fills" disclosure, and adds only
the part `config_files` cannot do: enable, start, stop, disable.

Why not plain `config_files` with a `~/.config/systemd/user/` path (the
precedent is the `chrony` unit's gpsd drop-in, D-072): it writes the file
and nothing makes systemd read it, enable it or stop it on uninstall, and
the catalog would then carry free-form unit text — the place a command line
quietly grows a `sh -c`.

### 6a. The block

```yaml
user_services:
  - name: hammunition-rigctld            # unit file name, without .service
    description: hamlib rigctld for the station's rig
    exec: [/usr/bin/rigctld, -m, "{station.rig_hamlib_model}",
           -r, "{station.rig_device}", -s, "{station.rig_baud}",
           -T, 127.0.0.1, -t, "4532"]
    binds_to_device: "{station.rig_device}"
    listens: [{protocol: tcp, address: 127.0.0.1, port: 4532}]
    unless_station: {rig_owner: flrig}   # §8
```

Validated at load: `exec[0]` is an absolute path to a file the unit's own
apt packages ship (checked in the plan against `dpkg -L`), every element is
one argv word (no shell, no `;`, `|`, `$` or `%` reaching the unit file, and
station values are re-checked by §4's pattern after substitution);
`listens` addresses must be loopback, and a non-loopback one is refused at
load, not warned. The engine renders the unit file (the fixed header, `[Unit]`,
`[Service]` with `Restart=on-failure` and `NoNewPrivileges=yes`, `[Install]`)
from these fields, so no manifest writes unit syntax.

### 6b. What the plan prints

```
User services (D-073), for the operator ham:
  rig-service: hammunition-rigctld
    writes   ~/.config/systemd/user/hammunition-rigctld.service
    runs     /usr/bin/rigctld -m 1035 -r /dev/serial/by-id/usb-Silicon_Labs_CP2105_…-if00-port0
             -s 38400 -T 127.0.0.1 -t 4532
    filled from: rig, rig_device, rig_baud
    listens  127.0.0.1:4532 — any program on this machine can key the
             transmitter through it; it has no password (rigctld -A is not implemented)
    starts   at your login, and when the radio's port appears
    then     systemctl --user daemon-reload
             systemctl --user enable hammunition-rigctld.service
             systemctl --user restart hammunition-rigctld.service   (only if the port is present)
    inspect  systemctl --user status hammunition-rigctld
    reverse  hammunition uninstall rig-service
```

When deferred: `rig-service: deferred — needs rig_device, rig_baud. Set
them: hammunition station set --rig-device … --rig-baud …`, and the rest
of the transaction proceeds.

### 6c. Running it

The `systemctl --user` steps run as the operator, never through `sudo`
(D-062's split: only root steps are prefixed). Run as root with an operator
known (`sudo hammunition`), they run as `systemctl --user
--machine=<operator>@.host` (systemd 248 and later; not yet run here); with
no operator, or no user manager running
for that operator, the file is written and enabled and the plan says the
service starts at the operator's next login. A changed station value
reaches the service only through a reinstall of `rig-service`, which
rewrites the file and restarts the service; `station set` prints that
command when it changes a rig value. The transaction log records
`user_service_written` and `user_service_enabled` with the unit name and
the operator, never the station values.

### 6d. Reversing it

`hammunition uninstall rig-service`: `systemctl --user disable --now
hammunition-rigctld.service`, then the file is removed **only if it starts
with the header Hammunition writes** (the content rule `hardware unapply`
uses, D-058); a file the operator rewrote is left and named. Then
`daemon-reload`. Nothing else was changed, so nothing else is restored.

### 6e. The alternatives, and what each costs

| | Cost |
|---|---|
| **A launcher** that runs `rigctld` in a terminal, like the GPS tether (D-061): no schema change, nothing persistent | The operator starts it before every session; forgetting it reads as "rig not responding" in each program in turn; nothing restarts it when the radio is switched off and on; `doctor` can say only whether it happens to be running |
| **An XDG autostart entry** (`~/.config/autostart/`) | Starts with a graphical login only (not over SSH, not on a headless Pi); no restart, no binding to the radio's port, no `is-enabled` to report; each desktop honours it slightly differently (D-060 measured three) |
| **A system service** with `User=` (what ETC ships, disabled until `et-radio` starts it) | Root to write and to change, for a value that lives in one operator's home; runs with nobody logged in, which is the one thing it does better, and linger (question 7) gives the user service the same |

## 7. Each CAT-capable program, configured once

Every program below can reach `rigctld` as *Hamlib NET rigctl*, hamlib model
2, at `127.0.0.1:4532`. The question per program is only where that is
written, and the Q-022 #1 ruling decides it: **a block where the program
does not rewrite its own file; a page where it does.**

| Program | Speaks to `rigctld` | Where it keeps the setting (measured) | Verdict |
|---|---|---|---|
| WSJT-X, JTDX, JS8Call | links hamlib | Qt INI: `CATNetworkPort`, `PTTMethod`, `CATHandshake`, `PTTport` (strings); `PTTMethod` is a Qt-serialised enum (`PTT_method_CAT`) and the file is rewritten on exit | **Page** (ruled) |
| MSHV | its binary carries *Hamlib NET rigctl* | not read | **Page** |
| fldigi (and flmsg, flamp through it) | links hamlib; also its own flrig client | `fldigi_def.xml`: `CHKUSEHAMLIBIS`, `HAMRIGMODEL`, `HAMRIGDEVICE`, `HAMRIGBAUDRATE`; `FLRIG_IP_ADDRESS`, `FLRIG_IP_PORT`; rewritten on exit | **Page** (ruled) |
| gpredict | its own TCP client, no hamlib | a radio file of its own under `~/.config/Gpredict/hwconf/` (`.rig`), keys `Host`, `Port`, `VFO_UP`, `VFO_DOWN`, `LO`, `LO_UP`, `SIGNAL_AOS`, `SIGNAL_LOS`, `VERSION` (strings); the type and PTT keys from gpredict's source, **not read**; written by gpredict only when the operator edits radios | **Block**: a new whole file, `hammunition.rig`, `Host=localhost`, `Port=4532`, deferred with the service. Loaded by gpredict before it ships, as #153 did for the QTH file |
| tlf | links hamlib | `logcfg.dat`: `RIGMODEL`, `RIGPORT`, `RIGSPEED`, `RIGCONF`, `RIGPTT` (strings); tlf never rewrites it | **Page now; a block if question 4 is yes.** The file is #153's whole-file block (callsign, grid); adding rig lines would defer the whole file for anyone without a rig. Whether `RIGPORT` takes `localhost:4532` for model 2 is **not measured** |
| Direwolf | links hamlib | `direwolf.conf`: `PTT RIG 2 localhost:4532` (its own errors say "A rig number, not a name, is required here") | **Page.** Same whole-file problem as tlf, and the packet radio is often not the station's CAT rig (a VHF set on a Digirig) |
| Pat | its own `rigctld` client (`wl2k-go`) | `config.json`: `hamlib_rigs` → `{name: {address, network, VFO}}`, then `rig` and `ptt_ctrl` per transport (`ardop`, `varahf`, …) (JSON tags in the binary); edited by `pat configure` and its web settings | **Page now.** A JSON merge is a `config_files` mode that does not exist (question 5) |
| FreeDATA 0.18.2 | its own client | `~/.config/FreeDATA/config.ini`: `[RADIO] control = rigctld`, with `[RIGCTLD] ip = 127.0.0.1`, `port = 4532` already the shipped defaults; `rigctld_bundle` starts a `rigctld` of its own | **Page**, one setting: *rigctld*, never *rigctld_bundle* (it would take 4532) |
| Mercury | links hamlib | no file; `-R <model> -A <device>` on its command line | **Page**: key through Pat's `rig`, or `-R 2 -A 127.0.0.1:4532` (**not measured**) |
| CQRLOG | its own client; starts its own `rigctld` | per radio: `RunRigCtld`, `RigCtldPort`, `RigCtldArgs`, host, model (strings) | **Page**, and the important line: untick *Run rigctld*, or it starts a second one on 4532 |
| QLog, KLog, xlog, QSSTV, FreeDV, PyQSO, not1mm | link hamlib (the first five measured) | each its own settings dialog | **Page** |
| SuperSDR, kel-agent, OpenHamClock's rig bridge | `rigctld` clients by their docs | command line or their own settings | **Page** |
| Xastir, YAAC | **no CAT** (§2) | — | Not consumers: they key through Direwolf |
| ardopcf | no hamlib | — | Keyed by Pat's `rig`, a serial line, or VOX |

The page is `docs/guides/rig-control.md`, whose program table already gives
these answers; it changes from "start `rigctld` by hand" to "set the three
values, and the service is there", and gains the rows above that it lacks.

## 8. Choosing flrig instead

flrig opens the port itself and shows a panel. It stays in `station`, and
choosing it is one station value:

```sh
hammunition station set --rig-owner flrig    # or rigctld, the default when unset
```

With `rig_owner: flrig`, `rig-service` is not deferred but **skipped by
name** ("the station's rig is owned by flrig"), and an already-enabled
service is disabled and its file removed by the same reinstall. flrig is
then configured in its own dialog (it keeps the radio, port and speed in its
own files and rewrites them, so a page, as Q-022 #1 ruled), with the same
three values `station show` prints. Every program then points at flrig:
*FLRig* (hamlib model 4) at `127.0.0.1:12345` for the hamlib-linked
programs, fldigi's own flrig tab, Pat and FreeDATA's flrig settings.

**Not proposed, for the bench to measure:** keeping 4532 for everyone by
running the service as `rigctld -m 4 -r 127.0.0.1:12345`, so flrig owns the
port and every program's setting is the same either way. It needs flrig
running before `rigctld` opens, which a login service cannot promise, and
neither `-R` nor flrig's start-up order has been measured.

`-R` (close the radio while no client is connected) is not used: it would
let a second program open the port between clients, which is exactly the
failure one owner exists to prevent.

## 9. What `doctor` checks

Read-only, and **never a command that keys the transmitter** (no `T`, no
`set_` anything):

| Check | How | Says |
|---|---|---|
| Station complete | the three values, and `rig` in the catalog | which `station set` flag is missing |
| Service | `systemctl --user is-enabled` and `is-active hammunition-rigctld` | not installed / disabled / failed, with `journalctl --user -u hammunition-rigctld -n 20` |
| Arguments match the station | the running `rigctld`'s `/proc/<pid>/cmdline` against model, device and speed | "station says 38400, rigctld runs at 4800: reinstall `rig-service`" |
| Listening on loopback only | `/proc/net/tcp` and `tcp6`: 4532 bound to 127.0.0.1, nothing else on it | a second listener (CQRLOG's own, FreeDATA's bundle) by process name where it is the operator's |
| Daemon answering | connect to `127.0.0.1:4532`, send `\dump_state`, read the reply's model line | the reply format is from hamlib's NET rigctl client, **checked against a dummy `rigctld` in the test suite**, not yet against a radio |
| Radio answering | `f` (read the frequency) | a timeout means speed, model or cable, in that order; the speed in the radio's menu cannot be read from here, so "baud matching" is this answer, never a claim about the menu |
| Device present | the by-id path resolves to a tty | "switch the radio on" (the service starts with it, §5) |
| Port not held elsewhere | the operator's own processes with that tty open (`/proc/*/fd`) | "flrig (pid N) has the port open: `rig_owner` says rigctld" |
| Groups | the user manager's `Groups:` (`/proc/<MainPID of user@UID.service>/status`) holds the group that owns the tty | "log out of every session; the user manager still has the groups from before the install" |
| hamlib knows the model | `rigctl -l` on this machine lists `hamlib_model` | the FTX-1's `1051` exists in 4.7.2 and is *Beta*; whether older targets list it is per target |

## 10. Disclosure, in one place

The plan (§6b) prints the file, the command line with the serial elided,
the listener, the sentence that any local program can key the transmitter
and that `rigctld` has no password, when it starts, the three `systemctl`
commands, how to inspect it and how to reverse it. `station set` prints the
backend's speed range and the reminder to match the radio's menu. The
`--json` plan carries a `user_services` array with the same fields and the
values' names, never their values (D-059); `doctor --json` carries §9's
checks. `docs/reference/json-interface.md` is regenerated in the
implementation.

## 11. Security, said plainly

- **Loopback is not per-user.** Any local account and any local process can
  connect to 127.0.0.1:4532 and key the transmitter; `rigctld -A` is "NOT
  IMPLEMENTED" by its own help. On a single-operator laptop that is the
  operator's own software; on a shared machine it is a transmitter anyone
  logged in can key. Said in the plan, the page, and `rig-service`'s
  `known_problems`.
- **A web page can reach it.** `rigctld` reads newline-separated commands,
  and a browser's HTTP request to `127.0.0.1:4532` is newline-separated
  text. Whether a request body's lines reach the command parser after
  `rigctld` rejects the request line, and whether the browsers on the
  targets block port 4532 or private-network requests, are **not measured**.
  The test suite sends an HTTP POST with a `T 1` body to a dummy `rigctld`
  and records whether PTT changes; if it does, this design does not ship
  until the risk has an answer, and the candidates (a filtering front on
  4532 that drops a connection whose first line is HTTP; a different port is
  not one) go back to the maintainer.
- **Nothing listens beyond loopback**: `-T 127.0.0.1` is fixed in the
  block, and `listens` refuses any other address at load.
- **No root.** The service runs as the operator with `NoNewPrivileges=yes`;
  other hardening (`RestrictAddressFamilies`, `PrivateTmp`) is not added
  until it has been run, because user managers support only part of it.

## 12. The bench, and what stays unmeasured until it has run

The FT-991A on the field laptop is the first rig and the evidence
D-073 needs before it is accepted; results go to
`docs/reference/bench-verification-5430.md`, summarised, with no serial
and no callsign quoted.

1. Capture the FT-991A's USB shape: the CP2105's identifier and product
   strings, `reports_serial`, which `-ifNN-` is CAT, the codec's
   identifier. Close the manifest's `identification_gap`.
2. `rigctl -m 1035 -r <by-id> -s <menu rate> f` by hand, then the service:
   start at login, `\dump_state`, `f`, `doctor` clean.
3. Switch the radio off and on: does `BindsTo` stop the service, and does
   the `.wants` link on the device unit start it again (§5)?
4. Log out and in; suspend and resume; a membership added by the install.
5. Each program in §7 against the service, starting with WSJT-X (CAT PTT
   on a dummy load), fldigi, gpredict's written `.rig` file, Pat, FreeDATA.
6. The flrig route: no service, everything at 12345.

Until then the docs claim nothing about the service's behaviour with a
radio, and the hardware page says `untested`.

## 13. Found while measuring, not fixed here

- **The `rigctl` launcher shadows `rigctl`.** `libhamlib-utils`' generated
  launcher is installed as `~/.local/bin/rigctl`, ahead of `/usr/bin` on the
  operator's `PATH`, and runs `rigctl -m 1` then waits for Enter whatever it
  is given. On the field laptop `type -a rigctl` finds it first, so every
  guide's `rigctl -l | grep …` opens the dummy rig's shell instead of
  listing models. A launcher must never take the name of a command on
  `PATH`; that fix, and a test that every launcher's name is not a command
  its own packages ship, is its own PR, before this one.
- `docs/guides/rig-control.md` and `docs/guides/digital-modes.md` say
  Hammunition does not run `rigctld`; they change with the implementation,
  not before.

## 14. Out of scope

Several radios on one station (one `rig` now; the block allows a second
service on another port later); Bluetooth CAT setup (`rfcomm` binding needs
root and is the operator's; a `bluetooth_rfcomm` radio is carried with that
said); `rotctld` for rotators (the same shape, after this has run);
`ser2net` and a rig on another machine (report §A2.4, its own unit);
writing any setting into a program that rewrites its own file; role
symlinks such as ETC's `/dev/et-cat` (D-042 rule 3); the per-radio wrappers
that configure each application for the active radio (D-042 rule 2: the
config lives on the application's manifest, not in a wrapper).

## 15. Questions for the maintainer

1. **The schema:** a `user_services` block beside `config_files` (§6), not
   a `system_modifications` kind? *Recommended.*
2. **The carrying unit:** a new `rig-service` unit in `station`, rather
   than the service on `libhamlib-utils` itself? *Recommended*, so an
   operator with no radio is not shown a deferral for hamlib.
3. **The fourth value:** `rig_owner` (`rigctld` default, or `flrig`), so
   choosing flrig is a station setting rather than a hand-disabled service
   that the next install re-enables? *Recommended.*
4. **Optional lines in a whole file:** tlf and Direwolf would each gain rig
   lines only if one file could be written two ways — a `config_files`
   entry with ordered variants, the first whose station values are all
   present written, a variant without the rig still a complete file. Build
   that, or keep both on the page? *Recommended: the page for now*; tlf is
   the only gain, and Direwolf's radio is often not the CAT rig.
5. **Pat:** a JSON-merge `config_files` mode (set `hamlib_rigs` and one
   transport's `rig`, touch nothing else) is the only way Pat gets a block.
   Worth a mode of its own, or the page? *Recommended: the page.*
6. **The UV-50PRO and radios without CAT:** a PTT-only service (the dummy
   model keyed on an interface's RTS line, §3c) as a later option, after
   the FT-991A has run? *Recommended: later, measured first.*
7. **Linger:** offer `loginctl enable-linger` (a root step, disclosed) for a
   station that must run unattended, or leave the service to logged-in
   sessions? *Recommended: leave it*, and say so in the page.
8. **The cross-protocol risk (§11):** if the dummy-`rigctld` test shows a
   browser's request can key PTT, is a small loopback filter in front of
   4532 acceptable, or does the service wait until upstream answers?
9. **A radio not in the catalog:** accept `--rig hamlib:<model>` checked
   against this machine's `rigctl -l`, so an IC-7300 owner is not blocked
   until someone writes its manifest? *Recommended*, with the plan saying
   the catalog has no notes for it.
