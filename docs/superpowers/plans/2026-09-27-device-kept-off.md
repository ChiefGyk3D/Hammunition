# Device kept off Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A parked device stays parked across reboots, suspend and a replug into the same port, until it is woken, and the tray says so once per login.

**Architecture:** Parking also writes one entry into `/etc/udev/rules.d/66-hammunition-kept.rules`, a file only the existing root helper (`hammunition-devctl`) writes, built from values read off the device and validated by pattern. Waking removes the entry. udev applies it as the device appears; nothing runs at boot. Live state is still read from sysfs; the file records intent only.

**Tech Stack:** Python 3.11+ (`mypy --strict`, pytest, ruff), udev, QML (Plasma 6) in the separate `hammunition-tray` repository.

**Spec:** `docs/superpowers/specs/2026-09-27-device-kept-off-design.md`

## Global Constraints

- Rules file path: `/etc/udev/rules.d/66-hammunition-kept.rules`, mode 0644, root-owned, rewritten whole and atomically.
- One entry per kept device, two lines: `# kept: <name>` then the rule. The rule, exactly:
  `ACTION=="add", SUBSYSTEM=="usb", ENV{DEVTYPE}=="usb_device", KERNEL=="<address>", ATTR{idVendor}=="<vendor>", ATTR{idProduct}=="<product>", ATTR{authorized}="0"`
- Validation: address `^\d+-\d+(\.\d+)*$`, vendor and product `^[0-9a-f]{4}$`, name `^[a-z0-9][a-z0-9-]*$`. Nothing else reaches the file.
- A line in the file the engine did not write is a refusal naming the line, never skipped and never overwritten.
- `park` keeps by default (the switch is the memory); `park --until-reboot` does not write the file.
- No new privileged path and no new polkit action: the existing helper writes the file.
- After a change: `udevadm control --reload`. No `trigger`.
- Every effect is verified by reading it back (D-031).
- No doc may claim the feature works across a reboot until Task 7 has recorded it on the bench page.
- Commits end with `Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>`; `scripts/check_commit_claims.py` runs on every commit.
- Run gates from the repo root with the checkout's venv: `.venv/bin/python -m pytest -q`, `.venv/bin/mypy --strict`, `.venv/bin/ruff check src tests`, `.venv/bin/ruff format --check src tests`, `.venv/bin/python scripts/check_doc_links.py`.

## Review Focus

1. **The kernel binds before udev's rule runs.** On `add` the device's interfaces are already probed, so `/dev/ttyACM0` may exist for a moment and gpsd may open it before `authorized=0` lands. Expected: the device ends parked and gpsd lets go, with no retry loop. Task 7 measures it; Task 6's docs say "as the device appears", never "before it binds", unless Task 7 shows otherwise.
2. **A kept device that is not plugged in.** `wake gps-receiver@3-5.1` must clear its entry even with nothing attached, and `state` must list it rather than hide it. Tests in Task 3.
3. **Two receivers of one model.** Keeping one must not keep the other: entries match port and IDs together. Test in Task 1 (distinct addresses give distinct entries) and Task 3 (waking one removes only its entry).
4. **A hand-edited or foreign rules file.** A line the engine did not write refuses the rewrite, names the line, and leaves the file untouched, while the sysfs park still happens and the message says it will not stay parked. Tests in Task 2.
5. **The last entry removed.** Waking the only kept device deletes the file rather than leaving a header-only file. Test in Task 2.

---

### Task 1: The kept-entry model, and the file format

**Files:**
- Modify: `src/hammunition/hardware/power.py`
- Test: `tests/test_power_control.py`

**Interfaces:**
- Consumes: `Parkable` (existing; `name`, `address`, `identifier` as `"vvvv:pppp"`), `PowerError`.
- Produces:
  - `KEPT_RULES: str = "/etc/udev/rules.d/66-hammunition-kept.rules"`
  - `@dataclass(frozen=True) class KeptEntry: name: str; address: str; vendor: str; product: str`, with `def rule(self) -> str` and `def same_device(self, other: KeptEntry) -> bool` (address, vendor and product equal; name ignored)
  - `def kept_entry(p: Parkable) -> KeptEntry` (raises `PowerError` on anything failing validation)
  - `def render_kept(entries: Iterable[KeptEntry]) -> str`
  - `def parse_kept(text: str) -> list[KeptEntry]` (raises `PowerError` naming a foreign line)
  - `guard(KEPT_RULES)` returns the path; `guard` of any other `/etc` path still raises.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_power_control.py` (add `import dataclasses` at the top, and `KEPT_RULES, KeptEntry, kept_entry, parse_kept, render_kept` to the existing `from hammunition.hardware.power import (...)`):

```python
def _gps(address: str = "3-5.1", identifier: str = "1546:01a9") -> Parkable:
    return Parkable(
        name="gps-receiver",
        summary="USB GNSS receivers",
        method="usb_deauthorize",
        quiet=(),
        sysfs_path=f"/sys/bus/usb/devices/{address}",
        identifier=identifier,
        parked=False,
    )


RULE = (
    'ACTION=="add", SUBSYSTEM=="usb", ENV{DEVTYPE}=="usb_device", KERNEL=="3-5.1", '
    'ATTR{idVendor}=="1546", ATTR{idProduct}=="01a9", ATTR{authorized}="0"'
)


def test_kept_entry_builds_the_exact_rule_line() -> None:
    assert kept_entry(_gps()).rule() == RULE


@pytest.mark.parametrize(
    "address",
    ["3-5.1\n", '3-5.1",RUN+="x', "3-5..1", "usb3", "3-", "3-5.1 "],
)
def test_kept_entry_refuses_an_address_that_is_not_a_usb_port(address: str) -> None:
    # No "/" in any of these: `Parkable.address` is the path's last component,
    # so a slash would test Path.name, not the validator.
    bad = dataclasses.replace(_gps(), sysfs_path=f"/sys/bus/usb/devices/{address}")
    assert bad.address == address
    with pytest.raises(PowerError):
        kept_entry(bad)


@pytest.mark.parametrize("identifier", ["1546:01A9x", "1546", "15a:01a9", '1546:01a9"'])
def test_kept_entry_refuses_an_identifier_that_is_not_two_hex_quads(identifier: str) -> None:
    with pytest.raises(PowerError):
        kept_entry(_gps(identifier=identifier))


def test_kept_entry_lowercases_the_identifier() -> None:
    assert kept_entry(_gps(identifier="1546:01A9")).product == "01a9"


def test_two_ports_are_two_entries() -> None:
    a, b = kept_entry(_gps("3-5.1")), kept_entry(_gps("3-6"))
    assert not a.same_device(b)
    assert parse_kept(render_kept([a, b])) == [a, b]


