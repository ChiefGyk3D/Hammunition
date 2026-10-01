# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""An in-process step records what it learned while running.  D-070.

A fetch knows only once it has run whether its bytes came from the LAN
mirror or the publisher, and the transaction log is where that belongs.
"""

from __future__ import annotations

import json
from pathlib import Path

from hammunition.backends import Action
from hammunition.distro import Target
from hammunition.execute import execute
from hammunition.plan import InstallPlan
from hammunition.state import TransactionLog


class NoRunner:
    def run(self, *args: object, **kwargs: object) -> object:  # pragma: no cover
        raise AssertionError("no command is run here")


def _ends(tmp_path: Path, action: Action) -> list[dict[str, object]]:
    log = TransactionLog(path=tmp_path / "t.jsonl")
    plan = InstallPlan(target=Target(distro="debian", version="13", arch="x86_64"), packages=())
    report = execute([action], NoRunner(), log=log, plan=plan)  # type: ignore[arg-type]
    assert report.ok
    entries = [json.loads(line) for line in log.path.read_text().splitlines()]
    return [e for e in entries if e["event"] == "action_end"]


def test_facts_a_step_fills_while_running_reach_action_end(tmp_path: Path) -> None:
    facts: dict[str, str] = {}

    def perform() -> str:
        facts.update(source="mirror", fetched_from="http://bunker.lan:8080/u/n")
        return "downloaded"

    action = Action(kind="fetch", description="d", detail="x", perform=perform, facts=facts)
    (end,) = _ends(tmp_path, action)
    assert end["source"] == "mirror" and end["fetched_from"] == "http://bunker.lan:8080/u/n"


def test_a_step_with_no_facts_logs_exactly_what_it_did_before(tmp_path: Path) -> None:
    action = Action(kind="fetch", description="d", detail="x", perform=lambda: "ok")
    (end,) = _ends(tmp_path, action)
    assert set(end) == {"event", "version", "timestamp", "kind", "detail", "outcome"}


def test_a_fact_cannot_overwrite_the_entrys_own_keys(tmp_path: Path) -> None:
    facts: dict[str, str] = {}

    def perform() -> str:
        facts.update(event="forged", kind="forged", source="publisher")
        return "ok"

    (end,) = _ends(
        tmp_path, Action(kind="fetch", description="d", detail="x", perform=perform, facts=facts)
    )
    assert end["event"] == "action_end" and end["kind"] == "fetch"
    assert end["source"] == "publisher"


def test_sources_default_to_none_and_facts_do_not_affect_equality() -> None:
    def perform() -> str:
        return ""

    a = Action(kind="fetch", description="d", detail="x", perform=perform)
    b = Action(kind="fetch", description="d", detail="x", perform=perform, facts={"k": "v"})
    assert a.sources == () and a == b
