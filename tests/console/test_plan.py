# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later
from typing import Any

import pytest

from hammunition.console.engine import EngineRefused
from hammunition.console.screens.plan import (
    PlanScreen,
    ResultScreen,
    Section,
    blocker_lines,
    install_sections,
    removal_sections,
)

from .helpers import FakeContext, FakeEngine, document, load, render


def view(**over: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "packages": [],
        "displaced": [],
        "apt_release": None,
        "no_recommends": None,
        "repos": [],
        "mirror": None,
        "data": [],
        "maps": None,
        "memberships": [],
        "consent_gates": [],
        "config_files": [],
        "user_services": [],
        "desktops_read": None,
        "deferrals": [],
        "notes": [],
        "records": None,
        "sudo": None,
        "commands": [],
        "suggestion_notes": [],
        "region_notes": [],
    }
    return {**base, **over}


def titles(sections: list[Section]) -> list[str]:
    return [s.title for s in sections]


def test_an_empty_view_has_no_sections() -> None:
    assert install_sections(view()) == []


def test_the_recorded_plan_lists_its_units_in_order_with_method_state_and_requester() -> None:
    plan = load("plan-station")["install"]
    sections = install_sections(plan)
    units = sections[0]
    assert units.title == "Units, in install order"
    first = plan["packages"][0]
    assert units.lines[0].startswith(f"{first['name']}  {first['method']}  {first['state']}")
    assert all(s.lines for s in sections), "a section with no lines must be hidden"


def test_the_gated_plan_says_you_will_type_yes_and_lists_each_risk() -> None:
    plan = load("plan-gated")["install"]
    gate = next(
        s for s in install_sections(plan) if s.title.startswith("You will be asked to type yes")
    )
    risk = plan["consent_gates"][0]["risk_lines"][0]
    assert any(risk in line for line in gate.lines) and gate.lines[0].startswith(
        plan["consent_gates"][0]["profile"]
    )


def test_every_section_the_spec_names_is_built_from_the_documents_real_field_names() -> None:
    v = view(
        packages=[
            {
                "name": "u1",
                "method": "apt",
                "state": "will install",
                "requested_by": ["requested"],
                "apt": [],
            }
        ],
        displaced=[{"package": "librtlsdr0", "declared_by": "u1"}],
        apt_release={"release": "trixie-backports", "packages": ["p1"]},
        no_recommends={"units": ["u1"], "packages": ["p2"]},
        repos=[
            {
                "name": "r",
                "unit": "u1",
                "packages": ["p3"],
                "uri": "https://example.org/apt",
                "suites": ["s"],
                "components": ["main"],
                "key_fingerprint": "AB CD",
                "sources": "/etc/apt/sources.list.d/r.sources",
                "keyring": "/etc/apt/keyrings/r.gpg",
                "consent_env_var": "X",
            }
        ],
        mirror={"url": "http://lan/", "ignored": False, "text": "mirror text"},
        data=[
            {
                "unit": "d1",
                "total_size": 5,
                "total_human": "5 MiB",
                "licence": "CC0",
                "licence_url": "u",
                "artifacts": [{"url": "https://e/x", "size": 5, "size_human": "5 MiB"}],
                "installs_under": "share/d1",
                "verified_by": "sha256, pinned by Hammunition",
                "approximate": False,
            }
        ],
        memberships=[
            {
                "user": "me",
                "group": "dialout",
                "package": "u1",
                "detail": "serial ports",
                "reverse_hint": "gpasswd -d",
            }
        ],
        config_files=[
            {
                "unit": "u1",
                "path": "/etc/x.conf",
                "mode": "0644",
                "append": False,
                "backup_existing": True,
                "fills": ["callsign"],
            }
        ],
        user_services=[
            {
                "unit": "u1",
                "name": "svc",
                "path": "/p",
                "exec": "/bin/x",
                "fills": [],
                "listen": "127.0.0.1:4532",
                "starts_now": False,
            }
        ],
        deferrals=[
            {
                "kind": "config",
                "subject": "/etc/y",
                "what": "not written",
                "why": "no callsign",
                "remedy": "station set",
            }
        ],
        notes=["a note"],
        records={"log": "/home/user/tx.jsonl", "handed_to": None},
        sudo={"keepalive": True, "interval_seconds": 240, "text": "sudo is asked once"},
        commands=[
            {
                "description": "d",
                "display": "sudo apt-get install u1",
                "argv": [],
                "action": None,
                "requires_root": True,
                "sources": [],
            }
        ],
    )
    flat = "\n".join(line for s in install_sections(v) for line in [s.title, *s.lines])
    for needle in (
        "u1  apt  will install  (requested by requested)",
        "librtlsdr0",
        "trixie-backports",
        "p2",
        "https://example.org/apt",
        "key fingerprint AB CD",
        "/etc/apt/keyrings/r.gpg",
        "mirror text",
        "d1: 5 MiB, licence CC0",
        "sha256, pinned by Hammunition",
        "me is added to group dialout",
        "/etc/x.conf",
        "fills: callsign",
        "svc",
        "127.0.0.1:4532",
        "no callsign",
        "station set",
        "a note",
        "/home/user/tx.jsonl",
        "sudo is asked once",
        "$ sudo apt-get install u1  (root)",
    ):
        assert needle in flat, needle
    assert "None" not in flat