def test_render_then_parse_round_trips() -> None:
    entry = kept_entry(_gps())
    text = render_kept([entry])
    assert f"# kept: gps-receiver\n{RULE}\n" in text
    assert parse_kept(text) == [entry]


def test_parse_refuses_a_line_hammunition_did_not_write() -> None:
    text = render_kept([kept_entry(_gps())]) + 'ACTION=="add", RUN+="/bin/sh -c evil"\n'
    with pytest.raises(PowerError, match="line 5"):
        parse_kept(text)


def test_parse_refuses_a_rule_without_its_name_line() -> None:
    with pytest.raises(PowerError):
        parse_kept(RULE + "\n")


def test_parse_of_an_empty_file_is_no_entries() -> None:
    assert parse_kept("") == []


def test_guard_admits_the_kept_rules_file_and_nothing_beside_it() -> None:
    assert guard(KEPT_RULES) == KEPT_RULES
    for other in (
        "/etc/udev/rules.d/65-hammunition.rules",
        "/etc/udev/rules.d/66-hammunition-kept.rules.d/x",
        "/etc/udev/rules.d/../../shadow",
        "/etc/udev/rules.d/66-hammunition-kept.rules/../../../shadow",
    ):
        with pytest.raises(PowerError):
            guard(other)
```

`test_parse_refuses_a_line_hammunition_did_not_write` expects line 5: the header is two lines, then `# kept:` and the rule are lines 3 and 4.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest -q tests/test_power_control.py -k "kept or render or parse or two_ports or guard_admits"`
Expected: ImportError on `KEPT_RULES`.

- [ ] **Step 3: Implement**

In `src/hammunition/hardware/power.py`: add `import re` and `from collections.abc import Iterable` under the existing imports (the `Iterable` import goes outside the `TYPE_CHECKING` block only if used at runtime; it is only a hint here, so put it inside `if TYPE_CHECKING:` beside `Mapping`). Add to `__all__`: `"KEPT_RULES"`, `"KeptEntry"`, `"kept_entry"`, `"parse_kept"`, `"render_kept"`. Then, after `WRITABLE_LEAVES`:

```python
KEPT_RULES = "/etc/udev/rules.d/66-hammunition-kept.rules"
"""The one file outside sysfs this module writes: devices kept parked across
reboots. udev applies it as a device appears, so nothing runs at boot. Named
66 to run after Hammunition's own 65-hammunition.rules."""

KEPT_HEADER = (
    "# Written by hammunition-devctl (D-056): devices kept parked across reboots.\n"
    "# Change it with `hammunition hardware park` and `wake`, not by hand.\n"
)

_ADDRESS = re.compile(r"\d+-\d+(\.\d+)*")
_HEX4 = re.compile(r"[0-9a-f]{4}")
_NAME = re.compile(r"[a-z0-9][a-z0-9-]*")
_RULE = re.compile(
    r'ACTION=="add", SUBSYSTEM=="usb", ENV\{DEVTYPE\}=="usb_device", '
    r'KERNEL=="(?P<address>[^"]*)", ATTR\{idVendor\}=="(?P<vendor>[^"]*)", '
    r'ATTR\{idProduct\}=="(?P<product>[^"]*)", ATTR\{authorized\}="0"'
)
_NAME_LINE = "# kept: "


@dataclass(frozen=True)
class KeptEntry:
    """One device kept parked: the port it sits in and what it is."""

    name: str
    address: str
    vendor: str
    product: str

    def rule(self) -> str:
        return (
            f'ACTION=="add", SUBSYSTEM=="usb", ENV{{DEVTYPE}}=="usb_device", '
            f'KERNEL=="{self.address}", ATTR{{idVendor}}=="{self.vendor}", '
            f'ATTR{{idProduct}}=="{self.product}", ATTR{{authorized}}="0"'
        )

    def same_device(self, other: KeptEntry) -> bool:
        """Port and model together. The name is a label, not identity."""
        return (self.address, self.vendor, self.product) == (
            other.address,
            other.vendor,
            other.product,
        )


def _validated(entry: KeptEntry) -> KeptEntry:
    for field, value, pattern in (
        ("name", entry.name, _NAME),
        ("address", entry.address, _ADDRESS),
        ("vendor", entry.vendor, _HEX4),
        ("product", entry.product, _HEX4),
    ):
        if not pattern.fullmatch(value):
            raise PowerError(
                f"refusing to keep {entry.name!r} parked: its {field} {value!r} is not "
                f"the shape a USB {field} has, and nothing else may reach a udev rule "
                f"that root applies"
            )
    return entry


def kept_entry(p: Parkable) -> KeptEntry:
    """The entry that keeps ``p`` parked, from values read off the device."""
    vendor, _, product = p.identifier.lower().partition(":")
    return _validated(KeptEntry(p.name, p.address, vendor, product))


def render_kept(entries: Iterable[KeptEntry]) -> str:
    body = "".join(
        f"{_NAME_LINE}{e.name}\n{e.rule()}\n"
        for e in sorted(set(entries), key=lambda e: (e.address, e.vendor, e.product, e.name))
    )
    return KEPT_HEADER + body


def parse_kept(text: str) -> list[KeptEntry]:
    """Read the file back. A line this module did not write is a refusal, never
    skipped: rewriting a file that holds somebody else's rule would delete it."""
    header = set(KEPT_HEADER.splitlines())
    entries: list[KeptEntry] = []
    pending: str | None = None
    for number, line in enumerate(text.splitlines(), start=1):
        if not line.strip() or line in header:
            continue
        if line.startswith(_NAME_LINE) and pending is None:
            pending = line[len(_NAME_LINE) :]
            continue
        match = _RULE.fullmatch(line)
        if pending is None or match is None:
            raise PowerError(
                f"{KEPT_RULES} line {number} was not written by Hammunition: {line!r}. "
                f"Refusing to rewrite a file holding a rule it does not own; move that "
                f"line to a file of its own and try again."
            )
        entries.append(
            _validated(KeptEntry(pending, match["address"], match["vendor"], match["product"]))
        )
        pending = None
    if pending is not None:
        raise PowerError(f"{KEPT_RULES} ends with '# kept: {pending}' and no rule after it")
    return entries
```

In `guard()`, as the first statement after `normalised = os.path.normpath(path)`:

```python
    if normalised == KEPT_RULES and path == KEPT_RULES:
        return normalised
```

Requiring `path == KEPT_RULES` as given, not only after normalising, is what refuses `.../66-hammunition-kept.rules/../../../shadow`: that normalises to `/etc/shadow` anyway, and `…rules.d/x/../66-hammunition-kept.rules` is refused rather than admitted by a path that merely resolves to it.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest -q tests/test_power_control.py`
Expected: all pass, including every existing `guard` test.

- [ ] **Step 5: Falsify one**

Temporarily change `_ADDRESS` to `r".+"`; `test_kept_entry_refuses_an_address_that_is_not_a_usb_port` must fail. Restore it.

- [ ] **Step 6: Commit**

```bash
git add src/hammunition/hardware/power.py tests/test_power_control.py
git commit -m "Kept off: the entry model and the rules file format (D-056 amendment)

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: Plans carry the kept change, and execute applies it

