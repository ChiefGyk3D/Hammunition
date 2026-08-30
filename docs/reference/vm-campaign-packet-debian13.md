# VM campaign — packet profile on Debian 13

The first automated campaign (`scripts/vm_campaign.py`), run 2026-08-30
against a freshly-reset `debian13_dev`, engine `3f79c0c` then `157a125`+.
The packet profile is D-008's reason for existing — the 73Linux delta's
EMCOMM core — and this is its first whole-profile verification anywhere.

## Result: 21 of 21 installed and confirmed

The first pass scored 17/21 with all four failures sharing one cause worth
the price of admission: **every git-method unit failed at `git init` on a
fresh baseline, because no earlier machine had ever lacked git** — each
previous VM carried it as a leftover of manual testing. The engine now owns
its own tool dependencies (a git build plans `git` into the apt set, a
patched source build plans `patch`), and the four units — qtsoundmodem,
qttermtcp, linbpq, ardopcf — installed and confirmed on the rerun, binaries
verified present and `ardopcf` answering with its version string.

Original first-pass report follows, kept verbatim as the evidence of the
finding.

---

# VM campaign report

**Date:** 2026-08-30
**Engine:** commit `3f79c0c`
**Target:** Target: Debian GNU/Linux 13 (trixie) (ID=debian, version=13, arch=x86_64)
**Units:** 21 — 17 installed+confirmed, 0 refused at plan time, 4 failed

Exit 0 is the engine's own bar: completed *and confirmed* by re-probe
(D-031). A plan-time refusal is honest coverage reporting, not a
failure — its text names what is missing.

| Unit | Outcome | Seconds |
|---|---|---:|
| `direwolf` | installed+confirmed | 4 |
| `qtsoundmodem` | FAILED | 17 |
| `qttermtcp` | FAILED | 2 |
| `ax25-tools` | installed+confirmed | 3 |
| `ax25-apps` | installed+confirmed | 2 |
| `ax25-xtools` | installed+confirmed | 2 |
| `linpac` | installed+confirmed | 2 |
| `uronode` | installed+confirmed | 2 |
| `linbpq` | FAILED | 4 |
| `pat` | installed+confirmed | 3 |
| `ardopcf` | FAILED | 1 |
| `xastir` | installed+confirmed | 5 |
| `aprsdigi` | installed+confirmed | 2 |
| `aprx` | installed+confirmed | 2 |
| `a2d` | installed+confirmed | 7 |
| `axmail` | installed+confirmed | 2 |
| `ax25mail-utils` | installed+confirmed | 2 |
| `ampr-ripd` | installed+confirmed | 2 |
| `minimodem` | installed+confirmed | 2 |
| `xygrib` | installed+confirmed | 3 |
| `tmd710-tncsetup` | installed+confirmed | 2 |

## Failures

### `qtsoundmodem`

```
  $ sudo install -D -m 0755 /home/chiefgyk3d/.cache/hammunition/build/qtsoundmodem-24.45/src/QtSoundModem /usr/local/bin/qtsoundmodem
Running:
  $ sudo env DEBIAN_FRONTEND=noninteractive apt-get install --yes -- build-essential libasound2-dev libfftw3-dev libpulse-dev libqt5serialport5-dev pkg-config qt5-qmake qtbase5-dev qtbase5-dev-tools
  $ [prepare] /home/chiefgyk3d/.cache/hammunition/build/qtsoundmodem-24.45/src (removed if present, then recreated)
    created /home/chiefgyk3d/.cache/hammunition/build/qtsoundmodem-24.45/src
  $ git init --quiet /home/chiefgyk3d/.cache/hammunition/build/qtsoundmodem-24.45/src
```

### `qttermtcp`

```
  $ sudo install -D -m 0755 /home/chiefgyk3d/.cache/hammunition/build/qttermtcp-0.81/src/QtTermTCP /usr/local/bin/qttermtcp
Running:
  $ sudo env DEBIAN_FRONTEND=noninteractive apt-get install --yes -- qtmultimedia5-dev
  $ [prepare] /home/chiefgyk3d/.cache/hammunition/build/qttermtcp-0.81/src (removed if present, then recreated)
    created /home/chiefgyk3d/.cache/hammunition/build/qttermtcp-0.81/src
  $ git init --quiet /home/chiefgyk3d/.cache/hammunition/build/qttermtcp-0.81/src
```

### `linbpq`

```
  $ sudo gpasswd --add chiefgyk3d dialout
Running:
  $ sudo env DEBIAN_FRONTEND=noninteractive apt-get install --yes -- libconfig-dev libi2c-dev libjansson-dev libminiupnpc-dev libpaho-mqtt-dev libpcap-dev
  $ [prepare] /home/chiefgyk3d/.cache/hammunition/build/linbpq-25.39/src (removed if present, then recreated)
    created /home/chiefgyk3d/.cache/hammunition/build/linbpq-25.39/src
  $ git init --quiet /home/chiefgyk3d/.cache/hammunition/build/linbpq-25.39/src
```

### `ardopcf`

```
  # Install ardopcf's ardopcf as ardopcf
  $ sudo install -D -m 0755 /home/chiefgyk3d/.cache/hammunition/build/ardopcf-1.0.4.1.3/src/ardopcf /usr/local/bin/ardopcf
Running:
  $ [prepare] /home/chiefgyk3d/.cache/hammunition/build/ardopcf-1.0.4.1.3/src (removed if present, then recreated)
    created /home/chiefgyk3d/.cache/hammunition/build/ardopcf-1.0.4.1.3/src
  $ git init --quiet /home/chiefgyk3d/.cache/hammunition/build/ardopcf-1.0.4.1.3/src
```

