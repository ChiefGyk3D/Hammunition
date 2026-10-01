# The rig as station data (D-073) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the station's radio a catalog device plus five station values, and run one shared `rigctld` per operator as a systemd user service the engine renders, enables, discloses and reverses, so every program keys through `127.0.0.1:4532`.

**Architecture:** A new `rig` hardware class and a `RigBlock` on device manifests describe the radio (hamlib model + CAT port, or a `ptt_only` shape). Five station values (`rig`, `rig_device`, `rig_baud`, `rig_ptt_line`, `rig_owner`) name the operator's choice, validated against the catalog by the CLI. A new `user_services` manifest block is rendered by the engine into `~/.config/systemd/user/`, enabled with `systemctl --user`, deferred when a value is missing (D-035), skipped for flrig/VOX, and reversed on uninstall by header match. A carrying package `rig-service` holds the block and lands in the `station` profile. `--unattended` plans `loginctl enable-linger` through the existing D-056 devctl helper's new `linger on|off` verb. `doctor` gains read-only rig checks that never key.

**Tech Stack:** Python 3.11+, pydantic v2 (`Strict` base), YAML catalog, systemd user services, hamlib `rigctld`, stdlib socket/HTTP for the loopback filter, `mypy --strict`.

**Spec:** `docs/superpowers/specs/2026-10-01-rig-station-data-design.md` (read it; §15 carries the nine binding rulings).

## Global Constraints