def test_map_regions_show_sizes_and_never_the_region_names() -> None:
    v = view(
        maps={
            "fetch": [
                {
                    "region": "north-america/us/sentinelregion",
                    "snapshot": "s",
                    "size": 1,
                    "size_human": "1 B",
                    "verified_by": "md5",
                    "nothing_to_do": False,
                }
            ],
            "current": [],
            "convert": [],
            "kept": [],
            "licence": "ODbL",
            "licence_url": "u",
            "download_total": 1,
            "download_total_human": "1 B",
            "disk_total": 9,
            "disk_total_human": "9 B",
            "estimate_note": "measured",
            "terrain": None,
            "boundaries": None,
            "unknown_country": False,
        }
    )
    flat = "\n".join(line for s in install_sections(v) for line in s.lines)
    assert (
        "sentinelregion" not in flat
        and "1 region(s) to download" in flat
        and "download 1 B, disk 9 B" in flat
    )


def test_station_values_are_named_never_shown() -> None:
    v = view(
        config_files=[
            {
                "unit": "u",
                "path": "/etc/a",
                "mode": "0600",
                "append": False,
                "backup_existing": False,
                "fills": ["callsign", "grid_square"],
            }
        ]
    )
    flat = "\n".join(line for s in install_sections(v) for line in s.lines)
    assert "callsign, grid_square" in flat and "N0CALL" not in flat


def test_null_fields_are_tolerated() -> None:
    v = view(
        packages=[{"name": "u", "method": None, "state": None, "requested_by": None, "apt": None}],
        deferrals=[{"kind": "package", "subject": "s", "what": "w", "why": "y", "remedy": None}],
    )
    flat = "\n".join(line for s in install_sections(v) for line in s.lines)
    assert "None" not in flat


def test_removal_sections() -> None:
    plan = load("plan-uninstall")["removal"]
    sections = removal_sections(plan)
    assert sections and all(s.lines for s in sections)
    flat = [s.title for s in sections]
    assert any("Steps" in t for t in flat) or plan["commands"] == []


def test_blocker_lines_show_subject_reason_and_the_remedy_only_when_there_is_one() -> None:
    lines = blocker_lines(
        [
            {"subject": "x", "reason": "because", "remedy": None},
            {"subject": "y", "reason": "r\x1b[2J", "remedy": "do z"},
        ]
    )
    assert lines[0] == "x: because" and lines[2] == "   remedy: do z" and len(lines) == 3
    assert "\x1b" not in "".join(lines) and not any("None" in line for line in lines)


def test_a_planned_install_shows_its_sections_and_says_nothing_changed_yet() -> None:
    ctx = FakeContext()
    screen = PlanScreen(ctx, "install", ["station"])
    screen.on_show()
    out = render(screen.widget(), 100, 40)
    assert "Nothing has been changed yet" in out and "Units, in install order" in out
    assert "b back" in out and "changes nothing" in out
    assert screen.runnable and ctx.panes == []


