# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later
"""The plan (D-016): what the engine will do, section by section as the engine
groups it, hidden when empty, shown before any real command can run."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import urwid

from hammunition.console.context import Context
from hammunition.console.engine import Document
from hammunition.console.fmt import clean, first_line
from hammunition.console.screens.base import Screen, text


@dataclass(frozen=True)
class Section:
    title: str
    lines: tuple[str, ...]


def _s(value: Any) -> str:
    return "" if value is None else clean(value)


def _names(value: Any) -> str:
    return ", ".join(_s(v) for v in value) if isinstance(value, list) else ""


def _dicts(value: Any) -> list[Mapping[str, Any]]:
    return [v for v in value if isinstance(v, dict)] if isinstance(value, list) else []


def blocker_lines(blockers: Sequence[Mapping[str, Any]]) -> list[str]:
    out: list[str] = []
    for b in blockers:
        out.append(f"{_s(b.get('subject'))}: {_s(b.get('reason'))}")
        if b.get("remedy"):
            out.append(f"   remedy: {_s(b['remedy'])}")
    return out


def _steps(commands: Any) -> list[str]:
    out = []
    for c in _dicts(commands):
        out.append(f"$ {_s(c.get('display'))}" + ("  (root)" if c.get("requires_root") else ""))
    return out


def install_sections(view: Mapping[str, Any]) -> list[Section]:
    out: list[Section] = []

    def add(title: str, lines: Sequence[str]) -> None:
        if lines:
            out.append(Section(title, tuple(lines)))

    add(
        "Units, in install order",
        [
            f"{_s(p.get('name'))}  {_s(p.get('method'))}  {_s(p.get('state'))}  (requested by {_names(p.get('requested_by')) or '-'})"
            for p in _dicts(view.get("packages"))
        ],
    )
    add(
        "Distribution packages that stay installed (displaced or shadowed)",
        [
            f"{_s(d.get('package'))}  (declared by {_s(d.get('declared_by'))})"
            for d in _dicts(view.get("displaced"))
        ],
    )
    release = view.get("apt_release")
    if isinstance(release, dict):
        add(
            "apt takes some packages from another release",
            [f"{_s(release.get('release'))}: {_names(release.get('packages'))}"],
        )
    norec = view.get("no_recommends")
    if isinstance(norec, dict):
        add(
            "apt installs these without Recommends",
            [f"units: {_names(norec.get('units'))}", f"packages: {_names(norec.get('packages'))}"],
        )
    repo_lines: list[str] = []
    for r in _dicts(view.get("repos")):
        repo_lines += [
            f"{_s(r.get('name'))} for {_s(r.get('unit'))}: {_s(r.get('uri'))}  suites {_names(r.get('suites'))}",
            f"   key fingerprint {_s(r.get('key_fingerprint'))}",
            f"   writes {_s(r.get('sources'))} and {_s(r.get('keyring'))}",
        ]
    add("Third-party apt repositories (each asks for its own typed confirmation)", repo_lines)
    mirror = view.get("mirror")
    if isinstance(mirror, dict):
        add("LAN mirror", [_s(mirror.get("text"))])
    data_lines: list[str] = []
    for d in _dicts(view.get("data")):
        approx = "about " if d.get("approximate") else ""
        data_lines.append(
            f"{_s(d.get('unit'))}: {approx}{_s(d.get('total_human'))}"
            + (" (approximate: measured when the unit was written)" if d.get("approximate") else "")
            + f", licence {_s(d.get('licence'))}, {_s(d.get('verified_by'))}"
        )
        data_lines += [
            f"   {_s(a.get('size_human'))}  {_s(a.get('url'))}" for a in _dicts(d.get("artifacts"))
        ]
        data_lines.append(f"   installs under {_s(d.get('installs_under'))}")
    add("Offline data downloaded (size and licence)", data_lines)
    maps = view.get("maps")
    if isinstance(maps, dict):
        fetch, current = len(_dicts(maps.get("fetch"))), len(_dicts(maps.get("current")))
        map_lines = [
            f"{fetch} region(s) to download, {current} already current",
            f"download {_s(maps.get('download_total_human'))}, disk {_s(maps.get('disk_total_human'))}",
            f"licence {_s(maps.get('licence'))}",
            _s(maps.get("estimate_note")),
        ]
        terrain = maps.get("terrain")
        if isinstance(terrain, dict):
            map_lines.append(
                f"terrain: download {_s(terrain.get('download_total_human'))}, licence {_s(terrain.get('licence'))}"
            )
            topo = terrain.get("topo")
            if isinstance(topo, dict):
                map_lines.append(
                    f"US Topo: download {_s(topo.get('download_total_human'))}, disk {_s(topo.get('disk_total_human'))}"
                )
                if topo.get("size_consent"):
                    map_lines.append(
                        f"You will be asked to type yes in the pane for this size: {_s(topo['size_consent'])}"
                    )
        add("Map regions (their names are in the CLI's own plan, not shown here)", map_lines)
    add(
        "Group memberships",
        [
            f"{_s(m.get('user'))} is added to group {_s(m.get('group'))} (for {_s(m.get('package'))}): {_s(m.get('detail'))}"
            + (f"  undo: {_s(m['reverse_hint'])}" if m.get("reverse_hint") else "")
            for m in _dicts(view.get("memberships"))
        ],
    )
    add(
        "Configuration files written (station values are filled in by name; the values are not shown)",
        [
            f"{_s(c.get('path'))}  ({_s(c.get('unit'))}, mode {_s(c.get('mode'))})"
            + (f"  fills: {_names(c.get('fills'))}" if c.get("fills") else "")
            for c in _dicts(view.get("config_files"))
        ],
    )
    add(
        "User services written and enabled",
        [
            f"{_s(u.get('name'))}: {_s(u.get('exec'))}  (listens {_s(u.get('listen'))})"
            for u in _dicts(view.get("user_services"))
        ],
    )
    deferral_lines: list[str] = []
    for d in _dicts(view.get("deferrals")):
        deferral_lines.append(
            f"{_s(d.get('kind'))} {_s(d.get('subject'))}: {_s(d.get('what'))} - {_s(d.get('why'))}"
        )
        if d.get("remedy"):
            deferral_lines.append(f"   {_s(d['remedy'])}")
    add("What will NOT happen", deferral_lines)
    add("Notes", [_s(n) for n in view.get("notes") or [] if isinstance(n, str)])
    records = view.get("records")
    if isinstance(records, dict):
        add("Records", [f"transaction log: {_s(records.get('log'))}"])
    gate_lines: list[str] = []
    for g in _dicts(view.get("consent_gates")):
        gate_lines.append(f"{_s(g.get('profile'))}:")
        gate_lines += [f"   {_s(r)}" for r in g.get("risk_lines") or []]
    add("You will be asked to type yes for each of these.", gate_lines)
    sudo = view.get("sudo")
    if isinstance(sudo, dict):
        add("sudo", [_s(sudo.get("text"))])
    add("Steps, exactly as they will run", _steps(view.get("commands")))
    return out


def removal_sections(view: Mapping[str, Any]) -> list[Section]:
    out: list[Section] = []

    def add(title: str, lines: Sequence[str]) -> None:
        if lines:
            out.append(Section(title, tuple(lines)))

    add(
        "apt packages removed",
        [
            f"{_s(u.get('unit'))}: {_names(u.get('packages'))}"
            for u in _dicts(view.get("to_remove"))
        ],
    )
    add(
        "Files and trees removed",
        [
            f"{_s(a.get('unit'))}: {_s(a.get('kind'))} {_s(a.get('path'))}  ({_s(a.get('basis'))})"
            for a in _dicts(view.get("artifacts"))
        ],
    )
    add(
        "Present, but not attributed to this engine: left alone",
        [
            f"{_s(u.get('unit'))}: {_names(u.get('paths'))}"
            for u in _dicts(view.get("left_unattributed"))
        ],
    )
    add(
        "Installed, but not by this engine: left alone",
        [
            f"{_s(u.get('unit'))}: {_names(u.get('packages'))}"
            for u in _dicts(view.get("left_foreign"))
        ],
    )
    add(
        "Nothing to remove",
        [
            f"{_s(u.get('unit'))}: {_names(u.get('packages'))}"
            for u in _dicts(view.get("already_absent"))
        ],
    )
    if view.get("not_reversed"):
        add("What uninstall does not undo, by design", [_s(view["not_reversed"])])
    add("Steps, exactly as they will run", _steps(view.get("commands")))
    return out


class PlanScreen(Screen):
    name = "plan"

    def __init__(self, ctx: Context, action: str, names: Sequence[str]) -> None:
        super().__init__(ctx)
        self.action = action
        self.names = list(names)
        self.title = f"Plan: {action} {' '.join(self.names)}"
        self.doc: Document | None = None
        self.runnable = False

    def on_show(self) -> None:
        # The document is kept across re-shows (a plan can take minutes); `r` is the explicit re-plan.
        if self.status.get("plan") in ("loading", "ok"):
            self.redraw()
            return
        self.replan()

    def replan(self) -> None:
        self.doc, self.runnable = None, False
        # No timeout: `install navigation --dry-run` measured 9 m 49 s on the bench.
        self.load(
            "plan",
            lambda: self.ctx.engine.read(self.action, *self.names, "--dry-run", timeout=None),
            self._store,
        )
        self.redraw()

    def _store(self, doc: Document) -> None:
        self.doc = doc
        self.runnable = doc.kind == "plan" and doc.body.get("outcome") == "planned"

    def redraw(self) -> None:
        rows: list[urwid.Widget] = []
        if self.status.get("plan") == "loading":
            rows.append(text("planning... this can take minutes for map profiles"))
        elif self.status.get("plan") == "error":
            rows += [text(self.errors["plan"], "fail"), text(""), text("Nothing was run.")]
        elif self.doc is not None and not self.runnable:
            rows += [
                text("The engine refused this transaction. Nothing will be run.", "fail"),
                text(""),
            ]
            rows += [text(line) for line in blocker_lines(_dicts(self.doc.body.get("blockers")))]
        elif self.doc is not None:
            rows += [
                text(
                    f"{self.action} {' '.join(self.names)}: planned. Nothing has been changed yet.",
                    "ok",
                ),
                text("R run this in a terminal pane   b back: changes nothing", "key"),
                text("(any consent is typed by you, inside the pane)"),
                text(""),
            ]
            view = (
                self.doc.body.get("install")
                if self.action == "install"
                else self.doc.body.get("removal")
            )
            sections = (
                install_sections(view)
                if self.action == "install" and isinstance(view, dict)
                else (removal_sections(view) if isinstance(view, dict) else [])
            )
            for section in sections:
                rows.append(text(section.title, "key"))
                rows += [text("  " + line) for line in section.lines]
                rows.append(text(""))
            rows.append(text("R run this in a terminal pane   b back: changes nothing", "key"))
        self.set_rows(rows)

    def keypress(self, key: str) -> str | None:
        if key == "R" and self.runnable:
            argv = self.ctx.engine.command(self.action, *self.names)
            self.ctx.run_pane(argv, f"{self.action} {' '.join(self.names)}", self._after_pane)
            return None
        if key == "r":
            self.replan()
            return None
        return key

    def _after_pane(self, code: int | None) -> None:
        self.ctx.replace(ResultScreen(self.ctx, self.action, self.names, code))


class ResultScreen(Screen):
    name = "result"

    def __init__(self, ctx: Context, action: str, names: Sequence[str], code: int | None) -> None:
        super().__init__(ctx)
        self.action, self.names, self.code = action, list(names), code
        self.title = f"{action} finished"
        self._logs: Document | None = None
        self._state: Document | None = None

    def on_show(self) -> None:
        self.load("logs", lambda: self.ctx.engine.read("logs"), lambda d: setattr(self, "_logs", d))
        self.load(
            "status", lambda: self.ctx.engine.read("status"), lambda d: setattr(self, "_state", d)
        )
        self.redraw()

    def _log_line(self) -> str:
        if self._logs is not None:
            runs = _dicts(self._logs.body.get("runs"))
            run = next((r for r in runs if r.get("command") == self.action), None)
            if run is None:
                return "Engine log: no run of this command is listed"
            code = run.get("exit_code")
            tail = f" (exit {code})" if isinstance(code, int) else ""
            return f"Engine log: {_s(run.get('result'))}{tail}  {_s(run.get('path'))}"
        if "logs" in self.errors:
            return f"Engine log: unknown ({first_line(self.errors['logs'])})"
        return "Engine log: reading..."

    def _state_lines(self) -> list[str]:
        if self._state is not None:
            latest = self._state.body.get("latest")
            if not isinstance(latest, dict):
                return ["Latest transaction: none recorded"]
            lines = [f"Latest transaction: {_s(latest.get('outcome'))}"]
            lines += [
                f"Not confirmed: {_s(c.get('subject'))} - {_s(c.get('detail'))}"
                for c in _dicts(latest.get("unconfirmed"))
            ]
            lines += [
                f"Deferred: {_s(d.get('subject'))} - {_s(d.get('why'))}"
                for d in _dicts(latest.get("deferred"))
            ]
            return lines
        if "status" in self.errors:
            return [f"Latest transaction: unknown ({first_line(self.errors['status'])})"]
        return ["Latest transaction: reading..."]

    def redraw(self) -> None:
        code = (
            f"Exit code: {self.code}"
            if self.code is not None
            else "Exit code: unknown (the program was cut off)"
        )
        self.set_rows(
            [
                text(f"{self.action} {' '.join(self.names)}: the program finished."),
                text(code),
                text(self._log_line()),
                *[text(line) for line in self._state_lines()],
                text(""),
                text(
                    "b back to the list (the engine's word above is the result; the console adds none of its own)",
                    "key",
                ),
            ]
        )

    def keypress(self, key: str) -> str | None:
        if key == "b":
            self.ctx.pop(2)
            return None
        return key