- Catalog is **pure data, no executable logic** (CLAUDE.md). The `rig` block and `user_services` block are declarative; the engine renders unit files, no manifest writes unit syntax.
- `mypy --strict` clean; type hints throughout. Small, focused files; follow established patterns.
- Fixed enums over free strings on anything the engine acts on (the `PowerMethod`/`QuietVerb` precedent): `cat.kind`, `ptt_only.lines`, `audio`, `ptt`, `rig_owner`, `rig_ptt_line`, `user_services.listens.protocol` are closed sets.
- Nothing is defaulted except `rig_owner` (default `rigctld`), which is a mode like `map_freshness`, not a station fact (D-035).
- `-T 127.0.0.1` is fixed in the rendered unit; `listens` refuses any non-loopback address **at load**, not at plan time.
- No shell: every `exec` element is one argv word; no `;`, `|`, `$`, `%`, backtick, whitespace reaching a unit file; station values re-checked by §4's pattern **after** substitution.
- The user service runs as the operator, never through sudo (D-062); only root steps are prefixed.
- Privacy: `station show` and its JSON print the by-id path in full (operator's own screen); the plan, `doctor`, `status` and every other `--json` elide the serial. Placeholders in all docs/tests: `N0CALL`, `FN31pr`, `/dev/serial/by-id/usb-Silicon_Labs_CP2105_...-if00-port0`.
- Machine rules during execution: everything under `nice -n 19 ionice -c 3`; never launch a GUI; never `pkill`/`killall`; never sudo or a real `hardware apply`/`install`; `rigctld` only ever `-m 1` (dummy) on an **ephemeral** loopback port (port 0) — never a real serial port, never `/dev/tty*`/`/dev/serial/*`, never bind 10110/10111/4532/4632; no real systemd user units (tests use a temp `XDG_CONFIG_HOME` and a fake `systemctl`); never read `~/.config/hammunition/`.
- Commit identity `git -c user.email=19499446+ChiefGyk3D@users.noreply.github.com`; every commit ends `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`. Commit-claims hook runs on every commit: claim only what the diff shows; never state what a decision or test "now says".
- Gate test result (Task 1, already measured 2026-10-01 on hamlib 4.7.2): a browser-shaped single-write HTTP POST does **not** key the dummy; raw `T 1` does. Gate OPEN → **the loopback filter proxy is NOT built**; `rigctld` stays on 4532. Task 1 ships the regression test; the proxy tasks are not in this plan.

## Review Focus

- A by-id path containing a shell metacharacter or `..`: `station set --rig-device` must refuse it (systemd would split/expand it in `ExecStart=`); pinned in Task 6.
- `rig_baud` outside the catalogued backend's range, or any `rig_baud`/`rig_ptt_line` given for the wrong rig kind: refused at `station set`, naming the range; pinned in Task 6.
- A `rig` value whose device the catalog no longer has (a catalog change after the value was set): the plan re-checks and defers `rig-service` by reason, never templates nothing; pinned in Task 9.
- A `user_services` `exec` element that is not one argv word, or a `listens` address that is not loopback: refused at manifest load, not at plan time; pinned in Task 4.
- An operator-rewritten unit file on uninstall: left in place and named, never removed, because it no longer starts with our header; pinned in Task 11.

---

## Task 1: The browser-keying gate as a regression test

**Files:**
- Test: `tests/test_rig_gate.py` (create)

**Interfaces:**
- Produces: nothing imported elsewhere; a standalone guard. Records the spec §11 / ruling 8 result in code.

- [ ] **Step 1: Write the test.** Start a dummy `rigctld -m 1 -T 127.0.0.1 -t 0`-style daemon on a free ephemeral loopback port (bind a socket to `("127.0.0.1", 0)`, read the port, close, pass it to `rigctld`), wait for it to listen, then in one write send a browser-shaped HTTP POST whose body is `T 1\n` (request line `POST / HTTP/1.1`, `Host`, `Content-Type: text/plain`, `Content-Length`, blank line, body), read any reply, then open a fresh connection and send `t\n` and assert the reply is `0\n` (PTT unchanged — gate OPEN). Falsification in the same test: a fresh connection sending raw `T 1\n` must return `RPRT 0` and a subsequent `t\n` must return `1\n` (keyed), proving the test reaches the parser. Skip the whole test with `pytest.mark.skipif` when `shutil.which("rigctld")` is None. Terminate the daemon in a `finally`.

```python
import shutil, socket, subprocess, time
import pytest

pytestmark = pytest.mark.skipif(shutil.which("rigctld") is None, reason="hamlib not installed")

def _free_port() -> int:
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close(); return p

def _wait(port: int) -> None:
    for _ in range(100):
        try:
            socket.create_connection(("127.0.0.1", port), timeout=0.2).close(); return
        except OSError:
            time.sleep(0.05)
    raise AssertionError("rigctld never listened")

def _talk(port: int, data: bytes, settle: float = 0.5) -> bytes:
    c = socket.create_connection(("127.0.0.1", port), timeout=2)
    c.sendall(data); time.sleep(settle); c.settimeout(0.3); out = b""
    try:
        while (chunk := c.recv(4096)):
            out += chunk
    except OSError:
        pass
    c.close(); return out

def test_browser_post_does_not_key_dummy_but_raw_command_does():
    port = _free_port()
    proc = subprocess.Popen(
        ["rigctld", "-m", "1", "-T", "127.0.0.1", "-t", str(port)],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        _wait(port)
        body = b"T 1\n"
        req = (b"POST / HTTP/1.1\r\nHost: 127.0.0.1\r\n"
               b"Content-Type: text/plain\r\nContent-Length: %d\r\n\r\n" % len(body)) + body
        _talk(port, req, settle=1.0)
        assert _talk(port, b"t\n", 0.3) == b"0\n"      # gate OPEN: POST did not key
        assert b"RPRT 0" in _talk(port, b"T 1\n", 0.3) # falsification: raw command reaches parser
        assert _talk(port, b"t\n", 0.3) == b"1\n"       # and keyed
    finally:
        proc.terminate(); proc.wait()
```

- [ ] **Step 2: Run it.** `nice -n 19 .venv/bin/python -m pytest tests/test_rig_gate.py -q` → PASS (or skipped if no hamlib; on the field laptop hamlib is present, so PASS).
- [ ] **Step 3: Commit.** `feat(rig): pin the browser-keying gate — POST does not key, raw does (D-073 §11)`

---

## Task 2: The `RigBlock` schema on device manifests

**Files:**
- Modify: `src/hammunition/manifest/hardware.py` (add `RigBlock`, `RigCat`, `RigPttOnly` classes; add `rig: RigBlock | None` to `_DeviceCommon`)
- Test: `tests/test_rig_schema.py` (create)

**Interfaces:**
- Produces: `RigBlock` with `.hamlib_model: int | None`, `.cat: RigCat | None`, `.ptt_only: RigPttOnly | None`, `.audio: Literal[...]`, `.ptt: list[...]`, `.ptt_interface: str | None`; `.kind` property returning `"cat"` or `"ptt_only"`. `RigCat` with `.kind` (interface enum), `.interface: str | None`, `.baud: tuple[int,int]`, `.factory_baud: int | None`, `.handshake`. `RigPttOnly` with `.lines: list[Literal["rts","dtr"]]`, `.vox: bool`.

- [ ] **Step 1: Write failing tests.** A CAT `RigBlock` (hamlib_model + cat, no ptt_only) loads; a `ptt_only` block loads; a block with **both** `hamlib_model`/`cat` and `ptt_only` raises `ManifestError`; a block with **neither** raises; `baud` must be `[low, high]` low<=high; `RigBlock(...).kind` returns `"cat"`/`"ptt_only"`.

```python
from hammunition.manifest.hardware import RigBlock
import pytest
from pydantic import ValidationError

def test_cat_block_loads():
    rig = RigBlock.model_validate({
        "hamlib_model": 1035,
        "cat": {"kind": "usb_cp2105_dual", "interface": "00", "baud": [4800, 38400], "handshake": "hardware"},
        "audio": "builtin_usb_codec", "ptt": ["cat", "rts"], "ptt_interface": "01",
    })
    assert rig.kind == "cat" and rig.hamlib_model == 1035

def test_ptt_only_block_loads():
    rig = RigBlock.model_validate({"ptt_only": {"lines": ["rts", "dtr"], "vox": True}, "audio": "external_interface"})
    assert rig.kind == "ptt_only"

def test_cat_and_ptt_only_mutually_exclusive():
    with pytest.raises((ValidationError, ValueError)):
        RigBlock.model_validate({"hamlib_model": 1035, "cat": {"kind": "usb_cp210x", "baud": [4800, 38400], "handshake": "none"}, "ptt_only": {"lines": ["rts"]}, "audio": "none"})

def test_neither_cat_nor_ptt_only_refused():
    with pytest.raises((ValidationError, ValueError)):
        RigBlock.model_validate({"audio": "none"})
```

- [ ] **Step 2: Run → FAIL** (`RigBlock` not defined). `nice -n 19 .venv/bin/python -m pytest tests/test_rig_schema.py -q`
- [ ] **Step 3: Implement.** In `hardware.py`, add near `PowerControl`:

```python
RigInterfaceKind = Literal[
    "usb_cp2105_dual", "usb_cp210x", "usb_ftdi", "usb_cdc_acm", "usb_ch340", "bluetooth_rfcomm"
]
RigAudio = Literal["builtin_usb_codec", "external_interface", "none"]
RigPtt = Literal["cat", "rts", "dtr", "vox"]
PttLine = Literal["rts", "dtr"]


class RigCat(Strict):
    """How a CAT radio's control port is reached and driven."""
    kind: RigInterfaceKind
    interface: str | None = Field(default=None, description="Which -ifNN- port is CAT, when the chip has several.")
    baud: tuple[int, int] = Field(description="The backend's [low, high] serial-speed range, from `rigctl -m N -u`.")
    factory_baud: int | None = Field(default=None, description="The radio's out-of-box CAT rate; only when read from the radio.")
    handshake: Literal["hardware", "software", "none"]

    @model_validator(mode="after")
    def _check(self) -> "RigCat":
        lo, hi = self.baud
        if lo <= 0 or hi < lo:
            raise ManifestError(f"rig cat baud {self.baud} must be [low, high] with 0 < low <= high")
        return self


class RigPttOnly(Strict):
    """A radio with no CAT: the serial control lines that key it."""
    lines: list[PttLine] = Field(min_length=1, description="Serial control lines an interface can key it by.")
    vox: bool = Field(default=False, description="The radio can key itself on audio instead.")


class RigBlock(Strict):
    """What a radio needs from Linux and from hamlib.  D-073."""
    hamlib_model: int | None = Field(default=None, description="`rigctl -l`; the plan checks the target's hamlib lists it.")
    cat: RigCat | None = None
    ptt_only: RigPttOnly | None = None
    audio: RigAudio
    ptt: list[RigPtt] = Field(default_factory=list, description="What the radio can be keyed by; the first is the default.")
    ptt_interface: str | None = Field(default=None, description="The -ifNN- port for RTS/DTR keying, where it differs from CAT.")

    @property
    def kind(self) -> Literal["cat", "ptt_only"]:
        return "ptt_only" if self.ptt_only is not None else "cat"

    @model_validator(mode="after")
    def _exclusive(self) -> "RigBlock":
        is_cat = self.hamlib_model is not None or self.cat is not None
        if is_cat and self.ptt_only is not None:
            raise ManifestError("a rig has either a hamlib backend and a CAT port, or ptt_only, never both")
        if not is_cat and self.ptt_only is None:
            raise ManifestError("a rig block must declare either hamlib_model+cat or ptt_only")
        if is_cat and (self.hamlib_model is None or self.cat is None):
            raise ManifestError("a CAT rig needs both hamlib_model and cat")
        return self
```

Add `rig: RigBlock | None = None` to `_DeviceCommon` (with a Field describing it). Add `RigBlock` etc. to `__all__`.

- [ ] **Step 4: Run → PASS.**
- [ ] **Step 5: Commit.** `feat(rig): add the RigBlock schema for radio device manifests (D-073 §3b)`

---

## Task 3: The `rig` class and the FT-991A / UV-50PRO device manifests

**Files:**
- Create: `catalog/hardware/classes/rig.yaml`
- Create: `catalog/hardware/devices/yaesu-ft-991a.yaml`
- Create: `catalog/hardware/devices/btech-uv-50pro.yaml`
- Test: `tests/test_rig_catalog.py` (create)

**Interfaces:**
- Consumes: `load_hardware` from `hammunition.manifest.load`; `RigBlock` (Task 2).
- Produces: three catalog entries loadable by `load_hardware`.

- [ ] **Step 1: Write the class.** `catalog/hardware/classes/rig.yaml` with CC0 SPDX header, `kind: class`, `name: rig`, `groups: [dialout]`, `packages: [libhamlib-utils, flrig]`, one confirmed `usb_ids` entry for the CP2105 `10c4:ea70` with `node_kind: serial`, `ports: 2`, an `ambiguity` block (`basis: kernel_generic_driver`, evidence citing the kernel `cp210x` table and `docs/reference/usb-ambiguity.md`, `also_used_by: [FTX-1, Digirig DR-891 (D-042)]`), `evidence` ≥10 chars, and `documentation` with the D-028 sentence in `known_problems` ("the chip does not say which radio it is; the operator's selection decides, through `station set --rig`"). No `udev`, no symlink.
- [ ] **Step 2: Write the FT-991A device** (`yaesu-ft-991a.yaml`): CC0 header, `kind: device`, `name: yaesu-ft-991a`, `vendor: yaesu`, `device_class: rig`, `composite: true`, two `usb_ids` both `10c4:ea70` carrying `node_kind` (`serial` for the two CAT/PTT ports — model the CP2105's two serial interfaces; and a `sound` id for the codec) — **but** composite requires ≥2 ids each with `node_kind` set and each needs evidence; since none is measured, set `status: untested`, `identification_gap` naming the two ports' product strings, `reports_serial` unknown, and the codec identifier, `gap_closure: maintainer_hardware`. Add the `rig` block: `hamlib_model: 1035`, `cat: {kind: usb_cp2105_dual, interface: "00", baud: [4800, 38400], handshake: hardware}`, `audio: builtin_usb_codec`, `ptt: [cat, rts, dtr]`, `ptt_interface: "01"`. Each value carries a `#` comment citing `rigctl -m 1035 -u` / Yaesu docs / "not measured". Provide `documentation` (what it is, what you can do, setup_steps, known_problems, upstream_url).
  - Note on composite: if the `composite: true` + unmeasured-identifier constraints make a clean confirmed entry impossible, set `composite: false` and carry a single confirmed CP2105 id plus the `identification_gap`; the device inherits the class's id. Choose whichever loads cleanly with the real validators; record the choice in the ledger. The `rig` block does not depend on `composite`.
- [ ] **Step 3: Write the UV-50PRO device** (`btech-uv-50pro.yaml`): `name: btech-uv-50pro`, `vendor: btech`, `device_class: rig`, **no** `usb_ids` of its own (it has no USB interface), `rig: {ptt_only: {lines: [rts, dtr], vox: true}, audio: external_interface}`, `status: untested`, `identification_gap` listing the four bench items from §3d (which line keys it; nothing written on the serial line; whether starting the service keys it; VOX level), `gap_closure: maintainer_hardware`, full `documentation`. Since it has no confirmed id of its own, it relies on `device_class: rig` to satisfy the "no confirmed id" rule.
- [ ] **Step 4: Write the test.** Load each with `load_hardware`; assert the FT-991A's `rig.hamlib_model == 1035` and `rig.kind == "cat"`; the UV-50PRO's `rig.kind == "ptt_only"` and `rig.ptt_only.vox is True`; the class carries `dialout` in groups and the CP2105 id with an ambiguity block.
- [ ] **Step 5: Run → PASS.** `nice -n 19 .venv/bin/python -m pytest tests/test_rig_catalog.py tests/test_hardware.py -q`. Also run `nice -n 19 .venv/bin/python -m pytest tests/test_schema.py -q` to confirm catalog-wide validation still passes.
- [ ] **Step 6: Commit.** `feat(rig): add the rig class and the FT-991A and UV-50PRO entries, untested (D-073 §3)`

---

## Task 4: The `user_services` manifest block

**Files:**
- Modify: `src/hammunition/manifest/schema.py` (add `UserServiceListen`, `UserService`; add `user_services: list[UserService]` to `PackageManifest`; extend the `{station.*}` reference validation to cover `exec`/`binds_to_device`)
- Test: `tests/test_user_services_schema.py` (create)

**Interfaces:**
- Produces: `UserService` with `.name: str`, `.description: str`, `.when_station: dict[str,str]`, `.unless_station: dict[str,str]`, `.exec: list[str]`, `.binds_to_device: str | None`, `.listens: list[UserServiceListen]`; `.station_variables: set[str]` property (names referenced in `exec`/`binds_to_device`). `UserServiceListen` with `.protocol: Literal["tcp"]`, `.address: str`, `.port: int`.

- [ ] **Step 1: Write failing tests.** A valid CAT service loads (`exec` with `{station.rig_hamlib_model}` etc.); an `exec` element containing a space (two words) is refused at load; a `listens` address that is not loopback (`0.0.0.0`, `192.168.1.5`) is refused at load; `exec[0]` must be absolute; two entries sharing a `name` whose `when_station` conditions can both hold is refused (checked at the manifest level — put this in Task-4 test as a `PackageManifest` with two same-named services with disjoint conditions passing and overlapping failing); `.station_variables` finds `rig_hamlib_model`, `rig_device`, `rig_baud`.

```python
from hammunition.manifest.schema import PackageManifest
import pytest

def _manifest(services):
    return {"name": "rig-service", "summary": "x" * 12, "stage": "1.0",
            "install": {"method": "apt", "packages": ["libhamlib-utils"]},
            "documentation": {...minimal valid...},
            "user_services": services}
```

(Fill the minimal valid `documentation`/`install` from an existing manifest, e.g. read `catalog/packages/libhamlib-utils.yaml` for the exact required doc fields.)

- [ ] **Step 2: Run → FAIL.**
- [ ] **Step 3: Implement.** Add after `ConfigFile`:

```python
class UserServiceListen(Strict):
    protocol: Literal["tcp"] = "tcp"
    address: str
    port: int = Field(ge=1, le=65535)

    @model_validator(mode="after")
    def _loopback(self) -> "UserServiceListen":
        if self.address not in ("127.0.0.1", "::1"):
            raise ManifestError(
                f"user service listens on {self.address}:{self.port}; a rig control port "
                f"must bind loopback (127.0.0.1), never a routable address (D-073 §11)"
            )
        return self


class UserService(Strict):
    """A systemd user service the engine renders from station values.  D-073 §6.

    Not a config_files path into ~/.config/systemd/user/, because something must
    also enable it, start it, and stop it on uninstall; not a system_modifications
    kind, because those are descriptions the engine does not render and a user
    service lives in one operator's home and needs no root.
    """
    name: str
    description: str
    when_station: dict[str, str] = Field(default_factory=dict)
    unless_station: dict[str, str] = Field(default_factory=dict)
    exec: list[str] = Field(min_length=1)
    binds_to_device: str | None = None
    listens: list[UserServiceListen] = Field(default_factory=list)

    @property
    def station_variables(self) -> set[str]:
        found: set[str] = set()
        for word in self.exec:
            found |= set(STATION_REF.findall(word))
        if self.binds_to_device:
            found |= set(STATION_REF.findall(self.binds_to_device))
        return found

    @model_validator(mode="after")
    def _check(self) -> "UserService":
        if not SLUG_WITH_DASH.match(self.name):  # reuse an existing name regex; unit file base name
            raise ManifestError(f"user service name {self.name!r} must be a unit-file base name")
        if not self.exec[0].startswith("/"):
            raise ManifestError(f"user service {self.name!r}: exec[0] {self.exec[0]!r} must be an absolute path")
        for word in self.exec:
            # One argv word: no shell metacharacters and no internal whitespace.
            # {station.*} references are allowed and re-checked after substitution.
            bare = STATION_REF.sub("X", word)
            if any(c in bare for c in " \t\n;|&$`%<>") :
                raise ManifestError(
                    f"user service {self.name!r}: exec element {word!r} is not one argv word; "
                    f"no shell, no whitespace or metacharacters reach the unit file (D-073 §6a)"
                )
        return self
```

Choose the name regex: check what `SLUG` is (`schema.py` top) — `SLUG` likely forbids dashes mid-name; unit base names like `hammunition-rigctld` use dashes. If `SLUG` allows them, use it; otherwise define `_UNIT_NAME = re.compile(r"^[a-z][a-z0-9-]*$")` locally. Verify by reading the `SLUG` definition before implementing.

Add `user_services: list[UserService] = Field(default_factory=list)` to `PackageManifest` and a `PackageManifest` model-validator asserting entries sharing a `name` have `when_station`/`unless_station` that cannot both hold (a simple check: for same-named pairs, require their `when_station` to disagree on at least one shared key, e.g. `rig_kind: cat` vs `rig_kind: ptt_only`). Extend the manifest's existing station-variable validation (around line 2278, where `config_files` variables are checked against `TEMPLATE_VARIABLES`) so `user_services` variables are also checked — but **allow** the three derived-at-plan-time names `rig_hamlib_model`, `rig_kind`, `rig_ptt_line_hamlib` in addition to `TEMPLATE_VARIABLES`. Define `RIG_DERIVED_AT_PLAN = frozenset({"rig_hamlib_model", "rig_kind", "rig_ptt_line_hamlib"})` in schema.py and use it in that validator.

- [ ] **Step 4: Run → PASS.**
- [ ] **Step 5: Commit.** `feat(rig): add the user_services manifest block, loopback-only, one-argv-word (D-073 §6)`

---

## Task 5: The five station values and their validation shape

**Files:**
- Modify: `src/hammunition/station.py` (add five fields to `Station`; `RIG_OWNERS`, `PTT_LINES` constants; validation in `__post_init__`; `as_dict`/`load_station`/`prompt_for` carry them; exclude `rig_owner` from being "invented" but keep as mode)
- Test: `tests/test_station.py` (extend)

**Interfaces:**
- Produces: `Station(rig=..., rig_device=..., rig_baud=..., rig_ptt_line=..., rig_owner=...)`; these are in `STATION_FIELDS` (so `{station.rig}` etc. are template variables and `station show` prints them). `rig_baud` is `int | None`.

- [ ] **Step 1: Write failing tests.** A Station with `rig="yaesu-ft-991a"`, `rig_device="/dev/serial/by-id/usb-...-if00-port0"`, `rig_baud=38400` round-trips through save/load; `rig_device` with `..` raises `StationError`; `rig_device` with a space/`$`/`;` raises; `rig_device` not starting with `/dev/` raises (it must be an absolute path under `/dev/`); `rig_ptt_line` must be `rts`/`dtr`/`vox`; `rig_owner` must be `rigctld`/`flrig`; `rig="hamlib:3073"` is accepted as a value (catalog membership is the CLI's check, not the dataclass's). Note: the dataclass does **not** check `rig_baud` against a range (no catalog here) nor cross-field kind rules (CLI does, Task 6) — the dataclass checks only the *shape a file needs*, matching the module's stated philosophy.

- [ ] **Step 2: Run → FAIL.**
- [ ] **Step 3: Implement.** Add constants and fields:

```python
RIG_OWNERS = ("rigctld", "flrig")
PTT_LINES = ("rts", "dtr", "vox")
#: An absolute path under /dev/ of the characters udev leaves in a by-id name.
RIG_DEVICE = re.compile(r"^/dev/[A-Za-z0-9#+\-.:=@_/]+$")
#: `hamlib:<model>` or a catalog device id (lowercase slug). The CLI checks which.
RIG_VALUE = re.compile(r"^(?:hamlib:[0-9]+|[a-z0-9][a-z0-9-]*)$")
```

Fields on `Station`: `rig: str | None = None`, `rig_device: str | None = None`, `rig_baud: int | None = None`, `rig_ptt_line: str | None = None`, `rig_owner: str | None = None`. In `__post_init__`: strip/validate `rig` against `RIG_VALUE`; `rig_device` against `RIG_DEVICE` (reject `..`, whitespace, quotes, `\`, `$`, `%` — `RIG_DEVICE` already excludes them; add an explicit `..` check); `rig_ptt_line` in `PTT_LINES`; `rig_owner` in `RIG_OWNERS`; `rig_baud` must be a positive int if set. Each raises `StationError` with a sentence naming the fix.

Update `_KNOWN_KEYS` (automatic via `fields(Station)`), `STATION_FIELDS` (automatic minus `_NOT_TEMPLATES`; rig fields are template variables so do **not** add them to `_NOT_TEMPLATES`), `as_dict` (add the five, each only when set; `rig_baud` as int), `load_station` (read the five; `rig_baud` via `int(...)`), and `prompt_for`/`Station(...)` reconstruction calls (add the five kwargs). Add `rig`/`rig_device`/`rig_baud` to `PROMPTS` with sensible questions.

- [ ] **Step 4: Run → PASS.** `nice -n 19 .venv/bin/python -m pytest tests/test_station.py -q`
- [ ] **Step 5: Commit.** `feat(rig): add the five rig station values with file-shape validation (D-073 §4)`

---

## Task 6: `station set` rig flags, catalog-checked

**Files:**
- Modify: `src/hammunition/cli/main.py` (`cmd_station_set`: add flags and catalog validation; the parser in `build_parser`)
- Create: `src/hammunition/rig.py` (a small pure module: `check_rig_value`, `check_rig_baud`, resolving a rig value against loaded hardware + this machine's hamlib model list; keeps `station.py` free of the catalog)
- Test: `tests/test_rig_cli.py` (create), `tests/test_rig_resolve.py` (create)

**Interfaces:**
- Consumes: `load_hardware`, `RigBlock` (Task 2), `Station` (Task 5).
- Produces: `hammunition.rig.resolve_rig(value, devices) -> RigResolution` (`.kind`, `.hamlib_model`, `.baud_range: tuple[int,int] | None`, `.manifest_name: str | None`, `.uncatalogued: bool`); `check_rig_baud(baud, range) -> None | str`; a function that lists this machine's hamlib models (for `hamlib:<model>`), parameterised with a `model_lister` callable so tests pass a fake (never shelling out in a unit test).

- [ ] **Step 1: Write failing tests** for `hammunition.rig`: `resolve_rig("yaesu-ft-991a", devices)` returns kind `cat`, model 1035, baud range `(4800, 38400)`; `resolve_rig("btech-uv-50pro", devices)` returns kind `ptt_only`, model None; `resolve_rig("hamlib:3073", devices, model_lister=lambda: {3073: (1200, 115200)})` returns uncatalogued cat with model 3073 and range from the lister; `resolve_rig("not-a-rig", devices)` raises with a message naming the rig devices; `resolve_rig("hamlib:9999", devices, model_lister=lambda: {})` raises (not in this machine's hamlib). `check_rig_baud(4800, (4800, 38400))` ok; `check_rig_baud(2400, (4800, 38400))` returns a sentence naming the range.
- [ ] **Step 2: Run → FAIL.**
- [ ] **Step 3: Implement `hammunition/rig.py`** — a pure module: parse `hamlib:<n>`; look the value up among device manifests whose `rig` block is set; derive kind/model/baud; for `hamlib:` use the `model_lister` (default reads `rigctl -l` via a subprocess helper that lives here but is injected in tests). Add `RigResolution` dataclass.
- [ ] **Step 4: Wire `cmd_station_set`.** Add argparse flags `--rig`, `--rig-device`, `--rig-baud` (int), `--rig-ptt-line` (choices rts/dtr/vox), `--rig-owner` (choices rigctld/flrig), `--unattended`/`--no-unattended` (store_true/store_false into one attr, default None), `--clear-rig` (store_true). In the handler, when `--rig`/`--rig-device`/etc. are given: load hardware, `resolve_rig`, and enforce the §4 table cross-field rules in the CLI:
  - `rig_baud` required-range-check for a CAT rig; **refused** for a PTT-only rig ("no data crosses the line").
  - `rig_ptt_line` **required** for a PTT-only rig, **refused** for a CAT rig.
  - For `hamlib:<model>`, `rig_baud` mandatory; print the "unmeasured here" note.
  - `rig_owner: flrig` with a PTT-only rig refused.
  - Warn (not refuse) when `rig_device` is not under `/dev/serial/by-id/`, when its `-ifNN-` differs from the manifest's `cat.interface`, and when the path does not currently exist.
  - On `--rig` for a CAT rig, print the backend's baud range and "read the radio's CAT RATE menu".
  - `--clear-rig` removes all five. `--unattended`/`--no-unattended` is Task 12 (store the flag, handle there).
  Build the new `Station(...)` with the five values threaded through alongside the existing ones; save; print what was set (eliding nothing — this is `station set`, the operator's own screen; but do not echo the device path's serial in any summary that `status`/plan would reuse — here it is fine to print to the operator).
- [ ] **Step 5: Write the CLI test** (`tests/test_rig_cli.py`): drive `cmd_station_set` with a fake args namespace and a temp `XDG_CONFIG_HOME`/`owner`, pointed at a test catalog (or monkeypatch `find_catalog`/`load_hardware` to return the three Task-3 entries); assert refusals and acceptances per the §4 table. Use the real catalog entries from Task 3 via `find_catalog`.
- [ ] **Step 6: Run → PASS.** `nice -n 19 .venv/bin/python -m pytest tests/test_rig_cli.py tests/test_rig_resolve.py -q`
- [ ] **Step 7: Commit.** `feat(rig): station set --rig/--rig-device/--rig-baud/--rig-ptt-line/--rig-owner, catalog-checked (D-073 §4)`

---

## Task 7: `station show` and its JSON carry the rig values

**Files:**
- Modify: `src/hammunition/interface/station.py` (`StationDocument` + `build_station` + `render_station`)
- Test: `tests/test_json_station_hardware.py` or `tests/test_station.py` (extend), `tests/test_rig_cli.py` (extend)

**Interfaces:**
- Produces: `StationDocument` with `rig`, `rig_device`, `rig_baud`, `rig_ptt_line`, `rig_owner` fields (full by-id path in this document — operator's own screen, per §4 privacy; the elision happens in the plan/doctor/status views, not here).

- [ ] **Step 1: Write failing test.** `build_station(path, Station(rig="yaesu-ft-991a", rig_device="/dev/serial/by-id/usb-...-if00-port0", rig_baud=38400))` → document carries them; `render_station` prints a `rig` line and the device path in full; a station with no rig renders as before (no rig lines, or "(not set)" consistent with existing fields).
- [ ] **Step 2: Run → FAIL.**
- [ ] **Step 3: Implement.** Add the five `described(...)` fields to `StationDocument`; set them in `build_station`. `render_station` already iterates `STATION_FIELDS` for scalar values — the three scalar rig fields (`rig`, `rig_device`, `rig_baud`→str, `rig_ptt_line`, `rig_owner`) are in `STATION_FIELDS` so they appear automatically; confirm the "nothing set" guard still triggers only when truly empty (add the rig fields to that guard's `any(...)`).
- [ ] **Step 4: Run → PASS.**
- [ ] **Step 5: Commit.** `feat(rig): station show and its JSON carry the rig values (D-073 §4)`

---

## Task 8: The `rig-service` carrying package and the `station` profile

**Files:**
- Create: `catalog/packages/rig-service.yaml`
- Modify: `catalog/profiles/station.yaml` (add `rig-service` to packages, document it)
- Create: `catalog/packages/.../` n/a; Test: `tests/test_rig_service_manifest.py` (create)

**Interfaces:**
- Consumes: the `user_services` schema (Task 4).
- Produces: a loadable manifest named `rig-service` carrying the two `user_services` entries from spec §6a, `depends: [libhamlib-utils]`, no launcher.

- [ ] **Step 1: Write the manifest.** `catalog/packages/rig-service.yaml`, CC0 header. It installs nothing of its own by apt beyond its dependency; use the minimal install method the schema allows for a unit that is only a carrier — check whether an empty/`apt` block with `packages: []` is valid; if a manifest must install at least one package, set `install.method: apt` `packages: [libhamlib-utils]` and `depends: [libhamlib-utils]` (idempotent). Carry the two `user_services` entries verbatim from spec §6a (CAT and PTT-only), with `when_station`/`unless_station`, `exec`, `binds_to_device`, `listens: [{protocol: tcp, address: 127.0.0.1, port: 4532}]`. Full `documentation` (what it does, why, depends-on, known_problems naming the §11 loopback-is-not-per-user caveat, upstream_url = hamlib). Add `status` and an `update` block if the schema requires one (check an existing simple manifest for the required fields).
- [ ] **Step 2: Add to the station profile.** Insert `rig-service` into `catalog/profiles/station.yaml` packages with a comment (one shared `rigctld` the operator's programs key through; deferred by name when no rig is set — an operator with no radio never sees a deferral for hamlib). Extend `manual_configuration` prose to mention `station set --rig`.
- [ ] **Step 3: Write the test.** Load the catalog (`load_all`); assert `rig-service` is present, carries two `user_services`, and that the `station` profile lists it. Assert the two entries' conditions cannot both hold (cat vs ptt_only).
- [ ] **Step 4: Run → PASS.** `nice -n 19 .venv/bin/python -m pytest tests/test_rig_service_manifest.py tests/test_schema.py -q`
- [ ] **Step 5: Commit.** `feat(rig): add the rig-service carrying unit to the station profile (D-073 §5)`

---

## Task 9: Planning the user services — render, substitute, defer, skip

**Files:**
- Create: `src/hammunition/userservice.py` (pure rendering: substitution map from station + rig resolution, the `.service` file body, defer/skip decisions)
- Modify: `src/hammunition/plan.py` (`InstallPlan.user_services` field; `_plan_user_services` analogous to `_plan_config`; call it in `resolve`)
- Test: `tests/test_user_services_plan.py` (create)

**Interfaces:**
- Produces: `PlannedUserService` (name, description, unit file body, the rendered `exec` argv, filled-from variable names, listens, binds_to_device resolved) and reuses `Deferral`. `render_unit_file(name, description, exec_argv, binds_to_device) -> str` producing the §5 unit text with the fixed Hammunition header, `[Unit]` (`BindsTo`/`After`/escaped device unit), `[Service]` (`ExecStart`, `Restart=on-failure`, `RestartSec=5`, `NoNewPrivileges=yes`), `[Install]` (`WantedBy=default.target` and the device unit). A helper `device_unit_name(by_id_path) -> str` doing systemd's `\x..` escaping of the `dev-serial-by\x2did-...device` unit name (reuse `systemd-escape` logic in pure Python; test it against a known mapping).

- [ ] **Step 1: Write failing tests.**
  - `plan_user_services(rig_service_manifest, station=Station(rig="yaesu-ft-991a", rig_device=DEV, rig_baud=38400), devices=...)` returns one planned service whose `exec` argv is `/usr/bin/rigctld -m 1035 -r DEV -s 38400 -T 127.0.0.1 -t 4532` and whose unit body contains that `ExecStart`, the `BindsTo=` device unit, `NoNewPrivileges=yes`, and the header's first line.
  - With `rig_device` unset → a `Deferral` naming `rig_device` (and `rig_baud`), no planned service.
  - With `rig_owner="flrig"` → skipped (a note "owned by flrig"), no planned service, no deferral.
  - With a PTT-only rig and `rig_ptt_line="vox"` → skipped ("keyed by VOX").
  - With a PTT-only rig and `rig_ptt_line="rts"` → `exec` is `/usr/bin/rigctld -m 1 -p DEV -P RTS -T 127.0.0.1 -t 4532`.
  - With `rig="hamlib:3073"` and no manifest → service planned with model 3073, and a note that the radio is unmeasured here.
  - With `rig` naming a device no longer in the catalog → a `Deferral` whose `why` says the catalog no longer has it (not a silent empty template).
  - Post-substitution safety: if a (hypothetical) station value contained a space or `$`, rendering **raises** (re-check §4 pattern after substitution).
- [ ] **Step 2: Run → FAIL.**
- [ ] **Step 3: Implement `userservice.py`.** The condition evaluation: `when_station`/`unless_station` map keys to expected values, evaluated against a dict that includes `rig_kind`, `rig_owner`, `rig_ptt_line`. The substitution map: `{station.rig_device}`→device, `{station.rig_baud}`→str(baud), `{station.rig_hamlib_model}`→str(model), `{station.rig_ptt_line_hamlib}`→`RTS`/`DTR`. Resolve the rig via `hammunition.rig.resolve_rig`. Defer (reuse `Deferral`, `kind="config"`) when a needed station value is missing (per kind: cat needs rig,rig_device,rig_baud; ptt_only needs rig,rig_device,rig_ptt_line), or when the rig value no longer resolves. Skip (return a note, not a deferral) for flrig / vox. After substitution, re-run the §4 device pattern / argv-word check and raise `PlanError`/`ManifestError` on violation.
- [ ] **Step 4: Wire into `plan.py`.** Add `user_services: tuple[PlannedUserService, ...] = ()` and keep deferrals flowing into `InstallPlan.deferrals`. In `resolve`, after config planning, call `_plan_user_services` over manifests that carry `user_services`, passing the station and loaded devices. The `resolve` signature may already take `station`; if it needs the hardware catalog, thread it through (follow how `_plan_config` gets `station`). Keep `station.py` free of the catalog — the rig resolution lives in `hammunition.rig`.
- [ ] **Step 5: Run → PASS.** `nice -n 19 .venv/bin/python -m pytest tests/test_user_services_plan.py tests/test_plan.py -q`
- [ ] **Step 6: Commit.** `feat(rig): plan the rig user service — render, substitute, defer, skip (D-073 §6)`

---

## Task 10: Executing the user services — write, enable, and the plan disclosure

**Files:**
- Modify: `src/hammunition/execute.py` (`user_service_steps(plan, ...)`; call it in `commands_for` after `config_steps`; log `user_service_written`/`user_service_enabled`)
- Modify: `src/hammunition/interface/plan.py` (a `UserServiceView` in the install plan view; `build_install_view` + `render_plan_view` print the §6b block, serial elided)
- Test: `tests/test_user_services_execute.py` (create), `tests/test_json_plan.py` (extend)

**Interfaces:**
- Consumes: `PlannedUserService` (Task 9), the operator-aware writer `write_operator_config`/`open_operator_dir`, `Command`.
- Produces: steps that (1) write `~/.config/systemd/user/<name>.service` as the operator with our header via the `O_NOFOLLOW` writer, (2) `systemctl --user daemon-reload`, (3) `systemctl --user enable <name>.service`, (4) `systemctl --user restart <name>.service` (only when the device path is present). As the operator (never sudo); when run as root with an operator known, `systemctl --user --machine=<operator>@.host`.

- [ ] **Step 1: Write failing tests.** With a planned CAT service and a fake runner + temp `XDG_CONFIG_HOME`, `user_service_steps` yields: a write Action/Command putting the unit body at the temp path, then `systemctl --user daemon-reload`, `enable`, `restart`. Assert the `systemctl` commands are **not** `requires_root` (run as operator). Assert the restart step is present only when the device path exists (pass an existing temp file as the device for that case; absent for the other). Assert the plan view's rendered lines contain `writes ~/.config/systemd/user/hammunition-rigctld.service`, `filled from: rig, rig_device, rig_baud`, the `listens 127.0.0.1:4532 — any program ... can key the transmitter ... no password`, and that the printed `ExecStart`/device path has the **serial elided**.
- [ ] **Step 2: Run → FAIL.**
- [ ] **Step 3: Implement.** `user_service_steps`: for each `plan.user_services`, write the file through `write_operator_config` (reuse the staging+`install` pattern `config_steps` uses, or the operator writer directly), then append the three/four `systemctl --user` `Command`s with `requires_root=False`. Detect root+operator to add `--machine=<op>@.host` (follow D-062's split). Record log entries. In `commands_for`, insert `commands.extend(user_service_steps(plan, ...))` right after `config_steps`. Add the plan view + renderer. Elide the serial using the same helper the plan uses elsewhere (grep for existing serial-eliding; if none, add a small `elide_serial(path)` in `hammunition/rig.py` using the `usb-..._<serial>-ifNN` shape, replacing the serial run with `…`).
- [ ] **Step 4: Run → PASS.** `nice -n 19 .venv/bin/python -m pytest tests/test_user_services_execute.py tests/test_json_plan.py -q`
- [ ] **Step 5: Commit.** `feat(rig): write and enable the rig user service, disclosed in the plan (D-073 §6b,§6c)`

---

## Task 11: Reversing the user service on uninstall

**Files:**
- Modify: `src/hammunition/execute.py` (`artifact_removal_steps`/`run_removal`: disable + remove-if-ours the unit file)
- Modify: the removal planning (wherever uninstall decides a unit's artifacts) to include user-service files owned by this engine
- Test: `tests/test_user_services_execute.py` (extend) or `tests/test_removal*.py`

**Interfaces:**
- Produces: on `uninstall rig-service`: `systemctl --user disable --now hammunition-rigctld.service`, then remove the file **only if** it starts with the Hammunition header (the D-058 content rule `hardware unapply` uses), else leave and name it; then `daemon-reload`. Linger untouched.

- [ ] **Step 1: Write failing tests.** Removal of a unit whose file starts with our header: steps include `disable --now`, remove the file, `daemon-reload`. A file the operator rewrote (no header): a step/log line names it as left in place; the file is not removed.
- [ ] **Step 2: Run → FAIL.**
- [ ] **Step 3: Implement.** Follow how uninstall reverses config files / hardware unapply's header-match removal. Reuse the header constant from Task 9/10.
- [ ] **Step 4: Run → PASS.**
- [ ] **Step 5: Commit.** `feat(rig): uninstall disables the rig service and removes only our own unit file (D-073 §6d)`

---

## Task 12: `--unattended` via the devctl `linger` verb

**Files:**
- Modify: `src/hammunition/cli/devctl.py` (`linger on|off` verb, acting on the caller's uid)
- Create: `src/hammunition/hardware/linger.py` (pure: plan + record `/etc/hammunition/linger.yaml`, the `loginctl enable-linger`/`disable-linger` command, reading the record)
- Modify: `src/hammunition/hardware/polkit.py` (widen the action description/message wording to include keeping services running after logout)
- Modify: `src/hammunition/cli/main.py` (`cmd_station_set --unattended/--no-unattended`: disclose what linger keeps alive, call the helper; thread into `hardware unapply`)
- Modify: `src/hammunition/cli/main.py` (`cmd_hardware_unapply`: also `linger off` if our record says we turned it on)
- Test: `tests/test_devctl.py` (extend), `tests/test_linger.py` (create)

**Interfaces:**
- Produces: `hammunition-devctl linger on|off`; it reads the caller's uid from `PKEXEC_UID`/`SUDO_UID`/`getuid` (never a name from argv), runs `loginctl enable-linger <uid-name>`, and writes `/etc/hammunition/linger.yaml` (root 0644, `atomic_write`) recording the uid and whether linger was already on. `plan_linger(on: bool, uid: int, already_on: bool) -> LingerPlan`; `read_linger_record() -> LingerRecord | None`.

- [ ] **Step 1: Write failing tests** (pure, no root): `plan_linger(True, uid, already_on=False)` yields a `loginctl enable-linger <name>` command and a record write marking it ours; `plan_linger(True, uid, already_on=True)` records "not ours" and does not plan a disable-capable record; `plan_linger(False, ...)` only disables if the record says ours. The record round-trips through a temp file. The polkit XML now contains the widened wording (assert `policy_xml()` mentions keeping services running after logout). Verify (string assertion) that `linger` acts on the uid, not an argv name.
- [ ] **Step 2: Run → FAIL.**
- [ ] **Step 3: Implement** `linger.py` (pure, D-058 `atomic_write`/`dir_lock` under `/etc/hammunition`), the devctl `linger` subparser + handler (determine uid: `int(os.environ.get("PKEXEC_UID") or os.environ.get("SUDO_UID") or os.getuid())`, resolve name via `pwd`), widen `policy_xml` description/message (keep the action id, path, defaults unchanged — only the human text widens), and `cmd_station_set` disclosure + call, and `cmd_hardware_unapply` reversal. The disclosure lists enabled user units via `systemctl --user list-unit-files --state=enabled` (gathered in the CLI, passed for display; in tests, injected) and states the transmitter-keyable-after-logout consequence.
- [ ] **Step 4: Run → PASS.** `nice -n 19 .venv/bin/python -m pytest tests/test_devctl.py tests/test_linger.py -q`
- [ ] **Step 5: Commit.** `feat(rig): opt-in --unattended through a devctl linger verb behind the existing polkit action (D-073 §5a)`

---

## Task 13: The gpredict radio config block

**Files:**
- Modify: `catalog/packages/gpredict.yaml` (add a `config_files` whole-file block writing `~/.config/Gpredict/hwconf/hammunition.rig`, templating `{station.rig_device}` so it defers with the rig per D-035)
- Test: `tests/test_config_blocks.py` (extend) or `tests/test_rig_gpredict.py` (create)

**Interfaces:**
- Consumes: existing `config_files` engine (no engine change).
- Produces: a radio file `Host=localhost`, `Port=4532`, the gpredict keys from §7 (`VFO_UP`/`VFO_DOWN`/`LO`/`LO_UP`/`SIGNAL_AOS`/`SIGNAL_LOS`/`VERSION`), with a comment line naming the rig via `{station.rig_device}` so the file is deferred until the rig is configured.

- [ ] **Step 1: Read** `catalog/packages/gpredict.yaml` to confirm it exists and its current shape (it may be a `.yaml` present among the 295; if gpredict is not catalogued, skip this task and record it as a deferred-minor). 
- [ ] **Step 2: Write failing test.** With a station having `rig_device` set, planning gpredict yields a config file whose body contains `Host=localhost` and `Port=4532`; with no rig set, gpredict defers the file naming `rig_device`.
- [ ] **Step 3: Run → FAIL.**
- [ ] **Step 4: Implement** the `config_files` block (whole-file, `backup_existing: true`). Body is literal gpredict `.rig` text plus a leading `# rig {station.rig_device}` comment so `station_variables` is non-empty and the file defers via the existing `_plan_config` machinery. Document in the manifest's `known_problems`/notes that PTT-only rigs have no Doppler CAT.
- [ ] **Step 5: Run → PASS.**
- [ ] **Step 6: Commit.** `feat(rig): write gpredict's radio file pointing at the shared rigctld (D-073 §7)`

---

## Task 14: `doctor` rig checks, read-only and never keying

**Files:**
- Modify: `src/hammunition/doctor.py` (add rig inputs to `run_checks` and a `rig_checks` section; never a keying command)
- Modify: `src/hammunition/cli/main.py` (`cmd_doctor`: gather the rig facts — station completeness, `systemctl --user is-enabled/is-active`, `/proc/<pid>/cmdline`, a loopback `\dump_state` probe, device presence, linger — and pass them in)
- Test: `tests/test_doctor.py` (extend), `tests/test_rig_dumpstate.py` (create — parses a real dummy rigctld's `\dump_state` on an ephemeral port)

**Interfaces:**
- Produces: `Check`s named `rig` covering §9: station complete; service enabled/active; arguments match the station; listening on loopback only; daemon answering `\dump_state`; (CAT only) radio answering `f` — never for PTT-only; device present; port not held elsewhere; groups on the user manager; hamlib knows the model; unattended/linger. All as pure inputs; the CLI gathers them.

- [ ] **Step 1: Write failing tests.** Feed `run_checks(... rig_station_complete=False, rig_missing=("rig_device",) ...)` → a `warn` check naming the missing flag. Feed a "service enabled+active, args match, loopback only, answering" set → `ok`. Feed "args differ (station 38400, running 4800)" → a `warn`/`fail` with the reinstall fix. A separate test (`test_rig_dumpstate.py`) starts a dummy `rigctld -m 1` on an ephemeral port, connects, sends `\dump_state`, and asserts the parser in `hammunition.rig` (`parse_dump_state_model(reply) -> int | None`) extracts the model line — the §9 "checked against a dummy rigctld in the test suite" requirement. Skip when no `rigctld`.
- [ ] **Step 2: Run → FAIL.**
- [ ] **Step 3: Implement.** Add the rig kwargs to `run_checks` (all defaulted so existing callers/tests are unaffected) and emit the checks. Add `parse_dump_state_model` to `hammunition/rig.py`. In `cmd_doctor`, gather the facts read-only: `systemctl --user is-enabled/is-active hammunition-rigctld`, read `/proc/net/tcp`+`tcp6` for 4532 loopback binding, connect to `127.0.0.1:4532` and send `\dump_state` (read-only; never `T`/`set_`), resolve the by-id path, read the user manager's groups, `loginctl show-user` + the linger record. Guard every probe so a machine with nothing set/offline yields `info`/`warn`, never a crash. **In tests, inject all of this; never let the test suite connect to 4532 or run systemctl.**
- [ ] **Step 4: Run → PASS.** `nice -n 19 .venv/bin/python -m pytest tests/test_doctor.py tests/test_json_doctor.py tests/test_rig_dumpstate.py -q`
- [ ] **Step 5: Commit.** `feat(rig): doctor checks the rig service read-only, never keying (D-073 §9)`

---

## Task 15: Documentation, decision record, changelog, generated references

**Files:**
- Rewrite: `docs/guides/rig-control.md` (around the service; §7 program table; PTT-only section; the flrig route; #174 note)
- Modify: `docs/reference/cli.md` (the new `station set` flags; `--unattended`; devctl `linger`)
- Modify: `docs/reference/json-interface.md` (regenerate: `nice -n 19 .venv/bin/python scripts/gen_json_reference.py` — never hand-edit)
- Modify: the station docs page under `docs/getting-started/` or `docs/profiles/station.md` if one exists (mention `station set --rig`)
- Modify: `docs/DECISIONS.md` (append **D-073**, status *proposed*, bench owed; summarise the nine rulings, the gate result, what the bench owes)
- Modify: `CLAUDE.md` (a D-073 row in the decisions table; update the counts: packages, classes, devices if the "Repo layout" counts are maintained — set them to the measured current values)
- Modify: `CHANGELOG.md` (under `## [Unreleased]`)
- Modify: `mkdocs.yml` (nav for any new page; rig-control already in nav — confirm)
- Test: `tests/test_docs_generated.py` (must stay green — `--check` no-op), `scripts/check_doc_links.py` (run it)

- [ ] **Step 1: Regenerate the JSON reference.** `nice -n 19 .venv/bin/python scripts/gen_json_reference.py` then confirm `--check` is a no-op.
- [ ] **Step 2: Rewrite `docs/guides/rig-control.md`** around the service: *Hamlib NET rigctl* at `127.0.0.1:4532` for WSJT-X, JTDX, JS8Call, fldigi, Pat, Direwolf, tlf, gpredict, FreeDATA, Mercury, with the flrig alternative; a PTT-only section (§3d); the #174-is-fixed note; placeholders only. Use the Write/Edit tools (never a heredoc).
- [ ] **Step 3: Update `cli.md`, the station docs, `CHANGELOG.md`, `mkdocs.yml`.**
- [ ] **Step 4: Append D-073 to `docs/DECISIONS.md`** following the house format (heading `## D-073 — ...`, the nine rulings folded in, the measured gate result, "status: proposed; bench owed", the §12 bench list).
- [ ] **Step 5: Add the CLAUDE.md decisions-table row** and correct the counts under "Repo layout" to the measured values.
- [ ] **Step 6: Run the doc checks.** `nice -n 19 .venv/bin/python scripts/check_doc_links.py` and `nice -n 19 .venv/bin/python -m pytest tests/test_docs_generated.py -q`.
- [ ] **Step 7: Commit.** `docs(rig): rig-control guide, cli, json-interface, D-073, changelog (D-073)`

---

## Task 16: Whole-branch green and final review

- [ ] **Step 1: `make check`.** `cd /home/chiefgyk3d/src/Hammunition-rig && nice -n 19 ionice -c 3 make check > /tmp/.../check.log 2>&1; echo "CHECK_EXIT=$?"` — require exit 0 (test `$?`, never `grep`).
- [ ] **Step 2: Full pytest under unshare.** `nice -n 19 unshare -r .venv/bin/python -m pytest tests -q -p no:cacheprovider` — require exit 0.
- [ ] **Step 3: Dispatch ONE whole-branch reviewer subagent on opus** (the only subagent permitted). Address its findings via `superpowers:receiving-code-review`. Re-run both green commands after any change.
