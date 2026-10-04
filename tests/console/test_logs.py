# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later
import os
from pathlib import Path
from typing import Any

from hammunition.console.engine import EngineRefused
from hammunition.console.screens.logs import (
    LogsScreen,
    LogViewScreen,
    is_inside,
    read_from,
    read_tail,
)

from .helpers import FakeContext, FakeEngine, document, load, render


def logs_doc(directory: Path, *runs: dict[str, Any]) -> Any:
    return document(
        "logs",
        {
            "directory": str(directory),
            "total_bytes": 0,
            "max_files": 30,
            "max_bytes": 1,
            "runs": list(runs),
        },
    )


def run_entry(
    path: Path, result: str = "ok", code: int | None = 0, command: str = "install"
) -> dict[str, Any]:
    return {
        "path": str(path),
        "started": "2026-10-03T14:02:11Z",
        "command": command,
        "pid": 1,
        "size": 1,
        "result": result,
        "exit_code": code,
    }


def ctx_for(doc: Any) -> FakeContext:
    engine = FakeEngine()
    engine.set(("logs",), doc)
    return FakeContext(engine=engine)


def test_the_list_shows_every_result_word_newest_first() -> None:
    screen = LogsScreen(FakeContext())
    screen.on_show()
    out = render(screen.widget(), 110, 20)
    runs = load("logs")["runs"]
    assert [r["result"] for r in runs] == [
        "running",
        "ok",
        "failed",
        "refused",
        "not confirmed",
        "incomplete",
    ]
    data = [
        line
        for line in out.splitlines()
        if any(r["command"] in line and r["result"] in line for r in runs)
    ]
    assert len(data) == len(runs) and "running" in data[0] and "incomplete" in data[-1]
    assert "None" not in out


def test_a_null_exit_code_is_a_dash() -> None:
    screen = LogsScreen(FakeContext())
    screen.on_show()
    running = next(ln for ln in render(screen.widget(), 110, 20).splitlines() if "running" in ln)
    assert running.rstrip().endswith("-")


def test_an_empty_log_and_a_failed_read() -> None:
    ctx = ctx_for(logs_doc(Path("/x")))
    screen = LogsScreen(ctx)
    screen.on_show()
    assert "No runs yet" in render(screen.widget(), 100, 10)
    engine = FakeEngine()
    engine.set(("logs",), EngineRefused(2, "no log dir"))
    screen = LogsScreen(FakeContext(engine=engine))
    screen.on_show()
    assert "no log dir" in render(screen.widget(), 100, 10)


def open_first(
    tmp_path: Path, name: str = "a.log", body: str = "line one\nline two\n", result: str = "ok"
) -> tuple[LogsScreen, FakeContext, Path]:
    logdir = tmp_path / "logs"
    logdir.mkdir()
    log = logdir / name
    log.write_text(body)
    ctx = ctx_for(logs_doc(logdir, run_entry(log, result, 0 if result == "ok" else None)))
    screen = LogsScreen(ctx)
    screen.on_show()
    next(r for r in screen._walker if getattr(r, "value", None)).keypress((100,), "enter")
    return screen, ctx, log


def test_enter_opens_the_file_the_engine_listed(tmp_path: Path) -> None:
    _, ctx, _ = open_first(tmp_path)
    view = ctx.pushed[-1]
    assert isinstance(view, LogViewScreen)
    assert (
        "line two" in render(view.widget(), 80, 10) and view.following is False and ctx.timers == []
    )


def test_log_text_is_cleaned_of_control_sequences(tmp_path: Path) -> None:
    _, ctx, _ = open_first(tmp_path, body="ok\x1b[2J\x1b]0;pwned\x07done\n")
    out = render(ctx.pushed[-1].widget(), 80, 10)
    assert "\x1b" not in out and "\x07" not in out and "done" in out


def test_invalid_utf8_in_a_log_is_tolerated(tmp_path: Path) -> None:
    logdir = tmp_path / "l"
    logdir.mkdir()
    log = logdir / "b.log"
    log.write_bytes(b"good\n\xff\xfe bad bytes\nafter\n")
    text, _ = read_tail(str(log))
    assert "good" in text and "after" in text


def test_only_the_last_64k_are_read(tmp_path: Path) -> None:
    log = tmp_path / "big.log"
    log.write_text("".join(f"row {i:06d}\n" for i in range(40000)))
    text, size = read_tail(str(log))
    assert size == log.stat().st_size and "row 039999" in text and "row 000000" not in text
    assert len(text) <= 70000 and text.startswith("row ")  # the partial first line is dropped


