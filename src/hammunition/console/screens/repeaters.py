# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later
"""The Repeaters screen (issue #322; D-064, D-074, D-081, D-082): the repeater layers on
this machine grouped by area, the areas, and the engine's own commands to fetch RepeaterBook
by state, import an export, choose the active areas, remove a layer, and look repeaters up.

Reads only `maps repeaters list --json` and `maps areas --json` (D-059). Every change is the
real command, shown first and run in a pane. A RepeaterBook row is the operator's own
personal-use data: the credit the engine prints is shown exactly as the document gives it."""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

import urwid

from hammunition.console import repeaterbook
from hammunition.console.context import Context
from hammunition.console.engine import Document
from hammunition.console.fmt import clean, human_size
from hammunition.console.screens.base import (
    FATAL,
    ConfirmScreen,
    PromptScreen,
    Row,
    Screen,
    describe_error,
    text,
)

SECRET = "REPEATERBOOK"
STATE = re.compile(r"^[A-Za-z]{2}(?:[0-9]{2})?$")  # `OH`, or RepeaterBook's `CA01` outside the US
COUNTY = re.compile(r"^[A-Za-z][A-Za-z .'-]{0,39}$")
AREA = re.compile(r"^[A-Za-z0-9][A-Za-z0-9/._-]{0,63}$")
GRID = re.compile(r"^[A-Ra-r]{2}[0-9]{2}(?:[A-Xa-x]{2}(?:[0-9]{2})?)?$")
LATLON = re.compile(r"^-?[0-9]{1,3}(?:\.[0-9]+)?,-?[0-9]{1,3}(?:\.[0-9]+)?$")
NUMBER = re.compile(r"^[0-9]+(?:\.[0-9]+)?$")
MODE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9-]{0,11}$")
BANDS = ("10m", "6m", "2m", "1.25m", "70cm", "33cm", "23cm", "13cm", "other")
LAYER_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


def _s(value: object, default: str = "?") -> str:
    return default if value is None else str(value)


def _dicts(value: object) -> list[Mapping[str, Any]]:
    return [v for v in value if isinstance(v, dict)] if isinstance(value, list) else []