**Files:**
- Modify: `src/hammunition/hardware/power.py`
- Test: `tests/test_power_control.py`

**Interfaces:**
- Consumes: Task 1's `KeptEntry`, `kept_entry`, `render_kept`, `parse_kept`, `KEPT_RULES`.
- Produces:
  - `PowerPlan` gains `keep: KeptEntry | None = None` and `forget: KeptEntry | None = None`.
  - `plan_park(p: Parkable, *, keep: bool = True) -> PowerPlan`
  - `plan_wake(p: Parkable) -> PowerPlan` (sets `forget=kept_entry(p)`)
  - `plan_forget(entry: KeptEntry) -> PowerPlan` (no sysfs writes; `forget=entry`)
  - `read_kept() -> list[KeptEntry]` (empty when the file is absent)
  - `execute(plan: PowerPlan) -> list[str]` unchanged in signature; now also applies `keep`/`forget` after the sysfs writes succeed, then calls `_reload_udev()`.
  - `_reload_udev() -> str | None` (None on success, else the reason).

- [ ] **Step 1: Update the fixture so park plans in existing tests do not touch `/etc`**

In `tests/test_power_control.py`, replace the `sysfs_root` fixture body with:

```python
    from hammunition.hardware import power

    monkeypatch.setattr(power, "ALLOWED_ROOTS", (*power.ALLOWED_ROOTS, str(tmp_path)))
    monkeypatch.setattr(power, "KEPT_RULES", str(tmp_path / "66-hammunition-kept.rules"))
    monkeypatch.setattr(power, "_reload_udev", lambda: None)
    return tmp_path
```

`guard()` reads the module global `KEPT_RULES` at call time, so the patched path is admitted and nothing else is.

- [ ] **Step 2: Write the failing tests**

Append (add `plan_forget, read_kept` to the import):

```python
def _node(root: Path, address: str = "3-5.1") -> Parkable:
    node = root / address
    (node / "power").mkdir(parents=True)
    (node / "authorized").write_text("1\n")
    (node / "power" / "control").write_text("on\n")
    return Parkable(
        name="gps-receiver",
        summary="USB GNSS receivers",
        method="usb_deauthorize",
        quiet=(),
        sysfs_path=str(node),
        identifier="1546:01a9",
        parked=False,
    )


def _kept_path() -> Path:
    from hammunition.hardware import power

    return Path(power.KEPT_RULES)


def test_park_keeps_by_default_and_writes_the_rule(sysfs_root: Path) -> None:
    p = _node(sysfs_root)
    assert execute(plan_park(p)) == []
    assert (Path(p.sysfs_path) / "authorized").read_text().strip() == "0"
    assert read_kept() == [kept_entry(p)]
    assert oct(_kept_path().stat().st_mode & 0o777) == "0o644"


def test_park_until_reboot_writes_no_rule(sysfs_root: Path) -> None:
    p = _node(sysfs_root)
    assert plan_park(p, keep=False).keep is None
    assert execute(plan_park(p, keep=False)) == []
    assert not _kept_path().exists()


def test_wake_removes_only_that_devices_entry(sysfs_root: Path) -> None:
    a, b = _node(sysfs_root, "3-5.1"), _node(sysfs_root, "3-6")
    assert execute(plan_park(a)) == [] and execute(plan_park(b)) == []
    assert execute(plan_wake(a)) == []
    assert read_kept() == [kept_entry(b)]


def test_waking_the_last_kept_device_deletes_the_file(sysfs_root: Path) -> None:
    p = _node(sysfs_root)
    execute(plan_park(p))
    assert execute(plan_wake(p)) == []
    assert not _kept_path().exists()


def test_parking_twice_keeps_one_entry(sysfs_root: Path) -> None:
    p = _node(sysfs_root)
    execute(plan_park(p))
    (Path(p.sysfs_path) / "authorized").write_text("1\n")
    execute(plan_park(p))
    assert read_kept() == [kept_entry(p)]


def test_forget_clears_an_absent_device_without_touching_sysfs(sysfs_root: Path) -> None:
    p = _node(sysfs_root)
    execute(plan_park(p))
    plan = plan_forget(kept_entry(p))
    assert plan.writes == ()
    assert execute(plan) == []
    assert read_kept() == []


def test_a_foreign_line_leaves_the_file_alone_and_says_the_park_will_not_stay(
    sysfs_root: Path,
) -> None:
    p = _node(sysfs_root)
    foreign = 'ACTION=="add", RUN+="/usr/bin/true"\n'
    _kept_path().write_text(foreign)
    problems = execute(plan_park(p))
    assert (Path(p.sysfs_path) / "authorized").read_text().strip() == "0"
    assert _kept_path().read_text() == foreign
    assert len(problems) == 1
    assert "parked now but will not stay parked" in problems[0]
    assert "line 1" in problems[0]


def test_a_failed_reload_is_reported_and_the_rule_is_still_written(
    sysfs_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from hammunition.hardware import power

    monkeypatch.setattr(power, "_reload_udev", lambda: "udevadm: not found")
    p = _node(sysfs_root)
    problems = execute(plan_park(p))
    assert read_kept() == [kept_entry(p)]
    assert problems == [
        "udev did not reload its rules (udevadm: not found); the entry applies from the next boot"
    ]


def test_no_kept_change_when_the_sysfs_write_failed(sysfs_root: Path) -> None:
    p = _node(sysfs_root)
    (Path(p.sysfs_path) / "authorized").unlink()
    (Path(p.sysfs_path) / "authorized").mkdir()  # write_text now raises
    assert execute(plan_park(p)) != []
    assert not _kept_path().exists()
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest -q tests/test_power_control.py`
Expected: new tests fail (`plan_forget`/`read_kept` missing, `plan_park` has no `keep`).

- [ ] **Step 4: Implement**

In `power.py`: add `import subprocess` and `import shutil`. Add `"plan_forget"`, `"read_kept"` to `__all__`. Extend `PowerPlan`:

```python
    keep: KeptEntry | None = None
    """On a park: the entry to add so the device stays parked. None with --until-reboot."""
    forget: KeptEntry | None = None
    """On a wake or a forget: the entry to remove, if it is there."""
```

Move `KeptEntry` (and its helpers from Task 1) above `PowerPlan` so the annotation resolves. Replace `_plan`'s last line and the two public planners:

