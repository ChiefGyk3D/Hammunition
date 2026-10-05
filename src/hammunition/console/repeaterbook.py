# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later
"""The RepeaterBook fetch as the console runs it (issue #344, D-081): one function the
Secrets screen and the Repeaters screen both call.

The fetch needs the `repeaterbook-client` unit. When it is not installed the console offers
the install first, through the Install screen's own plan (the engine's dry run, then `R` in a
pane), and runs the fetch after the install succeeds; declining, backing out or a failed
install runs nothing further. The installed state is read from `update repeaterbook-client
--json`, which compares the machine: `list --json` carries no per-unit installed state."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence

from hammunition.console.context import Context
from hammunition.console.engine import Document
from hammunition.console.screens.base import FATAL, ConfirmScreen
from hammunition.console.screens.plan import PlanScreen

UNIT = "repeaterbook-client"
FETCH_VERB = ("maps", "repeaters", "fetch-repeaterbook")
NOT_INSTALLED = "not installed"


def is_fetch(words: Sequence[str]) -> bool:
    return tuple(words[:3]) == FETCH_VERB


def unit_installed(doc: Document) -> bool | None:
    """True or False from the engine's row for the unit; None when it has no row for it."""
    rows = doc.body.get("rows")
    if not isinstance(rows, list):
        return None
    for row in rows:
        if isinstance(row, Mapping) and row.get("unit") == UNIT:
            return row.get("state") != NOT_INSTALLED
    return None


def run_fetch(ctx: Context, words: Sequence[str], on_exit: Callable[[int | None], None]) -> None:
    """Check the unit, then confirm and run the fetch `words` in a pane (installing the unit
    first when it is absent and the operator accepts). `on_exit` gets the fetch's exit code."""

    def finished(result: Document | None, error: BaseException | None) -> None:
        if error is not None and isinstance(error, FATAL):
            ctx.fatal(error)
            return
        installed = None if error is not None or result is None else unit_installed(result)
        if installed is False:
            _offer_install(ctx, words, on_exit)
        else:
            _confirm_fetch(ctx, words, on_exit, checked=installed is True)

    ctx.bg.submit(lambda: ctx.engine.read("update", UNIT), finished)


def _confirm_fetch(
    ctx: Context,
    words: Sequence[str],
    on_exit: Callable[[int | None], None],
    *,
    checked: bool = True,
) -> None:
    argv = ctx.engine.command(*words)
    lines = [
        "This runs the engine's own command; it prints RepeaterBook's terms and asks nothing the console answers:",
        "",
        "  " + " ".join(argv),
    ]
    if not checked:
        lines += [
            "",
            f"The console could not tell whether the {UNIT} unit is installed; the engine says so if it is not.",
        ]
    ctx.push(
        ConfirmScreen(
            ctx,
            "Run: " + " ".join(words[:3]),
            lines,
            lambda: ctx.run_pane(argv, " ".join(words[:3]), on_exit),
        )
    )


def _offer_install(
    ctx: Context, words: Sequence[str], on_exit: Callable[[int | None], None]
) -> None:
    fetch = " ".join(ctx.engine.command(*words))
    install = " ".join(ctx.engine.command("install", UNIT))

    def plan_it() -> None:
        ctx.push(
            PlanScreen(
                ctx,
                "install",
                [UNIT],
                after_success=lambda: ctx.run_pane(
                    ctx.engine.command(*words), " ".join(words[:3]), on_exit
                ),
            )
        )

    ctx.push(
        ConfirmScreen(
            ctx,
            f"Install {UNIT} first",
            [
                f"The RepeaterBook fetch needs the {UNIT} unit, and it is not installed.",
                "It is the unofficial third-party client, registered with RepeaterBook as App #114.",
                "",
                "R shows the engine's plan for the install (nothing changes yet); you run it there.",
                "When the install succeeds, this command runs in a pane straight after:",
                "",
                "  " + fetch,
                "",
                "The plan comes from: " + install,
                "Back (b) here, or on the plan, runs nothing.",
            ],
            plan_it,
        )
    )