def _num(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _split(raw: str) -> list[str]:
    return [t for t in re.split(r"[,\s]+", raw.strip()) if t]


def mhz(hz: object) -> str:
    n = _num(hz)
    return "?" if n is None or n <= 0 else f"{n / 1e6:.4f}"


def offset_text(hz: object) -> str:
    n = _num(hz)
    if n is None:
        return "?"
    return "0" if n == 0 else f"{n / 1e6:+.1f}"


def table_header() -> str:
    return f"{'Callsign':<10} {'Output':<9} {'Offset':>6} {'Tone':<6} {'Mode':<12} {'Dist':>8} {'Brg':>4}  Place"


def table_line(row: Mapping[str, Any]) -> str:
    dist, brg = _num(row.get("distance_km")), _num(row.get("bearing_deg"))
    return (
        f"{clean(_s(row.get('callsign'), '')) or '-':<10} {mhz(row.get('output_hz')):<9} "
        f"{offset_text(row.get('offset_hz')):>6} {clean(_s(row.get('tone'), '')) or '-':<6} "
        f"{clean(_s(row.get('mode'), '')) or '-':<12} "
        f"{('-' if dist is None else f'{dist:.1f} km'):>8} "
        f"{('-' if brg is None else f'{brg:.0f}'):>4}  {clean(_s(row.get('place'), ''))}"
    )


def layer_line(layer: Mapping[str, Any]) -> str:
    mark = "[x]" if layer.get("active") else "[ ]"
    marks = ""
    if layer.get("personal_use"):
        marks += "  personal use"
    if layer.get("unverified"):
        marks += "  unverified"
    return (
        f" {mark} {_s(layer.get('id')):<18} {_s(layer.get('rows')):>5} rows  "
        f"{_s(layer.get('day'))}{marks}"
    )


def area_line(area: Mapping[str, Any]) -> str:
    size = area.get("size_bytes")
    layers = area.get("layers")
    return (
        f" {_s(area.get('area')):<26} {_s(area.get('kind')):<7}"
        f"{'active' if area.get('active') else 'not active':<11}"
        f"{len(layers) if isinstance(layers, list) else 0} layers  "
        f"{human_size(size) if isinstance(size, int) and not isinstance(size, bool) else '?'}  "
        f"{_s(area.get('day'), 'no date')}"
    )


class RepeatersScreen(Screen):
    name = "repeaters"
    title = "Repeaters"

    def __init__(self, ctx: Context) -> None:
        super().__init__(ctx)
        self.note = ""
        self._layers: Document | None = None
        self._areas: Document | None = None

    def on_show(self) -> None:
        self.load(
            "layers", lambda: self.ctx.engine.read("maps", "repeaters", "list"), self._store_layers
        )
        self.load("areas", lambda: self.ctx.engine.read("maps", "areas"), self._store_areas)
        self.redraw()

    def _store_layers(self, doc: Document) -> None:
        self._layers = doc

    def _store_areas(self, doc: Document) -> None:
        self._areas = doc

    # -- drawing -----------------------------------------------------------
    def redraw(self) -> None:
        rows: list[urwid.Widget] = [
            text(
                "f fetch RepeaterBook by state   i import your own export   a choose active areas   "
                "x remove the selected layer   l look repeaters up",
                "dim",
            ),
            text(
                "Each is the engine's own command, shown before it runs. Nothing is deleted silently; "
                "choosing areas deletes nothing.",
                "dim",
            ),
        ]
        if self.note:
            rows.append(text(self.note, "warn"))
        rows.append(text(""))
        rows += self._area_rows()
        rows += self._layer_rows()
        self.set_rows(rows)

    def _error_or_loading(self, key: str, what: str) -> list[urwid.Widget] | None:
        if self.status.get(key) == "error":
            return [text(self.errors[key], "fail")]
        if (self._areas if key == "areas" else self._layers) is None:
            return [text(f"Reading the {what}...")]
        return None

    def _area_rows(self) -> list[urwid.Widget]:
        out: list[urwid.Widget] = [text("Areas", "key")]
        problem = self._error_or_loading("areas", "areas")
        if problem is not None:
            return [*out, *problem, text("")]
        body = self._areas.body if self._areas else {}
        active = body.get("active_areas")
        if isinstance(active, list):
            out.append(
                text(
                    "Active: "
                    + (", ".join(_s(a) for a in active) or "none (layers with no area stay)")
                )
            )
        else:
            out.append(text("Active: everything loaded (no areas chosen yet)"))
        unloaded = body.get("unloaded")
        if isinstance(unloaded, list) and unloaded:
            out.append(text("Named but not loaded: " + ", ".join(_s(a) for a in unloaded), "dim"))
        areas = _dicts(body.get("areas"))
        out += [text(area_line(a), None if a.get("active") else "dim") for a in areas]
        if not areas:
            out.append(text(" none loaded yet", "dim"))
        return [*out, text("")]

    def _layer_rows(self) -> list[urwid.Widget]:
        out: list[urwid.Widget] = [text("Layers (grouped by area; [x] is active)", "key")]
        problem = self._error_or_loading("layers", "layers")
        if problem is not None:
            return [*out, *problem]
        body = self._layers.body if self._layers else {}
        layers = _dicts(body.get("layers"))
        if not layers:
            out.append(
                text(
                    "No repeater layers yet. Press f to fetch RepeaterBook by state, or i to import your own export."
                )
            )
        groups: dict[str, list[Mapping[str, Any]]] = {}
        for layer in layers:
            area = layer.get("area")
            groups.setdefault(area if isinstance(area, str) else "", []).append(layer)
        for area in sorted(groups, key=lambda a: a == ""):  # the engine's order; no-area last
            out.append(text(f"{area}" if area else "No area (always active)", "dim"))
            for layer in groups[area]:
                row = Row(
                    layer_line(layer), ("layer", layer), attr=None if layer.get("active") else "dim"
                )
                out.append(row)
        for skip in _dicts(body.get("skipped")):
            out.append(text(f" left out {_s(skip.get('layer'))}: {_s(skip.get('reason'))}", "warn"))
        credits = body.get("credits")
        if isinstance(credits, list) and credits:
            out.append(text(""))
            out += [text(_s(c), "dim") for c in credits]
        return out

    # -- keys --------------------------------------------------------------
    def keypress(self, key: str) -> str | None:
        if key == "f":
            self._start_fetch()
        elif key == "i":
            self.ctx.push(
                PromptScreen(
                    self.ctx,
                    "Import your repeater export",
                    "Path to the file: ",
                    self._got_import,
                    note="RepeaterBook GPX or CSV, hearham JSON or a hand CSV, read offline from your own disk.",
                )
            )
        elif key == "a":
            self._start_activate()
        elif key == "x":
            self._start_remove()
        elif key == "l":
            self._start_lookup()
        else:
            return key
        return None

    def _say(self, note: str) -> None:
        self.note = note
        self.redraw()

    # -- running a command -------------------------------------------------
    def _confirm(self, words: Sequence[str], title: str, lines: Sequence[str], done: str) -> None:
        argv = self.ctx.engine.command(*words)
        self.ctx.push(
            ConfirmScreen(
                self.ctx,
                title,
                [*lines, "", "  " + " ".join(argv)],
                lambda: self.ctx.run_pane(argv, " ".join(words[:3]), self._after(done)),
            )
        )

    def _after(self, done: str) -> Callable[[int | None], None]:
        def after(code: int | None) -> None:
            self.note = (
                done
                if code == 0
                else f"The engine run ended with exit {code}; its words were in the pane."
            )
            self.ctx.pop()
            self.on_show()

        return after

    # -- fetch -------------------------------------------------------------
    def _start_fetch(self) -> None:
        def finished(doc: Document | None, error: BaseException | None) -> None:
            if error is not None and isinstance(error, FATAL):
                self.ctx.fatal(error)
                return
            if error is not None or doc is None:
                self._say(
                    f"Could not read where {SECRET} comes from: "
                    f"{describe_error(error) if error else 'no answer'}. Nothing was run."
                )
                return
            row = next(
                (s for s in _dicts(doc.body.get("secrets")) if s.get("name") == SECRET), None
            )
            if SECRET in self.ctx.session.names() or (row is not None and row.get("available")):
                self._ask_states()
                return
            why = (
                f"The RepeaterBook fetch needs {SECRET}, and nothing supplies it yet: "
                "enter it for this session (e) or name a Doppler project (d), then come back and press f."
            )
            self.note = "Nothing was run. " + why
            self.ctx.open_screen("secrets", note=why)

        self.ctx.bg.submit(lambda: self.ctx.engine.read("secrets", "status"), finished)

    def _ask_states(self) -> None:
        self.ctx.push(
            PromptScreen(
                self.ctx,
                "Fetch RepeaterBook",
                "State codes (e.g. OH MI): ",
                self._got_states,
                note="One or more, space or comma separated: a US state code, or RepeaterBook's own id such as CA01.",
            )
        )

    def _got_states(self, raw: str) -> None:
        states = _split(raw)
        if not states:
            return
        if not all(STATE.match(s) for s in states):
            self._say(
                "A state is two letters (OH), or RepeaterBook's id such as CA01. Nothing was run."
            )
            return
        states = [s.upper() for s in states]
        if len(states) == 1:
            self.ctx.push(
                PromptScreen(
                    self.ctx,
                    "Fetch RepeaterBook: county",
                    "County (blank: the whole state): ",
                    lambda county: self._got_county(states[0], county),
                    note=f"State {states[0]}. Several counties, separated by commas, are one request each.",
                )
            )
            return
        self._run_fetch(states, [])

    def _got_county(self, state: str, raw: str) -> None:
        counties = [c.strip() for c in raw.split(",") if c.strip()]
        if not all(COUNTY.match(c) for c in counties):
            self._say("A county name is letters, spaces, '.', ''' or '-'. Nothing was run.")
            return
        self._run_fetch([state], counties)

    def _run_fetch(self, states: Sequence[str], counties: Sequence[str]) -> None:
        words = list(repeaterbook.FETCH_VERB)
        for state in states:
            words += ["--state", state]
        for county in counties:
            words += ["--county", county]
        repeaterbook.run_fetch(self.ctx, words, self._after("The RepeaterBook fetch finished."))

    # -- import ------------------------------------------------------------
    def _got_import(self, raw: str) -> None:
        if not raw:
            return
        if raw.startswith("-") or any(ord(c) < 32 for c in raw):
            self._say("A path does not start with '-'. Nothing was run.")
            return
        path = Path(raw).expanduser()
        if not path.is_file():
            self._say(f"{clean(raw)} is not a file. Nothing was run.")
            return
        self._confirm(
            ["maps", "repeaters", "import", str(path)],
            "Import a repeater export",
            [
                "This runs the engine's own command. It reads the file offline, writes a layer into your",
                "overlay directory and tells QMapShack and Navit about it; it fetches nothing:",
            ],
            "The import finished.",
        )

    # -- activate ----------------------------------------------------------
    def _start_activate(self) -> None:
        active = self._areas.body.get("active_areas") if self._areas else None
        initial = " ".join(_s(a) for a in active) if isinstance(active, list) else "all"
        if isinstance(active, list) and not active:
            initial = "none"
        self.ctx.push(
            PromptScreen(
                self.ctx,
                "Choose the active areas",
                "Areas: ",
                self._got_areas,
                note="State codes (OH) or region names, space separated; `all` or `none`. Nothing is deleted.",
                initial=initial,
            )
        )

    def _got_areas(self, raw: str) -> None:
        tokens = _split(raw)
        if not tokens:
            return
        lowered = [t.lower() for t in tokens]
        if any(t in ("all", "none") for t in lowered):
            if len(tokens) != 1:
                self._say("`all` and `none` stand alone. Nothing was run.")
                return
            words = ["maps", "activate", f"--{lowered[0]}"]
        elif all(AREA.match(t) for t in tokens):
            words = ["maps", "activate", *tokens]
        else:
            self._say("An area is a state code (OH) or a region name. Nothing was run.")
            return
        self._confirm(
            words,
            "Choose the active areas",
            [
                "This runs the engine's own command. It writes the station's active areas and re-registers",
                "QMapShack, Navit and the browser map's list; it deletes no layer and no map:",
            ],
            "The active areas were set.",
        )

    # -- remove ------------------------------------------------------------
    def _start_remove(self) -> None:
        value = self.focused_value()
        layer = value[1] if isinstance(value, tuple) and value[0] == "layer" else None
        layer_id = layer.get("id") if isinstance(layer, dict) else None
        if not isinstance(layer_id, str) or not LAYER_ID.match(layer_id):
            self._say("Select a layer first (arrow keys), then press x. Nothing was run.")
            return
        self._confirm(
            ["maps", "repeaters", "remove", "--layer", layer_id],
            f"Remove layer {layer_id}",
            [
                f"This deletes the layer {layer_id}'s files from your overlay directory, rebuilds the",
                "all-sources file and rewrites your Navit copy. The engine asks nothing more, so this is the",
                "confirmation. Other layers and any file of yours in that directory stay:",
            ],
            f"Layer {layer_id} was removed.",
        )

    # -- lookup ------------------------------------------------------------
    def _start_lookup(self) -> None:
        self.ctx.push(
            PromptScreen(
                self.ctx,
                "Look up repeaters",
                "Near (blank: your station): ",
                self._got_near,
                note="A grid square (FN31pr) or LAT,LON in decimal degrees. Blank uses the station's grid square, if set.",
            )
        )

    def _got_near(self, near: str) -> None:
        if near and not (GRID.match(near) or LATLON.match(near)):
            self._say(
                "Near is a grid square (FN31pr) or LAT,LON such as 41.7,-72.7. Nothing was run."
            )
            return
        self.ctx.push(
            PromptScreen(
                self.ctx,
                "Look up repeaters: distance",
                "Within km (blank: any): ",
                lambda within: self._got_within(near, within),
                note="Only repeaters this far or nearer. Needs a position.",
            )
        )

    def _got_within(self, near: str, within: str) -> None:
        if within and not (NUMBER.match(within) and float(within) > 0):
            self._say("Within is a number of kilometres above zero. Nothing was run.")
            return
        self.ctx.push(
            PromptScreen(
                self.ctx,
                "Look up repeaters: band",
                "Band (blank: any): ",
                lambda band: self._got_band(near, within, band),
                note="One or more of " + ", ".join(BANDS) + ", space or comma separated.",
            )
        )

    def _got_band(self, near: str, within: str, raw: str) -> None:
        bands = [b.lower() for b in _split(raw)]
        if not all(b in BANDS for b in bands):
            self._say("A band is one of " + ", ".join(BANDS) + ". Nothing was run.")
            return
        self.ctx.push(
            PromptScreen(
                self.ctx,
                "Look up repeaters: mode",
                "Mode (blank: any): ",
                lambda mode: self._got_mode(near, within, bands, mode),
                note="FM, DMR, D-STAR, YSF, P25, NXDN, M17, TETRA or ATV; several match any.",
            )
        )

    def _got_mode(self, near: str, within: str, bands: Sequence[str], raw: str) -> None:
        modes = _split(raw)
        if not all(MODE.match(m) for m in modes):
            self._say("A mode is a short name such as FM or DMR. Nothing was run.")
            return
        words = ["maps", "repeaters", "list"]
        if near:
            words += ["--near", near]
        if within:
            words += ["--within", within]
        for band in bands:
            words += ["--band", band]
        for mode in modes:
            words += ["--mode", mode]
        self.ctx.push(LookupScreen(self.ctx, words))


class LookupScreen(Screen):
    """The repeaters one `maps repeaters list` lookup returns, nearest first, as a table."""

    name = "lookup"

    def __init__(self, ctx: Context, words: Sequence[str]) -> None:
        super().__init__(ctx)
        self.words = list(words)
        self.title = "Repeater lookup"
        self._doc: Document | None = None

    def on_show(self) -> None:
        self.load("lookup", lambda: self.ctx.engine.read(*self.words), self._store)
        self.redraw()

    def _store(self, doc: Document) -> None:
        self._doc = doc

    def redraw(self) -> None:
        asked = " ".join(self.ctx.engine.command(*self.words))
        rows: list[urwid.Widget] = [
            text("Read-only, from the layers on this machine: " + asked, "dim")
        ]
        if self.status.get("lookup") == "error":
            rows.append(text(self.errors["lookup"], "fail"))
        elif self._doc is None:
            rows.append(text("Reading..."))
        else:
            body = self._doc.body
            rows += self._table(body)
        self.set_rows(rows)

    def _table(self, body: Mapping[str, Any]) -> list[urwid.Widget]:
        centre = body.get("centre")
        if isinstance(centre, dict):
            if centre.get("source") == "station":
                where = "your station's grid square"  # the console never prints a station value
            else:
                where = f"{_s(centre.get('lat'))}, {_s(centre.get('lon'))}"
            within = _num(body.get("within_km"))
            head = f"Nearest first from {where}" + (f", within {within:g} km" if within else "")
        else:
            head = "No position given, so no distances"
        rows_in = _dicts(body.get("rows"))
        out: list[urwid.Widget] = [text(head), text(""), text(table_header(), "key")]
        out += [text(table_line(r)) for r in rows_in]
        if not rows_in:
            out.append(text("  none match"))
        out.append(text(""))
        out.append(
            text(f"{len(rows_in)} repeaters ({_s(body.get('merged'), '0')} merged across sources)")
        )
        credits = body.get("credits")
        if isinstance(credits, list):
            out += [text(""), *[text(_s(c), "dim") for c in credits]]
        return out
