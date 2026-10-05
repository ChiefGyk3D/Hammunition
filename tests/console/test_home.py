# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later
from typing import Any

import pytest

from hammunition.console.engine import EngineMissing, EngineRefused
from hammunition.console.screens.home import ChecksScreen, HomeScreen

from .helpers import FakeContext, FakeEngine, document, load, render


def shown(ctx: FakeContext) -> str:
    home = HomeScreen(ctx)
    home.on_show()
    return render(home.widget(), 100, 30)


def test_home_summarises_each_document() -> None:
    ctx = FakeContext()
    out = shown(ctx)
    d = load("doctor")
    assert f"Doctor: {d['fails']} fail, {d['warns']} warn, {d['healthy']} healthy" in out
    assert "Station: set" in out
    run = load("logs")["runs"][0]
    assert f"Last run: {run['command']} - {run['result']}" in out
    update = load("update-all")
    assert f"Behind the pin: {update['counts']['behind_pin']}" in out
    assert "retired in the catalog: 1" in out


def test_home_never_prints_a_station_value() -> None:
    out = shown(FakeContext())
    station = load("station-set")
    for value in (station["callsign"], station["grid_square"], station["node_alias"]):
        assert value not in out


def test_the_shared_header_is_fed_from_the_documents() -> None:
    ctx = FakeContext()
    shown(ctx)
    assert ctx.shared.engine_version == load("status")["engine"]
    assert ctx.shared.station_set is True
    d = load("doctor")
    assert ctx.shared.doctor == (d["fails"], d["warns"], d["healthy"])
    assert ctx.header_refreshes > 0 and ctx.shared.target != "?"


def test_a_station_that_is_not_set_says_so() -> None:
    ctx = FakeContext(engine=FakeEngine(station="none"))
    assert "Station: not set" in shown(ctx)
    assert ctx.shared.station_set is False


def test_an_engine_without_e2_refusing_update_leaves_the_rest_working() -> None:
    ctx = FakeContext(engine=FakeEngine(suffix="-without"))
    out = shown(ctx)
    assert "Behind the pin: unknown" in out and "the engine refused (exit 2)" in out
    assert "Doctor:" in out and "Station: set" in out


def test_each_read_fails_alone() -> None:
    engine = FakeEngine()
    engine.set(("station", "show"), ValueError("boom"))
    out = shown(FakeContext(engine=engine))
    assert "Station: unknown" in out and "ValueError: boom" in out and "Doctor: " in out


def test_a_fatal_engine_error_is_handed_to_the_shell() -> None:
    engine = FakeEngine()
    engine.set(("status",), EngineMissing("no engine"))
    ctx = FakeContext(engine=engine)
    HomeScreen(ctx).on_show()
    assert [type(e) for e in ctx.fatals] == [EngineMissing]


def test_missing_fields_and_an_empty_log_never_crash_or_say_none() -> None:
    engine = FakeEngine()
    engine.set(("doctor",), document("doctor", {"checks": []}))
    engine.set(("logs",), document("logs", {"directory": "/x", "runs": []}))
    engine.set(("update",), document("update", {"rows": [], "counts": {}}))
    out = shown(FakeContext(engine=engine))
    assert "Doctor: ? fail, ? warn, ? healthy" in out and "Last run: no runs yet" in out
    assert "Behind the pin: ?" in out and "None" not in out


def test_engine_text_is_cleaned_of_control_sequences() -> None:
    engine = FakeEngine()
    engine.set(("doctor",), EngineRefused(2, "\x1b[2Jmalicious"))
    out = shown(FakeContext(engine=engine))
    assert "\x1b" not in out and "malicious" in out


def test_digits_open_the_screens_in_order() -> None:
    ctx = FakeContext()
    home = HomeScreen(ctx)
    home.on_show()
    for digit, name in zip(
        "123456", ("install", "station", "secrets", "logs", "update", "help"), strict=True
    ):
        assert home.keypress(digit) is None
        assert ctx.opened[-1] == (name, {})
    assert home.keypress("9") == "9"


def test_enter_on_a_menu_row_opens_it() -> None:
    ctx = FakeContext()
    home = HomeScreen(ctx)
    home.on_show()
    row = next(r for r in home._walker if getattr(r, "value", None) == "logs")
    row.keypress((80,), "enter")
    assert ctx.opened[-1] == ("logs", {})


