# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later
"""A few screens rendered at a fixed size and compared with a reviewed text file. After an
intended change, regenerate with `UPDATE_GOLDEN=1 python3 -m pytest tests/test_golden.py`
and READ the diff before committing: a golden nobody reads is not a check."""

import os
from pathlib import Path

import pytest

from hammunition.console.screens.home import HomeScreen
from hammunition.console.screens.install import InstallScreen
from hammunition.console.screens.plan import PlanScreen
from hammunition.console.screens.update import UpdateScreen

from .fixture_scan import findings
from .helpers import FakeContext, FakeEngine, render

GOLDEN = Path(__file__).parent / "golden"


def check(name: str, drawn: str) -> None:
    path = GOLDEN / f"{name}.txt"
    if os.environ.get("UPDATE_GOLDEN") == "1":
        GOLDEN.mkdir(exist_ok=True)
        path.write_text(drawn + "\n")
        return
    assert path.exists(), (
        f"missing golden {name}: run UPDATE_GOLDEN=1 python3 -m pytest tests/test_golden.py and review it"
    )
    assert drawn + "\n" == path.read_text(), (
        f"{name} changed: review the diff; if intended, regenerate with UPDATE_GOLDEN=1"
    )


def drawn(screen: object) -> str:
    screen.on_show()  # type: ignore[attr-defined]
    return render(screen.widget(), 80, 24)  # type: ignore[attr-defined]


@pytest.mark.parametrize(
    "name,build",
    [
        ("home", lambda: HomeScreen(FakeContext())),
        ("install-with-e1", lambda: InstallScreen(FakeContext())),
        (
            "install-without-e1",
            lambda: InstallScreen(FakeContext(engine=FakeEngine(suffix="-without"))),
        ),
        ("plan-station", lambda: PlanScreen(FakeContext(), "install", ["station"])),
        ("update-with-e2", lambda: UpdateScreen(FakeContext())),
        (
            "update-without-e2",
            lambda: UpdateScreen(FakeContext(engine=FakeEngine(suffix="-without"))),
        ),
    ],
)
def test_golden(name: str, build: object) -> None:
    check(name, drawn(build()))  # type: ignore[operator]


def test_goldens_carry_no_identifier() -> None:
    for path in sorted(GOLDEN.glob("*.txt")):
        assert findings(path.read_text()) == [], path.name
