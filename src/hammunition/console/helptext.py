# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later
"""Text the console shows and prints. Keep the literal consent tokens out of here:
tests/test_consent_guard.py fails if one appears anywhere in the package but guard.py."""

from __future__ import annotations

import textwrap

USAGE = """\
usage: hammunition console [--help] [--version]

A full-screen terminal front end for the Hammunition engine. It reads the
engine's JSON documents and runs the engine's own commands in a terminal pane;
it never answers a consent prompt for you. Needs a terminal at least 80x24."""

# (keys, meaning). Every key listed here is handled somewhere; the README's
# keys table is generated from this tuple's content by hand and a test checks it.
KEYS: tuple[tuple[str, str], ...] = (
    ("1-7", "open the screen with that number (Home)"),
    ("Enter", "open the selected row"),
    ("b / Esc", "go back; changes nothing (in a text prompt only Esc: b is typed)"),
    ("?", "help"),
    ("q", "quit"),
    ("r", "refresh this screen"),
    ("R", "run the planned command in a terminal pane (plan and confirm screens)"),
    ("Tab", "switch between profiles and single units (Install)"),
    ("U", "plan an uninstall of the selected profile (Install)"),
    ("i", "the selected profile's documentation (Install)"),
    ("v", "reveal or hide station values (Station)"),
    ("c", "clear the selected value, where the engine can (Station)"),
    ("g", "where to get the selected secret (Secrets)"),
    ("d", "name a Doppler project and config for the selected secret (Secrets)"),
    ("e", "enter the selected secret for this session only, hidden (Secrets)"),
    ("x", "forget the session value of the selected secret (Secrets)"),
    ("f", "run the command the selected secret unlocks (Secrets)"),
    ("f", "fetch RepeaterBook by state (Repeaters)"),
    ("i", "import your own repeater export (Repeaters)"),
    ("a", "choose the active areas (Repeaters)"),
    ("x", "remove the selected layer (Repeaters)"),
    ("l", "look repeaters up near a place, by band and mode (Repeaters)"),
    ("u", "also ask upstream whether the catalog's pins are current (Update)"),
    ("A", "run the apt upgrade the report offers (Update)"),
    ("B", "plan the rebuilds the report offers (Update)"),
    ("s", "skip the selected first-run step (Home)"),
    ("D", "dismiss the first-run checklist (Home)"),
)

EXIT_CODES = (
    ("0", "normal exit"),
    ("1", "the console crashed (details, without any message text, in crash.log)"),
    ("2", "the console refused to start: no terminal, TERM=dumb, running as root, bad argument"),
)


def full_help() -> str:
    lines = [USAGE, "", "Keys:"]
    lines += [f"  {keys:<10} {meaning}" for keys, meaning in KEYS]
    lines += ["", "Exit codes:"]
    lines += [f"  {code:<10} {meaning}" for code, meaning in EXIT_CODES]
    return "\n".join(lines)


_RAW_HELP: dict[str, tuple[str, ...]] = {
    "home": (
        "Home shows what needs attention: the engine's own health check, whether your station is set, the last run and "
        "how many units are behind the catalog's pin. Enter on the health line lists each check and the engine's "
        "suggested fix; the console shows a fix and never runs one.",
    ),
    "install": (
        "Install lists the engine's profiles (a profile is a named bundle) and, with Tab, its single units. Enter opens "
        "the plan: everything the engine will do, before anything runs. G marks a profile that asks you to type yes first.",
        "A name you type in the box is handed to the engine as it is; the engine decides whether it exists.",
    ),
    "plan": (
        "The plan is the engine's own dry run. Nothing has changed while you read it. R runs the real command in a "
        "terminal pane, where sudo, the group choice and any typed yes are the engine's, answered by you. b goes back "
        "and changes nothing.",
    ),
    "station": (
        "Station shows the values the engine saved. Callsign, grid square, alias, regions and the rig port stay hidden "
        "until you press v. Enter changes one by running the engine's own station set command; the console keeps no "
        "copy and writes the value nowhere itself.",
    ),
    "secrets": (
        "Secrets lists the keys the engine can use for downloads that need one, and where each would come from: "
        "the environment, Doppler, or nowhere yet. It never shows a value. g says where to get one; d names a "
        "Doppler project and config (names only) through the engine's station set; e keeps a value in this console's "
        "memory for the engine commands it starts, writes it nowhere and forgets it when you quit.",
    ),
    "repeaters": (
        "Repeaters shows the repeater layers on this machine grouped by area, which areas are active, and the "
        "engine's credit for each source. f fetches RepeaterBook by state (it needs your own token: Secrets opens "
        "first when none answers, and the repeaterbook-client unit is offered when it is missing); i imports your "
        "own export from a file; a chooses the active areas, which deletes nothing; x removes the selected layer; "
        "l looks repeaters up near a place by distance, band and mode. Each is the engine's own command, shown "
        "before it runs.",
    ),
    "lookup": (
        "The lookup lists the repeaters the layers on this machine hold, nearest first when a position is known. "
        "RepeaterBook rows are for your own use on this machine; the credit below the table is the engine's.",
    ),
    "logs": (
        "Logs lists every run the engine recorded, newest first, with its result in the engine's own words. Enter opens "
        "the file; a run that is still going is followed live.",
    ),
    "update": (
        "Update compares what is installed with the catalog. Nothing is fetched unless you press u, which also asks "
        "GitHub, git hosts and PyPI whether the catalog's pins are current. A runs the apt upgrade it offers (apt asks "
        "you first); B plans the rebuilds it offers.",
    ),
    "help": (
        "Help is this screen. Enter on a profile shows what it is for and what you still set up by hand.",
    ),
}

# Wrapped here so each line fits the narrowest terminal the console supports.
SCREEN_HELP: dict[str, tuple[str, ...]] = {
    name: tuple(line for para in paras for line in textwrap.wrap(para, 76))
    for name, paras in _RAW_HELP.items()
}

NEVER: tuple[str, ...] = (
    "It never answers a consent prompt for you: you type yes into the engine's own prompt, in the pane.",
    "It never runs anything but the engine's own commands (and the apt upgrade the engine's update report offers).",
    "It never writes a secret anywhere: one you enter lives in its memory for the engine commands it starts and is cleared when you quit.",
    "It never stores your callsign, grid square or any station value; the engine's station file is the only copy.",
    "It never fetches anything from the network itself; the engine does, and it asks GitHub, git hosts and PyPI only when you press u on Update.",
)