```python
    return PowerPlan(writes=_usb_writes(p, park=park), quiet=p.quiet, restore=not park)


def plan_park(p: Parkable, *, keep: bool = True) -> PowerPlan:
    """The writes that detach ``p`` and let its port suspend, and, unless
    ``keep`` is false, the entry that keeps it parked across reboots."""
    base = _plan(p, park=True)
    return PowerPlan(base.writes, base.quiet, base.restore, keep=kept_entry(p) if keep else None)


def plan_wake(p: Parkable) -> PowerPlan:
    """The writes that bring ``p`` back, and removal of its kept entry."""
    base = _plan(p, park=False)
    return PowerPlan(base.writes, base.quiet, base.restore, forget=kept_entry(p))


def plan_forget(entry: KeptEntry) -> PowerPlan:
    """Remove a kept entry for a device that is not attached. No sysfs writes:
    there is no node to write to, and the entry is all that is left of it."""
    return PowerPlan(writes=(), quiet=(), restore=True, forget=entry)


def read_kept() -> list[KeptEntry]:
    path = Path(KEPT_RULES)
    if not path.exists():
        return []
    return parse_kept(path.read_text())


def _reload_udev() -> str | None:
    if shutil.which("udevadm") is None:
        return "udevadm is not on PATH"
    result = subprocess.run(
        ["udevadm", "control", "--reload"], capture_output=True, text=True, check=False
    )
    return None if result.returncode == 0 else (result.stderr.strip() or f"exit {result.returncode}")


def _write_kept(entries: list[KeptEntry]) -> None:
    path = Path(guard(KEPT_RULES))
    if not entries:
        path.unlink(missing_ok=True)
        return
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(render_kept(entries))
        fh.flush()
        os.fsync(fh.fileno())
    os.chmod(tmp, 0o644)
    os.replace(tmp, path)


def _apply_kept(plan: PowerPlan) -> list[str]:
    who = (plan.keep or plan.forget)
    assert who is not None
    try:
        current = read_kept()
        wanted = [e for e in current if not (plan.forget and e.same_device(plan.forget))]
        if plan.keep and not any(e.same_device(plan.keep) for e in wanted):
            wanted.append(plan.keep)
        if wanted == current:
            return []
        _write_kept(wanted)
        after = read_kept()
    except (OSError, PowerError) as exc:
        if plan.keep:
            return [f"{who.name} is parked now but will not stay parked: {exc}"]
        return [f"{who.name}'s kept entry could not be removed: {exc}"]
    if plan.keep and not any(e.same_device(plan.keep) for e in after):
        return [f"{who.name} is parked now but will not stay parked: the entry did not read back"]
    if plan.forget and any(e.same_device(plan.forget) for e in after):
        return [f"{who.name}'s kept entry is still in {KEPT_RULES} after removing it"]
    reason = _reload_udev()
    if reason is not None:
        return [f"udev did not reload its rules ({reason}); the entry applies from the next boot"]
    return []
```

At the end of `execute`, replace `return problems` with:

```python
    if problems or (plan.keep is None and plan.forget is None):
        return problems
    return _apply_kept(plan)
```

Update the module docstring's "**Nothing here is persisted.**" paragraph to: "**What persists is intent, not state.** A parked device stays parked through one udev rule per device in `KEPT_RULES`, applied by udev as the device appears. Whether a device *is* parked is still read from sysfs by :func:`parkable`; the file only says what the operator asked for, and `state` reports both."

- [ ] **Step 5: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest -q tests/test_power_control.py`, then `.venv/bin/mypy --strict`
Expected: pass; mypy clean.

- [ ] **Step 6: Falsify one**

Delete the `if plan.forget and any(...)` read-back check and change `_write_kept` to write `current` instead of `wanted`; `test_wake_removes_only_that_devices_entry` must fail. Restore both.

- [ ] **Step 7: Commit**

```bash
git add src/hammunition/hardware/power.py tests/test_power_control.py
git commit -m "Kept off: park writes the entry, wake removes it, both read back

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: The helper: `--until-reboot`, forgetting an absent device, and `state`

**Files:**
- Modify: `src/hammunition/cli/devctl.py`
- Test: `tests/test_devctl.py`

**Interfaces:**
- Consumes: `plan_park(p, keep=...)`, `plan_wake`, `plan_forget`, `read_kept`, `kept_entry`, `KeptEntry`, `PowerError`.
- Produces:
  - `hammunition-devctl park [--until-reboot] NAME`
  - `wake NAME@ADDRESS` succeeds for a kept device that is not attached.
  - `resolve_kept(name: str, kept: list[KeptEntry]) -> KeptEntry` (public; the CLI uses it too)
  - `state` JSON: every attached parkable gets `"kept": bool, "attached": true`; each kept entry with no attached device appears as `{"name", "summary": "", "address", "identifier": "vvvv:pppp", "method": "usb_deauthorize", "parked": null, "kept": true, "attached": false}`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_devctl.py` (import `Callable` from `collections.abc`, `KeptEntry` from `hammunition.hardware.power` and `resolve_kept` from `hammunition.cli.devctl`):

```python
GPS_KEPT = KeptEntry("gps-receiver", "3-5.1", "1546", "01a7")


def _recording(seen: list[object]) -> Callable[[object], list[str]]:
    def fake(plan: object) -> list[str]:
        seen.append(plan)
        return []

    return fake


def test_state_marks_an_attached_kept_device(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "hammunition.cli.devctl._survey",
        lambda: ([_parkable("gps-receiver", "3-5.1", parked=True)], []),
    )
    monkeypatch.setattr("hammunition.cli.devctl.read_kept", lambda: [GPS_KEPT])
    assert main(["state"]) == 0
    [row] = json.loads(capsys.readouterr().out)
    assert row["kept"] is True and row["attached"] is True and row["parked"] is True


