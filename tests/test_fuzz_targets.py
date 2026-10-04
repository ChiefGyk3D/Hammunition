# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""The Atheris targets under ``fuzz/`` stay runnable.

GYST's python-fuzz.yml runs them for a fixed time, but only in CI; a target that
rots (an import that moved, a signature that changed) would otherwise be found
a week later. Each target's ``TestOneInput`` is called here on a handful of
seeds, without ``atheris.Fuzz()``, and must not raise.
"""

from __future__ import annotations

import importlib
import random
from collections.abc import Callable
from pathlib import Path

import pytest

atheris = pytest.importorskip("atheris")

FUZZ_DIR = Path(__file__).resolve().parent.parent / "fuzz"
TARGETS = sorted(p.stem for p in FUZZ_DIR.glob("fuzz_*.py"))

_RANDOM = random.Random(20261004).randbytes(64 * 1024)
SEEDS: dict[str, bytes] = {
    "empty": b"",
    "zeros": bytes(256),
    "ones": b"\xff" * 256,
    "text": b"ID=debian\nFN31pr\n{}\n<gpx/>\ncallsign,output_mhz\n",
    "truncated": b'{"class":"TPV","device":"/dev/ttyACM0","mo',
    "random": _RANDOM,
}


@pytest.fixture(autouse=True)
def _fuzz_importable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.syspath_prepend(str(FUZZ_DIR))


def _load(name: str) -> Callable[[bytes], None]:
    module = importlib.import_module(name)
    func: Callable[[bytes], None] = module.TestOneInput
    return func


def test_the_targets_exist() -> None:
    assert len(TARGETS) >= 6, TARGETS


@pytest.mark.parametrize("seed", SEEDS)
@pytest.mark.parametrize("target", TARGETS)
def test_target_accepts_seed(target: str, seed: str) -> None:
    _load(target)(SEEDS[seed])


@pytest.mark.parametrize("target", TARGETS)
def test_target_survives_many_random_inputs(target: str) -> None:
    run = _load(target)
    rng = random.Random(target)
    for _ in range(60):
        run(rng.randbytes(rng.randint(0, 4096)))