def test_refuses_a_path_outside_the_log_directory(tmp_path: Path) -> None:
    logdir = tmp_path / "logs"
    logdir.mkdir()
    outside = tmp_path / "secret.txt"
    outside.write_text("secret")
    (logdir / "link.log").symlink_to(outside)
    (logdir / "real.log").write_text("x")
    assert is_inside(str(logdir / "real.log"), str(logdir))
    assert not is_inside(str(logdir / "link.log"), str(logdir)), "a symlink out of the directory"
    assert not is_inside(str(logdir / ".." / "secret.txt"), str(logdir))
    assert not is_inside(str(outside), str(logdir))
    assert not is_inside(str(logdir), str(logdir)), "the directory itself"
    assert not is_inside(str(logdir / "missing.log"), str(logdir)), (
        "must be an existing regular file"
    )
    assert not is_inside(str(tmp_path / "logs-evil" / "x"), str(logdir)), (
        "a sibling with the same prefix"
    )


def test_the_list_refuses_to_open_a_path_that_escapes(tmp_path: Path) -> None:
    logdir = tmp_path / "logs"
    logdir.mkdir()
    secret = tmp_path / "secret.txt"
    secret.write_text("secret")
    ctx = ctx_for(logs_doc(logdir, run_entry(secret)))
    screen = LogsScreen(ctx)
    screen.on_show()
    next(r for r in screen._walker if getattr(r, "value", None)).keypress((100,), "enter")
    assert ctx.pushed == [] and "not inside the log directory" in screen.note
    assert "not inside the log directory" in render(screen.widget(), 100, 10)


def test_a_running_log_is_followed_and_new_lines_appear(tmp_path: Path) -> None:
    _, ctx, log = open_first(tmp_path, result="running")
    view = ctx.pushed[-1]
    assert view.following and len(ctx.timers) == 1 and ctx.timers[0][0] == 1.0
    with open(log, "a") as handle:
        handle.write("a new line\n")
    ctx.timers.pop()[1]()
    assert "a new line" in render(view.widget(), 80, 10) and len(ctx.timers) == 1


def test_leaving_the_view_stops_the_following(tmp_path: Path) -> None:
    _, ctx, _ = open_first(tmp_path, result="running")
    view = ctx.pushed[-1]
    view.on_hide()
    ctx.timers.pop()[1]()
    assert ctx.timers == [] and view.following is False


def test_a_log_deleted_by_rotation_while_open_is_a_calm_note_not_a_traceback(
    tmp_path: Path,
) -> None:
    _, ctx, log = open_first(tmp_path, result="running")
    view = ctx.pushed[-1]
    log.unlink()
    ctx.timers.pop()[1]()
    assert "rotated away" in view.note and ctx.timers == [] and view.following is False
    assert "rotated away" in render(view.widget(), 80, 10)


def test_a_truncated_log_is_reread(tmp_path: Path) -> None:
    _, ctx, log = open_first(tmp_path, body="old old old old old old old\n" * 20, result="running")
    view = ctx.pushed[-1]
    log.write_text("fresh\n")
    ctx.timers.pop()[1]()
    assert "truncated" in view.note and "fresh" in render(view.widget(), 80, 10)


def test_read_from_returns_only_new_text_and_none_when_gone(tmp_path: Path) -> None:
    log = tmp_path / "x.log"
    log.write_text("abc\n")
    text, offset = read_from(str(log), 0) or ("", 0)
    assert text == "abc\n" and offset == 4
    assert read_from(str(log), 4) == ("", 4)
    log.unlink()
    assert read_from(str(log), 4) is None


def test_a_view_never_holds_more_than_the_line_cap(tmp_path: Path) -> None:
    _, ctx, log = open_first(tmp_path, result="running")
    view = ctx.pushed[-1]
    with open(log, "a") as handle:
        handle.write("".join(f"l{i}\n" for i in range(6000)))
    ctx.timers.pop()[1]()
    assert len(view.lines) <= 5000 and view.lines[-1] == "l5999"


def test_read_from_is_bounded_and_skips_a_large_gap(tmp_path: Path) -> None:
    log = tmp_path / "g.log"
    log.write_text("".join(f"row {i:05d}\n" for i in range(5000)))
    text, offset = read_from(str(log), 0, max_bytes=1000) or ("", 0)
    assert (
        offset == log.stat().st_size
        and len(text) <= 1000
        and "row 04999" in text
        and "row 00000" not in text
    )
    assert text.startswith("row ")


def test_a_log_that_outgrows_the_cap_between_ticks_notes_the_gap(tmp_path: Path) -> None:
    _, ctx, log = open_first(tmp_path, result="running")
    view = ctx.pushed[-1]
    with open(log, "a") as handle:
        handle.write("".join(f"g{i:06d}\n" for i in range(20000)))
    ctx.timers.pop()[1]()
    assert "Skipped" in view.note and view.lines[-1] == "g019999" and view.following


def test_rotation_between_the_read_and_the_size_check_is_calm(
    tmp_path: Path, monkeypatch: Any
) -> None:
    _, ctx, _ = open_first(tmp_path, result="running")
    view = ctx.pushed[-1]

    def gone(_path: str) -> int:
        raise FileNotFoundError(_path)

    monkeypatch.setattr(os.path, "getsize", gone)
    ctx.timers.pop()[1]()
    assert "rotated away" in view.note and view.following is False and ctx.timers == []
