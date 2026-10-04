# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later
"""A callsign resolves to a name and an address; a grid square says where the station is.
They live in the engine's station file and nowhere else. This opens every screen against
a station full of sentinels and then looks everywhere the console could have put one."""

import os
from pathlib import Path

import pytest

from hammunition.console import config
from hammunition.console.app import Shell, build_registry, write_crash_log
from hammunition.console.config import SCREENS, Config
from hammunition.console.worker import SyncBackground

from .helpers import FakeEngine, document, load, render

SENTINELS = ("ZZ9SENTINEL", "ZZ99zz", "SENTALIAS", "sentinelregion", "usb-SENTINELSERIAL")


def station_body() -> dict[str, object]:
    return {
        **load("station-set"),
        "callsign": SENTINELS[0],
        "grid_square": SENTINELS[1],
        "node_alias": SENTINELS[2],
        "map_regions": [f"north-america/us/{SENTINELS[3]}"],
        "rig_device": f"/dev/serial/by-id/{SENTINELS[4]}-if00",
    }


def test_no_station_value_reaches_a_screen_a_file_or_the_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = tmp_path / "home"
    (home / ".config").mkdir(parents=True)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(home / ".config"))
    env_before = dict(os.environ)
    engine = FakeEngine()
    engine.set(("station", "show"), document("station", station_body()))
    cfg_path = config.config_path(os.environ)
    shell = Shell(
        engine,
        Config(),
        SyncBackground(),
        pane_factory=lambda a, t, e: shell.stack[-1],
        after=lambda s, f: None,
        registry=build_registry(),
        save=lambda c: config.save(c, cfg_path),
    )
    shell.open_screen("home")
    for name in SCREENS[1:]:
        shell.open_screen(name)
    drawn = [render(shell.root, 120, 40)]
    for screen in list(shell.stack):  # every screen, not only the top one
        drawn.append(render(screen.widget(), 120, 40))
    for sentinel in SENTINELS:
        assert not any(sentinel in text for text in drawn), (
            f"{sentinel} was drawn before any reveal"
        )

    station = next(s for s in shell.stack if s.name == "station")
    station.keypress("v")  # type: ignore[attr-defined]
    assert SENTINELS[0] in render(station.widget(), 120, 40)
    station.on_hide()
    assert SENTINELS[0] not in render(station.widget(), 120, 40), (
        "leaving the screen must hide the values again"
    )

    try:
        raise RuntimeError(f"callsign {SENTINELS[0]} grid {SENTINELS[1]}")
    except RuntimeError as exc:
        crash = write_crash_log(exc, config.config_dir(os.environ))
    assert crash is not None

    files = [p for p in home.rglob("*") if p.is_file()]
    assert {p.name for p in files} == {"config.toml", "crash.log"}, files
    for path in files:
        data = path.read_bytes()
        for sentinel in SENTINELS:
            assert sentinel.encode() not in data, f"{sentinel} found in {path.name}"
    assert dict(os.environ) == env_before, "the console changed the environment"
    assert not any(s in v for v in os.environ.values() for s in SENTINELS)
    assert config.load(cfg_path).last_screen == SCREENS[-1]