def test_capital_r_runs_the_real_command_in_a_pane_without_dry_run_or_json() -> None:
    ctx = FakeContext()
    screen = PlanScreen(ctx, "install", ["station"])
    screen.on_show()
    assert screen.keypress("r") is None and ctx.panes == []  # lowercase r only re-plans
    assert screen.keypress("R") is None
    pane = ctx.panes[0]
    assert pane.argv == ["hammunition", "install", "station"] and pane.title == "install station"
    assert "--dry-run" not in pane.argv and "--json" not in pane.argv


def test_uninstall_plans_and_runs_the_uninstall_verb() -> None:
    ctx = FakeContext()
    screen = PlanScreen(ctx, "uninstall", ["station"])
    screen.on_show()
    assert ctx.engine.calls[-1] == ("uninstall", "station", "--dry-run")
    screen.keypress("R")
    assert ctx.panes[0].argv == ["hammunition", "uninstall", "station"]


def test_a_refused_plan_shows_blockers_and_cannot_be_run() -> None:
    ctx = FakeContext()
    screen = PlanScreen(ctx, "install", ["no-such-unit-xyz"])
    screen.on_show()
    out = render(screen.widget(), 100, 30)
    assert (
        "refused" in out and "Nothing will be run" in out and "Units, in install order" not in out
    )
    blocker = load("plan-refused")["blockers"][0]
    assert blocker["subject"] in out and blocker["reason"][:20] in out
    assert screen.runnable is False and screen.keypress("R") == "R" and ctx.panes == []


def test_an_engine_error_is_shown_and_runs_nothing() -> None:
    engine = FakeEngine()
    engine.set(("install", "x", "--dry-run"), EngineRefused(2, "no catalog"))
    ctx = FakeContext(engine=engine)
    screen = PlanScreen(ctx, "install", ["x"])
    screen.on_show()
    out = render(screen.widget(), 100, 20)
    assert "no catalog" in out and "Nothing was run" in out
    screen.keypress("R")
    assert ctx.panes == []


def test_a_malicious_reason_never_reaches_the_terminal() -> None:
    engine = FakeEngine()
    engine.set(
        ("install", "x", "--dry-run"),
        document(
            "plan",
            {
                "action": "install",
                "requested": ["x"],
                "outcome": "refused",
                "blockers": [{"subject": "s", "reason": "\x1b]0;pwned\x07bad", "remedy": None}],
                "install": None,
                "removal": None,
            },
            exit_code=2,
        ),
    )
    ctx = FakeContext(engine=engine)
    screen = PlanScreen(ctx, "install", ["x"])
    screen.on_show()
    assert "\x1b" not in render(screen.widget(), 100, 20)


def test_when_the_pane_ends_the_result_replaces_it_and_back_returns_to_the_list() -> None:
    ctx = FakeContext()
    screen = PlanScreen(ctx, "install", ["station"])
    screen.on_show()
    screen.keypress("R")
    ctx.panes[0].on_exit(0)
    result = ctx.replaced[-1]
    assert isinstance(result, ResultScreen)
    out = render(result.widget(), 100, 20)
    assert "Exit code: 0" in out
    run = next(r for r in load("logs")["runs"] if r["command"] == "install")
    assert (
        f"Engine log: {run['result']} (exit {run['exit_code']})" in out
        or "Engine log: running" in out
    )
    assert "Latest transaction:" in out
    assert result.keypress("b") is None and ctx.popped == 2


def test_a_cut_off_program_has_no_exit_code_and_says_so() -> None:
    result = ResultScreen(FakeContext(), "install", ["station"], None)
    result.on_show()
    assert "Exit code: unknown" in render(result.widget(), 100, 20)


def test_the_result_survives_a_failing_log_read() -> None:
    engine = FakeEngine()
    engine.set(("logs",), ValueError("unreadable"))
    result = ResultScreen(FakeContext(engine=engine), "install", ["station"], 1)
    result.on_show()
    out = render(result.widget(), 100, 20)
    assert "Exit code: 1" in out and "Engine log: unknown" in out and "unreadable" in out


def _maps(**over: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "fetch": [],
        "current": [],
        "licence": "ODbL",
        "download_total_human": "1 B",
        "disk_total_human": "2 B",
        "estimate_note": "n",
        "terrain": None,
    }
    return {**base, **over}