def test_state_lists_a_kept_device_that_is_not_attached(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("hammunition.cli.devctl._survey", lambda: ([], []))
    monkeypatch.setattr("hammunition.cli.devctl.read_kept", lambda: [GPS_KEPT])
    assert main(["state"]) == 0
    assert json.loads(capsys.readouterr().out) == [
        {
            "name": "gps-receiver",
            "summary": "",
            "address": "3-5.1",
            "identifier": "1546:01a7",
            "method": "usb_deauthorize",
            "parked": None,
            "kept": True,
            "attached": False,
        }
    ]


def test_state_still_prints_json_when_the_kept_file_is_foreign(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken() -> list[KeptEntry]:
        raise PowerError("line 1 was not written by Hammunition")

    monkeypatch.setattr("hammunition.cli.devctl._survey", lambda: ([], []))
    monkeypatch.setattr("hammunition.cli.devctl.read_kept", broken)
    assert main(["state"]) == 0
    out, err = capsys.readouterr()
    assert json.loads(out) == []
    assert "line 1" in err


def test_park_until_reboot_plans_no_kept_entry(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[object] = []
    monkeypatch.setattr(
        "hammunition.cli.devctl._survey", lambda: ([_parkable("gps-receiver", "3-5.1")], [])
    )
    monkeypatch.setattr("hammunition.cli.devctl.execute", _recording(seen))
    assert main(["park", "--until-reboot", "gps-receiver"]) == 0
    assert seen[0].keep is None  # type: ignore[attr-defined]
    assert main(["park", "gps-receiver"]) == 0
    assert seen[1].keep is not None  # type: ignore[attr-defined]


def test_wake_forgets_a_kept_device_that_is_not_attached(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[object] = []
    monkeypatch.setattr("hammunition.cli.devctl._survey", lambda: ([], []))
    monkeypatch.setattr("hammunition.cli.devctl.read_kept", lambda: [GPS_KEPT])
    monkeypatch.setattr("hammunition.cli.devctl.execute", _recording(seen))
    assert main(["wake", "gps-receiver@3-5.1"]) == 0
    assert seen[0].writes == () and seen[0].forget == GPS_KEPT  # type: ignore[attr-defined]


def test_park_of_an_absent_device_is_still_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("hammunition.cli.devctl._survey", lambda: ([], []))
    monkeypatch.setattr("hammunition.cli.devctl.read_kept", lambda: [GPS_KEPT])
    assert main(["park", "gps-receiver@3-5.1"]) == 2


def test_resolve_kept_refuses_a_bare_name_matching_two_ports() -> None:
    other = KeptEntry("gps-receiver", "3-6", "1546", "01a7")
    with pytest.raises(PowerError, match="3-5.1"):
        resolve_kept("gps-receiver", [GPS_KEPT, other])
    assert resolve_kept("gps-receiver@3-6", [GPS_KEPT, other]) == other
```

Update the existing `test_state_prints_json_a_tray_can_read` expected dict to add `"kept": False, "attached": True`, and in that test also `monkeypatch.setattr("hammunition.cli.devctl.read_kept", lambda: [])`. Add the same `read_kept` stub to every other existing test that calls `main(["state"])`.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest -q tests/test_devctl.py`
Expected: failures on the new tests (`--until-reboot` unknown, no `kept` key, no `resolve_kept`).

- [ ] **Step 3: Implement**

In `devctl.py`, extend the power import with `KeptEntry, kept_entry, plan_forget, read_kept`; add `"resolve_kept"` to `__all__`. Add:

```python
def resolve_kept(name: str, kept: list[KeptEntry]) -> KeptEntry:
    """A kept entry named ``NAME`` or ``NAME@ADDRESS``, for a device not attached."""
    wanted, _, address = name.partition("@")
    candidates = [e for e in kept if e.name == wanted and (not address or e.address == address)]
    if not candidates:
        raise PowerError(f"{name!r} is neither attached nor kept parked")
    if len(candidates) > 1:
        ports = ", ".join(f"{e.name}@{e.address}" for e in candidates)
        raise PowerError(f"{wanted!r} is kept at {len(candidates)} ports: {ports}. Name one.")
    return candidates[0]
```

Replace `_do` with:

```python
def _do(verb: str, name: str, *, keep: bool = True) -> int:
    found, skipped = _survey()
    for unit, why in skipped:
        print(f"note: {unit} is not parkable right now: {why}", file=sys.stderr)
    try:
        try:
            target = resolve(name, found)
        except PowerError:
            if verb != "wake":
                raise
            plan = plan_forget(resolve_kept(name, read_kept()))
        else:
            plan = plan_park(target, keep=keep) if verb == "park" else plan_wake(target)
    except PowerError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_UNPLANNABLE
    problems = execute(plan)
    for problem in problems:
        print(f"unverified: {problem}", file=sys.stderr)
    return EXIT_FAILED if problems else EXIT_OK
```

`resolve`'s own error is replaced by `resolve_kept`'s only on `wake`; a `park` of an absent device keeps `resolve`'s message.

Replace the body of `_state` after the skipped loop with:

```python
    try:
        kept = read_kept()
    except (OSError, PowerError) as exc:
        print(f"note: kept-off entries unreadable: {exc}", file=sys.stderr)
        kept = []

    def is_kept(p: Parkable) -> bool:
        try:
            mine = kept_entry(p)
        except PowerError:
            return False
        return any(e.same_device(mine) for e in kept)

    rows: list[dict[str, object]] = [
        {
            "name": p.name,
            "summary": p.summary,
            "address": p.address,
            "identifier": p.identifier,
            "method": p.method,
            "parked": p.parked,
            "kept": is_kept(p),
            "attached": True,
        }
        for p in sorted(found, key=lambda p: (p.name, p.address))
    ]
    attached = {(p.address, p.identifier.lower()) for p in found}
    for e in sorted(kept, key=lambda e: (e.name, e.address)):
        if (e.address, f"{e.vendor}:{e.product}") in attached:
            continue
        rows.append(
            {
                "name": e.name,
                "summary": "",
                "address": e.address,
                "identifier": f"{e.vendor}:{e.product}",
                "method": "usb_deauthorize",
                "parked": None,
                "kept": True,
                "attached": False,
            }
        )
    # Always a JSON array, including when it is empty: the applet parses this
    # every five seconds and a human sentence here is a parse error every five
    # seconds.
    print(json.dumps(rows))
    return EXIT_OK
```

In `main()`: add to the `park` subparser only:

```python
        if verb_name == "park":
            p.add_argument(
                "--until-reboot",
                action="store_true",
                help="park now without keeping it parked across reboots",
            )
```

and dispatch with `return _do(verb, args.name, keep=not getattr(args, "until_reboot", False))`. Update the `state` help to "JSON: every parkable device, attached or kept, and whether it is parked". Update the module docstring's first paragraph to say `park` also keeps the device parked across reboots unless `--until-reboot`.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest -q tests/test_devctl.py tests/test_power_control.py && .venv/bin/mypy --strict`
Expected: pass.

- [ ] **Step 5: Commit**

```bash
git add src/hammunition/cli/devctl.py tests/test_devctl.py
git commit -m "Kept off: the helper keeps by default, forgets absent devices, reports both

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: The CLI: `park --until-reboot`, the disclosure, `state`, and `unapply`

**Files:**
- Modify: `src/hammunition/cli/main.py` (`cmd_hardware_state`, `_power_verb`, `cmd_hardware_park`, `cmd_hardware_unapply`, the `hardware` subparsers around line 2550)
- Test: `tests/test_cli.py`

**Interfaces:**
- Consumes: `plan_park(p, keep=...)`, `plan_wake`, `plan_forget`, `read_kept`, `kept_entry`, `KEPT_RULES` from `hammunition.hardware.power`; `resolve`, `resolve_kept` from `hammunition.cli.devctl`.
- Produces: `hammunition hardware park [--until-reboot] [--dry-run] NAME`; `state` output with a `kept` column and a section for kept devices not attached; `unapply` removing `KEPT_RULES`.

- [ ] **Step 1: Write the failing tests**

Find the existing `hardware park`/`state`/`unapply` tests in `tests/test_cli.py` (search `cmd_hardware_state`, `"park"`, `hardware_unapply`) and add beside them, reusing their helpers for stubbing the survey and the helper path:

```python
def test_hardware_park_dry_run_discloses_the_kept_entry(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import importlib

    cli = importlib.import_module("hammunition.cli.main")
    _stub_power_verb(monkeypatch, cli, tmp_path, [_gps_parkable()])
    assert cli.main(["hardware", "park", "--dry-run", "gps-receiver"]) == 0
    out = capsys.readouterr().out
    assert "66-hammunition-kept.rules" in out
    assert 'KERNEL=="3-5.1"' in out
    assert "stays parked across reboots" in out


def test_hardware_park_until_reboot_passes_the_flag_and_writes_no_entry(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import importlib

    cli = importlib.import_module("hammunition.cli.main")
    _stub_power_verb(monkeypatch, cli, tmp_path, [_gps_parkable()])
    assert cli.main(["hardware", "park", "--until-reboot", "--dry-run", "gps-receiver"]) == 0
    out = capsys.readouterr().out
    assert "66-hammunition-kept.rules" not in out
    assert "park --until-reboot gps-receiver@3-5.1" in out


def test_hardware_wake_of_an_absent_kept_device_discloses_the_removal(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import importlib

    from hammunition.hardware.power import KeptEntry

    cli = importlib.import_module("hammunition.cli.main")
    _stub_power_verb(monkeypatch, cli, tmp_path, [])
    monkeypatch.setattr(
        "hammunition.hardware.power.read_kept",
        lambda: [KeptEntry("gps-receiver", "3-5.1", "1546", "01a9")],
    )
    assert cli.main(["hardware", "wake", "--dry-run", "gps-receiver@3-5.1"]) == 0
    out = capsys.readouterr().out
    assert "not attached" in out
    assert "remove its kept entry" in out


def test_hardware_state_shows_kept_and_absent(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    import importlib

    from hammunition.hardware.power import KeptEntry

    cli = importlib.import_module("hammunition.cli.main")
    monkeypatch.setattr(cli, "_survey_parkables", lambda args: ([_gps_parkable(parked=True)], []))
    monkeypatch.setattr(
        "hammunition.hardware.power.read_kept",
        lambda: [
            KeptEntry("gps-receiver", "3-5.1", "1546", "01a9"),
            KeptEntry("gps-receiver", "3-6", "1546", "01a9"),
        ],
    )
    assert cli.main(["hardware", "state"]) == 0
    out = capsys.readouterr().out
    assert "kept" in out.splitlines()[0]
    assert "Kept parked, not attached" in out
    assert "gps-receiver@3-6" in out
    assert "A reboot wakes everything" not in out


def test_hardware_unapply_removes_the_kept_rules_file(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import importlib

    cli = importlib.import_module("hammunition.cli.main")
    kept = tmp_path / "66-hammunition-kept.rules"
    kept.write_text("# kept: gps-receiver\n")
    monkeypatch.setattr("hammunition.hardware.power.KEPT_RULES", str(kept))
    _stub_unapply_with_nothing_logged(monkeypatch, cli)
    assert cli.main(["hardware", "unapply", "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert f"rm -f {kept}" in out
    assert "udevadm control --reload" in out
```

Write `_gps_parkable(parked: bool = False) -> Parkable` (address `3-5.1`, identifier `1546:01a9`, `sysfs_path="/sys/bus/usb/devices/3-5.1"`), `_stub_power_verb(monkeypatch, cli, tmp_path, found)` (creates a file at `tmp_path/"helper"`, sets `cli.HELPER_PATH` to it, stubs `shutil.which` to return `/usr/bin/pkexec`, stubs `cli._survey_parkables` to `lambda args: (found, [])`, and stubs `hammunition.hardware.power.read_kept` to `lambda: []`), and `_stub_unapply_with_nothing_logged(monkeypatch, cli)` (stubs `cli.operator` to return `"op"` and `cli.TransactionLog` to a class whose `read()` returns `[]`) at the top of this group, modelled on the existing unapply tests' stubs.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest -q tests/test_cli.py -k "kept or until_reboot or unapply_removes_the_kept"`
Expected: fail.

- [ ] **Step 3: Implement**

Parser: in the loop that builds the `park`/`wake` subparsers, add to `park` only:

```python
        if verb == "park":
            p_verb.add_argument(
                "--until-reboot",
                action="store_true",
                help="park now, but let a reboot wake it (no kept entry)",
            )
```

`_power_verb`: import `KEPT_RULES, plan_forget, read_kept` alongside the existing imports. Replace the `try: target = ... plan = ...` block with:

```python
    from hammunition.cli.devctl import resolve_kept

    keep = not getattr(args, "until_reboot", False)
    absent = False
    try:
        try:
            target = resolve_parkable(args.name, found)
        except PowerError:
            if verb != "wake":
                raise
            entry = resolve_kept(args.name, read_kept())
            plan = plan_forget(entry)
            absent = True
            label, address, summary = entry.name, entry.address, "not attached"
        else:
            plan = plan_park(target, keep=keep) if verb == "park" else plan_wake(target)
            label, address, summary = target.name, target.address, target.summary
    except PowerError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_UNPLANNABLE

    argv = ["pkexec", HELPER_PATH, verb]
    if verb == "park" and not keep:
        argv.append("--until-reboot")
    argv.append(f"{label}@{address}")
    command = Command(argv=tuple(argv), description=f"{verb.capitalize()} {label} at {address}")
    print(f"{verb.capitalize()}ing {label} ({summary}) at {address}\n")
    if plan.writes:
        print("Writes this will cause:")
        for write in plan.writes:
            print(f"  {write.path} <- {write.value}")
    if plan.keep is not None:
        print(f"\nIt stays parked across reboots. Added to {KEPT_RULES}:")
        print(f"  {plan.keep.rule()}")
    elif verb == "park":
        print("\nA reboot wakes it (--until-reboot): no kept entry is written.")
    if plan.forget is not None:
        note = "It is not attached, so this will only" if absent else "This will also"
        print(f"\n{note} remove its kept entry from {KEPT_RULES}, if present.")
    print(f"\n  # {command.description}\n  $ {command.display()}")
```

and change the later references from `target.name` to `label` in the final "Done" message.

`cmd_hardware_state`: after printing the table, read kept entries and print:

```python
    from hammunition.hardware.power import PowerError, kept_entry, read_kept

    try:
        kept = read_kept()
    except (OSError, PowerError) as exc:
        print(f"\nKept-off entries could not be read: {exc}")
        kept = []
```

Move this read above the table and print the header as `f"{'device':24} {'address':10} {'state':8} {'kept':5} summary"`, each row with `'yes' if any(e.same_device(kept_entry(p)) for e in kept) else 'no'` in the kept column. Then, for kept entries not matching any attached device:

```python
    absent = [e for e in kept if not any(e.same_device(kept_entry(p)) for p in found)]
    if absent:
        print("\nKept parked, not attached (cleared with `hammunition hardware wake NAME@ADDRESS`):")
        for e in absent:
            print(f"  {e.name}@{e.address}  {e.vendor}:{e.product}")
    print(
        "\n`hammunition hardware park NAME` keeps it parked across reboots; "
        "`park --until-reboot NAME` lets a reboot wake it; `wake NAME` brings it back."
    )
```

The early return for "No parkable device is attached" must move below the absent section, so a machine with only absent kept entries still lists them.

`cmd_hardware_unapply`: before `if not recorded and not skipped:`, compute

```python
    from hammunition.hardware.power import KEPT_RULES

    kept_present = Path(KEPT_RULES).exists()
```

change both early "Nothing to …" returns to also require `not kept_present`, and after `commands = [...]` append:

```python
    if kept_present:
        commands.append(
            Command(
                argv=("rm", "-f", KEPT_RULES),
                description="Remove the kept-off entries, so every device wakes from the next boot",
                requires_root=True,
            )
        )
        commands.append(
            Command(
                argv=("udevadm", "control", "--reload"),
                description="Reload udev's rules",
                requires_root=True,
            )
        )
        present.append(KEPT_RULES)
```

Update `cmd_hardware_park`'s docstring to "Detach a device and keep it parked across reboots, unless --until-reboot." and `cmd_hardware_unapply`'s docstring's list of what it removes.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest -q && .venv/bin/mypy --strict && .venv/bin/ruff check src tests && .venv/bin/ruff format --check src tests`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add src/hammunition/cli/main.py tests/test_cli.py
git commit -m "Kept off: the CLI discloses the entry, lists kept devices, unapply removes it

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 5: `doctor` reports kept devices

**Files:**
- Modify: `src/hammunition/doctor.py` (`run_checks`), `src/hammunition/cli/main.py` (`cmd_doctor`)
- Test: `tests/test_doctor.py` (or wherever `run_checks` is tested; `grep -rn run_checks tests`)

**Interfaces:**
- Consumes: `read_kept`, `kept_entry`, `parkable` survey from Task 4's `_survey_parkables`.
- Produces: `run_checks(..., kept_attached: list[str] = [], kept_absent: list[str] = [])` (keyword-only, defaulted as `tuple()` to avoid a mutable default: `kept_attached: tuple[str, ...] = ()`, `kept_absent: tuple[str, ...] = ()`).

- [ ] **Step 1: Write the failing tests**

```python
def test_doctor_reports_kept_devices_as_info() -> None:
    checks = run_checks(**_BASE, kept_attached=("gps-receiver@3-5.1",))
    kept = [c for c in checks if c.name == "kept off"]
    assert kept and kept[0].status == "info"
    assert "gps-receiver@3-5.1" in kept[0].detail


def test_doctor_warns_about_a_kept_entry_with_nothing_attached() -> None:
    checks = run_checks(**_BASE, kept_absent=("gps-receiver@3-6",))
    kept = [c for c in checks if c.name == "kept off"]
    assert kept and kept[0].status == "warn"
    assert "hammunition hardware wake gps-receiver@3-6" in (kept[0].fix or "")


def test_doctor_says_nothing_about_kept_when_none_is_kept() -> None:
    assert not [c for c in run_checks(**_BASE) if c.name == "kept off"]
```

`_BASE` is the keyword dict the existing doctor tests already pass to `run_checks`; reuse it (define it from an existing test's arguments if it is not already a module constant).

- [ ] **Step 2: Run to verify they fail**

Run: `.venv/bin/python -m pytest -q tests/test_doctor.py -k kept`
Expected: TypeError on the unknown keyword.

- [ ] **Step 3: Implement**

Add the two keyword parameters to `run_checks` and, after the udev-rules check:

```python
    if kept_absent:
        names = ", ".join(kept_absent)
        checks.append(
            Check(
                "kept off",
                "warn",
                f"kept parked but not attached: {names}",
                fix="; ".join(f"`hammunition hardware wake {n}` clears it" for n in kept_absent),
            )
        )
    elif kept_attached:
        checks.append(
            Check("kept off", "info", f"parked across reboots: {', '.join(kept_attached)}")
        )
```

(Match `Check`'s actual constructor; if `fix` is positional, pass it positionally.) In `cmd_doctor`, compute both tuples with `read_kept()` and the survey, inside `try/except (OSError, PowerError, CatalogError, SystemExit)` falling back to empty tuples, and pass them.

- [ ] **Step 4: Run and commit**

Run: `.venv/bin/python -m pytest -q && .venv/bin/mypy --strict`

```bash
git add src/hammunition/doctor.py src/hammunition/cli/main.py tests/test_doctor.py
git commit -m "Kept off: doctor names kept devices and flags an entry with nothing attached

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 6: Documentation

**Files:**
- Modify: `docs/DECISIONS.md` (D-056), `docs/hardware/power-control.md`, `docs/reference/cli.md`, `catalog/hardware/classes/gps-receiver.yaml` (the comment "Nothing is persisted: a reboot wakes it again."), `docs/superpowers/specs/2026-09-27-device-kept-off-design.md` (§3's "before its interfaces bind"), `README.md` (the power-control status row), `CLAUDE.md` (the D-056 row)
- Regenerate: `.venv/bin/python scripts/gen_hardware_reference.py`

- [ ] **Step 1: D-056 amendment**

Under `### Why parked state is not persisted`, add a section `### Amendment (<date>): parked is kept, as intent, in one udev rule per device` saying: the maintainer asked for the switch to stay where it is set; the file records intent, sysfs remains the state and `state` reports both, so the disagreement D-056 worried about is shown rather than reconciled; the mechanism (port and IDs, validated, written only by the helper, `66-`, reload not trigger); `--until-reboot` keeps the old behaviour; what Task 7 measured about the kernel binding before the rule runs, stated as measured.

- [ ] **Step 2: The operator pages**

`power-control.md`: a "Kept off across reboots" section with: what `park` now does, `--until-reboot`, how to inspect (`cat /etc/udev/rules.d/66-hammunition-kept.rules`, `hammunition hardware state`), how to remove one (`wake NAME@ADDRESS`, works unplugged) or all (`hammunition hardware unapply`), that moving a device to another port brings it back, and that a hand-added line makes the engine refuse to rewrite the file. Replace every "a reboot wakes everything" with the new behaviour. `cli.md`: the flag, the `state` columns, the JSON fields `kept` and `attached` with `parked: null` for absent devices, `unapply` removing the file.

- [ ] **Step 3: The claims**

`gps-receiver.yaml`'s comment and the spec's §3 wording: "applied by udev as the device appears" and whatever Task 7 measured about the moment before it. README status row and CLAUDE.md row: "kept across reboots" only once Task 7 has passed; until then leave "designed, not built" replaced by "built; reboot not yet measured".

- [ ] **Step 4: Regenerate and check**

Run: `.venv/bin/python scripts/gen_hardware_reference.py && .venv/bin/python scripts/check_doc_links.py && .venv/bin/python -m pytest -q tests/test_docs_generated.py`
Expected: pass.

- [ ] **Step 5: Commit**

```bash
git add docs catalog README.md CLAUDE.md
git commit -m "Docs: kept off across reboots, D-056 amended

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 7: Bench proof on the field laptop (maintainer at the keyboard)

**Files:**
- Modify: `docs/reference/bench-verification-5430.md` (a new session section; no hostname, no position, no callsign)

- [ ] **Step 1: Re-apply the helper from this branch**

`.venv/bin/hammunition hardware apply` from the branch checkout; answer `yes`.

- [ ] **Step 2: Keep the GPS off and record the port**

`hammunition hardware park gps-receiver`; then `cat /etc/udev/rules.d/66-hammunition-kept.rules` and `hammunition hardware state`. Record the port.

- [ ] **Step 3: Reboot and measure**

After login: `cat /sys/bus/usb/devices/<port>/authorized` (expect `0`), `ls /dev/ttyACM*` (expect none), `journalctl -b --no-pager | grep -E 'gpsdctl|ttyACM|<port>'` to see whether ttyACM0 appeared before the rule landed and for how long, whether gpsd retried, and whether the tray's notice appeared. Confirm the port name did not change.

- [ ] **Step 4: Wake, reboot, measure again**

`hammunition hardware wake gps-receiver`; the file is gone; reboot; the receiver is awake and gets a 3D fix.

- [ ] **Step 5: Write the session and correct the docs**

Add the session to the bench page. Then apply Task 6 Step 3's wording with what was measured, and update the README/CLAUDE.md rows to "kept across reboots, measured". Commit:

```bash
git add docs README.md CLAUDE.md catalog
git commit -m "Bench record: kept off across a reboot on the field laptop

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 8: The tray: "kept off", absent devices, and the login notice (`hammunition-tray` repository)

Runs after `hammunition-tray`'s Debian-package plan has landed, so the new dependency goes into its control file.

**Files:**
- Modify: in hammunition-tray: `main.qml` and `FullRepresentation.qml` (under plasmoid/package/contents/ui), `build.sh` (under packaging/debian; its Depends), `metadata.json` (Version `0.2.0`), `CHANGELOG.md`, `README.md`
- Test: hammunition-tray's `test_applet_package.py` (under tests)

**Interfaces:**
- Consumes: the helper's `state` JSON from Task 3 (`kept`, `attached`, `parked: null`).

- [ ] **Step 1: Write the failing tests**

Append to hammunition-tray's `test_applet_package.py`:

```python
class KeptOff(unittest.TestCase):
    def test_the_notice_is_sent_at_most_once_per_load(self):
        main = read(os.path.join(UI, "main.qml"))
        self.assertIn("import org.kde.notification", main)
        self.assertIn("property bool keptNoticeSent: false", main)
        self.assertRegex(main, r"if \(!keptNoticeSent[^)]*\)")
        self.assertIn("keptNoticeSent = true", main)

    def test_an_absent_device_gets_no_switch(self):
        full = read(os.path.join(UI, "FullRepresentation.qml"))
        self.assertIn("visible: modelData.attached !== false", full)

    def test_an_absent_kept_device_can_be_forgotten(self):
        full = read(os.path.join(UI, "FullRepresentation.qml"))
        self.assertIn('i18n("Forget")', full)
        self.assertIn("root.forget(modelData)", full)

    def test_the_package_depends_on_the_notification_module(self):
        build = read(os.path.join(ROOT, "packaging", "debian", "build.sh"))
        self.assertIn("qml6-module-org-kde-notifications", build)
```

- [ ] **Step 2: Run to verify they fail**

Run: `python3 -m unittest discover -s tests`
Expected: 4 failures.

- [ ] **Step 3: Implement**

`main.qml`: add `import org.kde.notification`; add

```qml
    property bool keptNoticeSent: false

    Notification {
        id: keptNotice
        componentName: "plasma_workspace"
        eventId: "notification"
        iconName: "hammunition-devices"
        title: i18n("Kept off")
    }

    function noticeKept() {
        if (!keptNoticeSent && devices) {
            keptNoticeSent = true;
            const names = devices
                .filter(d => d.attached !== false && d.parked && d.kept)
                .map(d => d.summary || d.name);
            if (names.length > 0) {
                keptNotice.text = names.join(", ");
                keptNotice.sendEvent();
            }
        }
    }

    function forget(device) {
        if (acting) return;
        acting = true;
        lastError = "";
        exec.run("pkexec " + helper + " wake " + target(device));
    }
```

and call `root.noticeKept()` right after `devices = JSON.parse(stdout);` in `handleResult`. `anyParked`/`parkedCount` count only `d.attached !== false && d.parked`.

`FullRepresentation.qml` delegate: the second label's text becomes `modelData.attached === false ? i18n("%1 at %2, kept off, not attached", modelData.name, modelData.address) : (modelData.kept ? i18n("%1 at %2, kept off", modelData.name, modelData.address) : i18n("%1 at %2", modelData.name, modelData.address))`; the `Switch` gets `visible: modelData.attached !== false`; add beside it

```qml
                PlasmaComponents.Button {
                    visible: modelData.attached === false
                    enabled: !root.acting
                    text: i18n("Forget")
                    onClicked: root.forget(modelData)
                }
```

and change the footer label to `i18n("Off stays off across reboots until you turn it back on.")`.

`build.sh`: add `qml6-module-org-kde-notifications` to Depends (measured on Parrot 7.3: it ships `org/kde/notification`). `metadata.json` `Version` `0.2.0`; `CHANGELOG.md` `## [0.2.0]` section; README: the switch now remembers, what the notice is, and "Forget" for an unplugged kept device.

- [ ] **Step 4: Run, reinstall, look at it**

Run: `python3 -m unittest discover -s tests`, then the tray's `install.sh` and `systemctl --user restart plasma-plasmashell`; open the applet and check a kept device reads "kept off", and log out and in to see the notice once.

- [ ] **Step 5: Commit**

```bash
git add plasmoid packaging tests CHANGELOG.md README.md
git commit -m "Kept off in the tray: the label, Forget for an unplugged device, one notice per login

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```