def checks(*items: dict[str, Any]) -> list[dict[str, Any]]:
    return list(items)


def test_the_checks_list_shows_the_fix_text_and_never_runs_it() -> None:
    ctx = FakeContext()
    engine = FakeEngine()
    engine.set(
        ("doctor",),
        document(
            "doctor",
            {
                "fails": 1,
                "warns": 0,
                "healthy": 1,
                "checks": checks(
                    {
                        "name": "udev",
                        "status": "fail",
                        "detail": "rules missing\x1b[2J",
                        "fix": "hammunition hardware apply",
                    },
                    {"name": "disk", "status": "ok", "detail": "plenty", "fix": None},
                ),
            },
        ),
    )
    ctx.engine = engine
    home = HomeScreen(ctx)
    home.on_show()
    row = next(r for r in home._walker if getattr(r, "value", None) == "doctor")
    row.keypress((80,), "enter")
    screen = ctx.pushed[-1]
    assert isinstance(screen, ChecksScreen)
    out = render(screen.widget(), 100, 20)
    assert "fix: hammunition hardware apply" in out and "rules missing" in out and "\x1b" not in out
    assert "never runs" in out and "None" not in out
    assert ctx.panes == []


@pytest.mark.parametrize("state", ["fail", "warn", "ok", "info", "future-state"])
def test_every_check_state_renders(state: str) -> None:
    screen = ChecksScreen(
        FakeContext(), [{"name": "n", "status": state, "detail": "d", "fix": None}]
    )
    assert f"[{state}] n: d" in render(screen.widget(), 100, 10)


def test_null_fields_degrade_to_unknown() -> None:
    engine = FakeEngine()
    engine.set(
        ("doctor",),
        document(
            "doctor",
            {
                "fails": None,
                "warns": None,
                "healthy": None,
                "checks": [{"name": None, "status": None, "detail": None, "fix": None}],
            },
        ),
    )
    engine.set(
        ("logs",),
        document(
            "logs",
            {"runs": [{"command": None, "result": None, "exit_code": None, "started": None}]},
        ),
    )
    engine.set(("update",), document("update", {"rows": None, "counts": None}))
    engine.set(("station", "show"), document("station", {"callsign": None, "grid_square": None}))
    ctx = FakeContext(engine=engine)
    out = shown(ctx)
    assert (
        "None" not in out
        and "Doctor: ? fail" in out
        and "Last run: ? - ?" in out
        and "Behind the pin: ?" in out
    )
    assert ctx.shared.doctor is None
    screen = ChecksScreen(ctx, [{"name": None, "status": None, "detail": None, "fix": None}])
    assert "None" not in render(screen.widget(), 100, 10)


def lagging_doctor() -> Any:
    return document(
        "doctor",
        {
            "checks": [
                {
                    "name": "engine version",
                    "status": "warn",
                    "detail": "0.20.0 (checkout), 0.19.0 (installed): the venv lags the tree",
                    "fix": "hammunition self-update",
                    "fix_argv": ["hammunition", "self-update"],
                }
            ],
            "fails": 0,
            "warns": 1,
            "healthy": 0,
        },
    )


def test_home_offers_the_engine_update_when_doctor_reports_the_lag() -> None:
    engine = FakeEngine()
    engine.set(("doctor",), lagging_doctor())
    ctx = FakeContext(engine=engine)
    out = shown(ctx)
    assert "0.20.0 (checkout), 0.19.0 (installed)" in out
    assert "Press U to run `hammunition self-update`" in out


def test_u_confirms_then_runs_self_update_in_a_pane() -> None:
    engine = FakeEngine()
    engine.set(("doctor",), lagging_doctor())
    ctx = FakeContext(engine=engine)
    home = HomeScreen(ctx)
    home.on_show()
    assert home.keypress("U") is None
    confirm = ctx.pushed[-1]
    assert "hammunition self-update" in render(confirm.widget(), 100, 20)
    assert ctx.panes == []  # nothing runs until the operator confirms
    confirm.keypress("R")
    assert ctx.panes[-1].argv == ["hammunition", "self-update"]
    assert "--yes" not in ctx.panes[-1].argv


def test_no_offer_and_u_is_inert_when_the_versions_agree() -> None:
    ctx = FakeContext()
    home = HomeScreen(ctx)
    home.on_show()
    assert "self-update" not in render(home.widget(), 100, 30)
    assert home.keypress("U") == "U" and ctx.pushed == []