def test_the_topo_size_consent_sentence_is_shown_with_its_typed_yes_label() -> None:
    terrain = {
        "licence": "PD",
        "download_total_human": "3 GiB",
        "topo": {
            "download_total_human": "9 GiB",
            "disk_total_human": "14 GiB",
            "size_consent": "Over 10 GB\x1b[2J: type yes",
        },
    }
    flat = "\n".join(
        line for s in install_sections(view(maps=_maps(terrain=terrain))) for line in s.lines
    )
    assert "asked to type yes in the pane" in flat and "Over 10 GB" in flat and "\x1b" not in flat
    assert "terrain: download 3 GiB" in flat and "US Topo: download 9 GiB, disk 14 GiB" in flat


@pytest.mark.parametrize(
    "terrain",
    [
        None,
        {"licence": "PD", "download_total_human": "3 GiB"},
        {"licence": "PD", "download_total_human": "3 GiB", "topo": None},
        {"licence": "PD", "download_total_human": "3 GiB", "topo": {"size_consent": None}},
    ],
)
def test_a_missing_or_null_size_consent_renders_without_it(terrain: Any) -> None:
    flat = "\n".join(
        line for s in install_sections(view(maps=_maps(terrain=terrain))) for line in s.lines
    )
    assert "type yes" not in flat and "None" not in flat


def test_an_approximate_data_total_says_so() -> None:
    d = {
        "unit": "d",
        "total_human": "5 MiB",
        "licence": "x",
        "verified_by": "v",
        "artifacts": [],
        "installs_under": "s",
        "approximate": True,
    }
    flat = "\n".join(line for s in install_sections(view(data=[d])) for line in s.lines)
    assert "about 5 MiB (approximate" in flat


def test_the_longest_plan_at_80x24_shows_the_run_and_back_hint_on_the_first_screen() -> None:
    ctx = FakeContext()
    screen = PlanScreen(ctx, "install", ["station"])
    screen.on_show()
    out = render(screen.widget(), 80, 24)
    assert (
        "Nothing has been changed yet" in out
        and "R run this in a terminal pane   b back: changes nothing" in out
    )
    assert "Units, in install order" in out


def test_the_topo_size_consent_fixture_variant_is_shown() -> None:
    engine = FakeEngine()
    plan = load("plan-station-size-consent")
    engine.set(
        ("install", "station", "--dry-run"),
        document("plan", {k: v for k, v in plan.items() if k not in ("schema", "kind", "engine")}),
    )
    screen = PlanScreen(FakeContext(engine=engine), "install", ["station"])
    screen.on_show()
    assert "asked to type yes in the pane" in render(screen.widget(), 100, 60)


def test_a_plan_is_read_once_across_re_shows_and_r_re_plans() -> None:
    ctx = FakeContext()
    screen = PlanScreen(ctx, "install", ["station"])

    def plans() -> list[tuple[str, ...]]:
        return [c for c in ctx.engine.calls if c[-1] == "--dry-run"]

    screen.on_show()
    screen.on_show()
    assert len(plans()) == 1 and screen.doc is not None
    assert screen.keypress("r") is None
    assert len(plans()) == 2


def test_dry_run_reads_have_no_timeout_and_other_reads_keep_the_default() -> None:
    ctx = FakeContext()
    PlanScreen(ctx, "install", ["station"]).on_show()
    PlanScreen(ctx, "uninstall", ["station"]).on_show()
    ctx.engine.read("status")
    assert ctx.engine.timeouts[("install", "station", "--dry-run")] is None
    assert ctx.engine.timeouts[("uninstall", "station", "--dry-run")] is None
    assert ctx.engine.timeouts[("status",)] == 180.0


def test_the_loading_line_warns_that_map_profiles_take_minutes() -> None:
    from hammunition.console.worker import Background

    class Held(Background):
        def submit(self, call: Any, done: Any) -> None:
            pass

        def attach(self, loop: Any) -> None:
            pass

    screen = PlanScreen(FakeContext(bg=Held()), "install", ["navigation"])
    screen.on_show()
    assert "can take minutes for map profiles" in render(screen.widget(), 100, 10)
