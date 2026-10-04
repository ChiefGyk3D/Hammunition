# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later
"""The engine's own menu entry for `hammunition console` (#302, D-050).

The console is not a catalog unit any more: it is a subcommand of the engine, so no
manifest generates its entry. The menu writes it itself, beside the device entries,
running the engine by its absolute path (a menu entry's PATH has no ~/.local/bin,
issue #145).
"""

from pathlib import Path

from hammunition.menus import ENGINE_ENTRY_ID, engine_entry_steps, render_engine_entry

ENGINE = Path("/home/someone/.local/bin/hammunition")


def test_the_entry_runs_the_console_subcommand_in_a_terminal_by_absolute_path() -> None:
    text = render_engine_entry(engine=ENGINE)
    assert f"Exec={ENGINE} console\n" in text
    assert "Terminal=true\n" in text and "Type=Application\n" in text
    assert "Name=Install and manage the station from a terminal (hammunition console)\n" in text
    assert "X-Hammunition-Generated=engine\n" in text


def test_it_sits_where_the_desktop_keeps_workstation_tools() -> None:
    """`workstation` is a `menu: false` group: no Hammunition submenu, the desktop's HamRadio."""
    assert "Categories=HamRadio;X-Hammunition-workstation;\n" in render_engine_entry(engine=ENGINE)


def test_the_step_writes_the_entry_and_a_second_run_changes_nothing(tmp_path: Path) -> None:
    (step,) = engine_entry_steps(tmp_path, engine=ENGINE)
    assert "hammunition console" in step.description
    step.perform()
    first = (tmp_path / ENGINE_ENTRY_ID).read_text()
    (again,) = engine_entry_steps(tmp_path, engine=ENGINE)
    again.perform()
    assert (tmp_path / ENGINE_ENTRY_ID).read_text() == first


def test_the_entry_id_is_in_neither_family_another_prune_owns() -> None:
    assert not ENGINE_ENTRY_ID.startswith(("hammunition-cli-", "hammunition-device-"))
