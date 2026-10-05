# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import urwid

from hammunition.console.context import Context, header_target
from hammunition.console.engine import Document
from hammunition.console.fmt import first_line
from hammunition.console.screens.base import ConfirmScreen, Row, Screen, text
from hammunition.console.screens.plan import PlanScreen
from hammunition.console.walkthrough import MARK, STARTER, Step, show_checklist, steps

READS: dict[str, tuple[str, ...]] = {
    "status": ("status",),
    "doctor": ("doctor",),
    "station": ("station", "show"),
    "logs": ("logs",),
    "update": ("update",),
    "list": (
        "list",
    ),  # the first-run checklist reads the starter profile's installed state from it
}
MENU = (
    ("install", "Install", "pick a profile or unit, read the plan, run it"),
    ("station", "Station", "your callsign, grid square, maps and rig"),
    ("logs", "Logs", "what each run did"),
    ("update", "Update", "installed versus the catalog"),
    ("help", "Help", "keys, and what each profile is for"),
)


def _count(body: Mapping[str, Any], key: str) -> str:
    value = body.get(key)
    return str(value) if isinstance(value, int) and not isinstance(value, bool) else "?"


def _s(value: object, default: str = "?") -> str:
    return default if value is None else str(value)


def doctor_text(doc: Document | None, error: str | None) -> str:
    if doc is not None:
        b = doc.body
        return (
            f"Doctor: {_count(b, 'fails')} fail, {_count(b, 'warns')} warn, "
            f"{_count(b, 'healthy')} healthy  (Enter lists the checks)"
        )
    if error:
        return f"Doctor: unavailable - {first_line(error)}"
    return "Doctor: checking (a few seconds)..."


def station_text(doc: Document | None, error: str | None) -> str:
    if doc is not None:
        both = doc.body.get("callsign") is not None and doc.body.get("grid_square") is not None
        return "Station: set" if both else "Station: not set  (open Station to set it)"
    if error:
        return f"Station: unknown - {first_line(error)}"
    return "Station: checking..."


def last_run_text(doc: Document | None, error: str | None) -> str:
    if doc is not None:
        runs = doc.body.get("runs")
        if not isinstance(runs, list):
            return "Last run: unknown"
        if not runs or not isinstance(runs[0], dict):
            return "Last run: no runs yet"
        r = runs[0]
        code = r.get("exit_code")
        tail = f" (exit {code})" if isinstance(code, int) and not isinstance(code, bool) else ""
        return f"Last run: {_s(r.get('command'))} - {_s(r.get('result'))}{tail}  {r.get('started') or ''}".rstrip()
    if error:
        return f"Last run: unknown - {first_line(error)}"
    return "Last run: checking..."


def behind_text(doc: Document | None, error: str | None) -> str:
    if doc is not None:
        counts = doc.body.get("counts")
        behind = _count(counts, "behind_pin") if isinstance(counts, dict) else "?"
        rows = doc.body.get("rows")
        retired = (
            sum(1 for r in rows if isinstance(r, dict) and r.get("state") == "retired")
            if isinstance(rows, list)
            else 0
        )
        extra = f"; retired in the catalog: {retired}" if retired else ""
        return f"Behind the pin: {behind}{extra}"
    if error:
        return f"Behind the pin: unknown ({first_line(error)})"
    return "Behind the pin: checking..."


UPDATE_FIX = ["hammunition", "self-update"]


def engine_lag(doc: Document | None) -> str | None:
    """The doctor's own sentence when the venv lags the checkout (#311), else None.

    Found by the fix doctor attaches (argv, #245), not by the check's name."""
    checks = doc.body.get("checks") if doc is not None else None
    if not isinstance(checks, list):
        return None
    for check in checks:
        if (
            isinstance(check, dict)
            and check.get("fix_argv") == UPDATE_FIX
            and check.get("status") != "ok"
        ):
            return _s(check.get("detail"), "the installed engine lags the checkout")
    return None


class ChecksScreen(Screen):
    name = "checks"
    title = "Doctor checks"

    def __init__(self, ctx: Context, checks: Sequence[Mapping[str, Any]]) -> None:
        super().__init__(ctx)
        rows: list[urwid.Widget] = [
            text("The fixes below are text to read; the console never runs one.", "dim"),
            text(""),
        ]
        for check in checks:
            state = _s(check.get("status"))
            attr = {"fail": "fail", "warn": "warn", "ok": "ok"}.get(state)
            rows.append(
                text(f"[{state}] {_s(check.get('name'))}: {check.get('detail') or ''}", attr)
            )
            if check.get("fix"):
                rows.append(text(f"      fix: {check['fix']}", "dim"))
        self._walker[:] = rows


