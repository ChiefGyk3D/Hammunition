# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""The udev sweep's pair parser reads every syntax a rule can use.

brltty had ZERO rows in a sweep that claimed to filter nothing, because its
rules say ``ENV{PRODUCT}=="403/de58/*"`` and the parser read only
``ATTRS{idVendor}`` (2026-09-12, D-047). These lines are taken verbatim from
the shipped files that proved each case.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location(
    "udev_rule_pairs", REPO_ROOT / "scripts" / "udev_rule_pairs.py"
)
assert spec and spec.loader
pairs = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pairs)

BRLTTY_CH340 = (
    'ENV{PRODUCT}=="1a86/7523/*", ATTRS{idVendor}=="1a40", ATTRS{idProduct}=="0101", '
    'ENV{BRLTTY_BRAILLE_DRIVER}="bm", GOTO="brltty_usb_run"'
)
BRLTTY_HEDO = 'ENV{PRODUCT}=="403/de58/*", ENV{BRLTTY_BRAILLE_DRIVER}="hd", GOTO="brltty_usb_run"'
RTLSDR = 'SUBSYSTEMS=="usb", ATTRS{idVendor}=="0bda", ATTRS{idProduct}=="2838", MODE:="0666"'
HACKRF_RAD1O = 'ENV{ID_VENDOR_ID}=="1fc9", ENV{ID_MODEL_ID}=="0042", MODE="660", GROUP="plugdev"'


def test_the_attrs_syntax_still_reads() -> None:
    assert pairs.find_pair(RTLSDR) == ("0bda", "2838")


def test_env_product_reads_and_pads_the_vendor_the_kernel_writes_without_zeros() -> None:
    """``403/de58`` is the kernel's PRODUCT string for 0403:de58."""
    assert pairs.find_pair(BRLTTY_HEDO) == ("0403", "de58")


def test_env_product_wins_over_a_parent_attrs_on_the_same_line() -> None:
    """brltty's CH340 line names the device by PRODUCT and its *parent hub* by
    ATTRS. The pair the rule is about is the device's. Read the other way
    round, the sweep would file a Terminus hub as a braille display."""
    assert pairs.find_pair(BRLTTY_CH340) == ("1a86", "7523")


def test_id_vendor_id_syntax_reads() -> None:
    assert pairs.find_pair(HACKRF_RAD1O) == ("1fc9", "0042")


def test_half_a_pair_is_nothing() -> None:
    assert pairs.find_pair('ATTRS{idVendor}=="0403", MODE="0666"') is None
    assert pairs.find_pair('ENV{ID_VENDOR_ID}=="0403"') is None
    assert pairs.find_pair("# Device: 0403:DE58") is None


def test_the_old_parser_missed_brltty_which_is_why_this_module_exists() -> None:
    """Falsifiability: the regex that was the whole parser before 2026-09-12
    returns nothing for the line the fix was written for."""
    assert pairs.ATTRS_PAIR.search(BRLTTY_HEDO) is None
    assert pairs.find_pair(BRLTTY_HEDO) is not None


def test_the_sweep_script_imports_this_module_rather_than_inlining_it() -> None:
    sweep = (REPO_ROOT / "scripts" / "udev-sweep.sh").read_text()
    runner = (REPO_ROOT / "scripts" / "run-udev-sweep.sh").read_text()
    assert "from udev_rule_pairs import find_pair" in sweep
    assert 'udev_rule_pairs.py":/udev_rule_pairs.py:ro' in runner
    # CI must go through the runner rather than restate its podman line: the
    # restated line mounted only the sweep script, so the weekly citation job
    # died on `import udev_rule_pairs` from the day the parser became a module.
    ci = (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text()
    assert "run: scripts/run-udev-sweep.sh debian-13" in ci
    assert 'udev-sweep.sh":/sweep.sh' not in ci
    assert "PAIR = re.compile" not in sweep, "the inline copy is back; it cannot be tested there"