class HomeScreen(Screen):
    name = "home"
    title = "Home"

    def __init__(self, ctx: Context) -> None:
        super().__init__(ctx)
        self.docs: dict[str, Document] = {}
        self.skipped: set[str] = set()
        self.note = ""

    def on_show(self) -> None:
        for key, words in READS.items():
            self._start(key, words)
        self.redraw()

    def _start(self, key: str, words: tuple[str, ...]) -> None:
        self.docs.pop(key, None)
        self.load(key, lambda: self.ctx.engine.read(*words), lambda doc: self._store(key, doc))

    def _store(self, key: str, doc: Document) -> None:
        self.docs[key] = doc
        shared, body = self.ctx.shared, doc.body
        shared.engine_version = doc.engine
        if key == "status":
            shared.target = header_target(
                body.get("target") if isinstance(body.get("target"), dict) else None
            )
        elif key == "doctor":
            fails, warns, healthy = body.get("fails"), body.get("warns"), body.get("healthy")
            if (
                isinstance(fails, int)
                and isinstance(warns, int)
                and isinstance(healthy, int)
                and not isinstance(fails, bool)
                and not isinstance(warns, bool)
                and not isinstance(healthy, bool)
            ):
                shared.doctor = (fails, warns, healthy)
        elif key == "station":
            shared.station_set = (
                body.get("callsign") is not None and body.get("grid_square") is not None
            )
        self.ctx.refresh_header()

    def _walkthrough_rows(self) -> list[urwid.Widget]:
        if self.ctx.config.walkthrough_dismissed:
            return []
        if "station" not in self.docs and "station" not in self.errors:
            return []  # still reading: do not flash a checklist that may be all done
        station = self.docs["station"].body if "station" in self.docs else None
        catalog = self.docs["list"].body if "list" in self.docs else None
        items = steps(station, catalog, self.skipped)
        if not show_checklist(items):
            return []
        rows: list[urwid.Widget] = [
            text(
                "First run: four steps, each optional. Enter opens one, s skips it, D dismisses this list.",
                "key",
            )
        ]
        if self.note:
            rows.append(text(self.note, "warn"))
        for step in items:
            row = Row(f" {MARK[step.state]} {step.number}  {step.label}  - {step.detail}", step)
            urwid.connect_signal(row, "activate", self._open_step)
            rows.append(row)
        rows.append(text(""))
        return rows

    def _open_step(self, row: Row) -> None:
        step = row.value
        if not isinstance(step, Step):
            return
        if step.key == "station":
            self.ctx.open_screen("station")
        elif step.key == "hardware":
            self.ctx.push(
                ConfirmScreen(
                    self.ctx,
                    "Apply the hardware rules",
                    [
                        "This runs: hammunition hardware apply",
                        "",
                        "It prints its own plan and asks for its own typed confirmation (and your sudo password).",
                        "The console cannot show that plan first: the engine has no JSON form of it yet.",
                    ],
                    self._run_hardware,
                )
            )
        elif step.key == "pick":
            self.ctx.open_screen("install", highlight=STARTER)
        elif step.key == "install":
            self.ctx.push(PlanScreen(self.ctx, "install", [STARTER]))

    def _offer_update(self) -> None:
        self.ctx.push(
            ConfirmScreen(
                self.ctx,
                "Update the engine",
                [
                    "This runs: hammunition self-update",
                    "",
                    "It fetches this checkout, fast-forwards it and re-runs bootstrap.sh, "
                    "printing each step first and asking its own confirmation in the pane. "
                    "It never touches apt, installed units or your station.",
                ],
                self._run_update,
            )
        )

    def _run_update(self) -> None:
        self.ctx.run_pane(self.ctx.engine.command("self-update"), "self-update", self._after_update)

    def _after_update(self, code: int | None) -> None:
        self.note = (
            "" if code == 0 else f"self-update exited {code}; its own words were in the pane."
        )
        self.ctx.pop()
        self.on_show()  # re-read: the version, and doctor, have changed

    def _run_hardware(self) -> None:
        self.ctx.run_pane(
            self.ctx.engine.command("hardware", "apply"), "hardware apply", self._after_hardware
        )

    def _after_hardware(self, code: int | None) -> None:
        self.note = (
            ""
            if code == 0
            else f"hardware apply exited {code}; its own words were in the pane. The step stays on the list."
        )
        self.ctx.pop()

    def redraw(self) -> None:
        doc, err = self.docs.get, self.errors.get
        rows: list[urwid.Widget] = [
            text("The engine's own commands, one screen at a time.", "dim"),
            text(""),
        ]
        rows += self._walkthrough_rows()
        doctor = Row(doctor_text(doc("doctor"), err("doctor")), "doctor")
        urwid.connect_signal(doctor, "activate", self._open_checks)
        lag = engine_lag(doc("doctor"))
        if lag:
            rows.append(text(f"Engine: {lag}", "warn"))
            rows.append(text("  Press U to run `hammunition self-update`.", "key"))
        rows += [
            doctor,
            text(station_text(doc("station"), err("station"))),
            text(last_run_text(doc("logs"), err("logs"))),
            text(behind_text(doc("update"), err("update"))),
            text(""),
            text("Where to next (press the number, or Enter):", "dim"),
        ]
        for number, (name, label, blurb) in enumerate(MENU, 1):
            row = Row(f" {number}  {label:<9} {blurb}", name)
            urwid.connect_signal(row, "activate", self._open_row)
            rows.append(row)
        self.set_rows(rows)

    def _open_checks(self, _row: Row) -> None:
        doctor = self.docs.get("doctor")
        checks = doctor.body.get("checks") if doctor else None
        if isinstance(checks, list):
            self.ctx.push(ChecksScreen(self.ctx, [c for c in checks if isinstance(c, dict)]))

    def _open_row(self, row: Row) -> None:
        self.ctx.open_screen(str(row.value))

    def keypress(self, key: str) -> str | None:
        if key in ("1", "2", "3", "4", "5"):
            self.ctx.open_screen(MENU[int(key) - 1][0])
            return None
        if key == "U" and engine_lag(self.docs.get("doctor")):
            self._offer_update()
            return None
        if key == "D":
            self.ctx.config.walkthrough_dismissed = True
            self.ctx.save_config()
            self.redraw()
            return None
        if key == "s":
            step = self.focused_value()
            if isinstance(step, Step):
                self.skipped.add(step.key)
                self.redraw()
                return None
        return key
