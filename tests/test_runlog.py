# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""A readable log of every run that changes state or runs long.  D-077."""

from __future__ import annotations

import importlib
import json
import os
import re
import sys
from pathlib import Path

import pytest

from hammunition import runlog
from hammunition.backends import Command, SubprocessRunner
from json_support import FIXTURE_CATALOG, parse_one, validate
from test_json_install import _machine

cli = importlib.import_module("hammunition.cli.main")

LINE = re.compile(
    r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}Z (meta|out|err|cmd|cmd-out|cmd-err|cmd-end|result)\s"
)


def _only_log(directory: Path) -> Path:
    found = sorted(directory.glob("*.log"))
    assert len(found) == 1, found
    return found[0]


# -- argv ----------------------------------------------------------------------


def test_station_values_are_redacted_in_both_spellings() -> None:
    argv = [
        "install",
        "x",
        "--callsign",
        "N0CALL",
        "--grid-square=FN31pr",
        "--yes",
        "--mirror",
        "http://lan/",
    ]
    assert runlog.redact_argv(argv) == [
        "install",
        "x",
        "--callsign",
        "<redacted>",
        "--grid-square=<redacted>",
        "--yes",
        "--mirror",
        "<redacted>",
    ]


# -- the file ------------------------------------------------------------------


def test_a_dry_run_leaves_a_log_and_the_terminal_sees_the_same_bytes(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    _run_logs_in_tmp: Path,
) -> None:
    _machine(monkeypatch, tmp_path)
    rc = cli.main(["--catalog", str(FIXTURE_CATALOG), "install", "--dry-run", "fixture-apt"])
    captured = capsys.readouterr()
    assert rc == 0
    log = _only_log(_run_logs_in_tmp)
    text = log.read_text()
    assert re.match(r"\d{8}T\d{6}Z-install-\d+\.log$", log.name)
    assert all(LINE.match(line) for line in text.splitlines()), text
    assert "argv: hammunition --catalog" in text
    assert "command: install" in text
    assert "Dry run: nothing above was executed." in text
    assert re.search(r"result\s+exit=0 ok elapsed=", text.splitlines()[-1])
    # The terminal still gets everything, and the last line says where the log is.
    assert "Dry run: nothing above was executed." in captured.out
    assert captured.err.splitlines()[-1] == f"Log: {log}"
    # What the log holds as `out` is what stdout got, line for line.
    logged_out = [x[33:] for x in text.splitlines() if x[25:32].strip() == "out"]
    assert logged_out == captured.out.splitlines()


def test_modes_are_private(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, _run_logs_in_tmp: Path
) -> None:
    _machine(monkeypatch, tmp_path)
    cli.main(["--catalog", str(FIXTURE_CATALOG), "install", "--dry-run", "fixture-apt"])
    assert _only_log(_run_logs_in_tmp).stat().st_mode & 0o777 == 0o600
    assert _run_logs_in_tmp.stat().st_mode & 0o777 == 0o700


def test_json_output_is_unchanged_and_the_run_is_still_logged(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    _run_logs_in_tmp: Path,
) -> None:
    _machine(monkeypatch, tmp_path)
    rc = cli.main(
        ["--catalog", str(FIXTURE_CATALOG), "install", "--dry-run", "--json", "fixture-apt"]
    )
    captured = capsys.readouterr()
    assert rc == 0
    assert parse_one(captured.out)["kind"] == "plan"
    assert "Log:" not in captured.err, "a --json run's stderr is diagnostics for the document"
    assert "--json" in _only_log(_run_logs_in_tmp).read_text()


@pytest.mark.parametrize(
    "argv", [["status"], ["list", "packages"], ["doctor"], ["station", "show"]]
)
def test_readouts_leave_no_log(
    argv: list[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    _run_logs_in_tmp: Path,
) -> None:
    _machine(monkeypatch, tmp_path)
    cli.main(["--catalog", str(FIXTURE_CATALOG), *argv])
    capsys.readouterr()
    assert list(_run_logs_in_tmp.glob("*.log")) == []


def test_station_set_is_never_logged(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    _run_logs_in_tmp: Path,
) -> None:
    """Its argv *is* the station values."""
    _machine(monkeypatch, tmp_path)
    cli.main(["station", "set", "--callsign", "N0CALL"])
    capsys.readouterr()
    assert list(_run_logs_in_tmp.glob("*.log")) == []
    assert "N0CALL" not in "".join(
        p.read_text() for p in _run_logs_in_tmp.glob("**/*") if p.is_file()
    )


def test_the_log_is_readable_while_the_run_is_going(tmp_path: Path) -> None:
    """Write-through: a killed run leaves a usable log."""
    path = tmp_path / "logs" / "20261002T000000Z-install-1.log"
    run = runlog._open(path, None)
    run.write("meta", "first")
    assert "first" in path.read_text(), "flushed per line, before any close"
    assert runlog.list_runs(path.parent)[0].result == "running"
    run.close(None, 0.0)
    assert runlog.list_runs(path.parent)[0].result == "incomplete", "no result line, no holder"


def test_progress_redraws_leave_their_start_and_finish_lines(tmp_path: Path) -> None:
    run = runlog._open(tmp_path / "20261002T000000Z-install-2.log", None)
    run.feed("err", "checking 9 tiles (needs the network)…\n")
    run.feed("err", "\r  3/9")
    run.feed("err", "\r  6/9")
    run.feed("err", "\r\x1b[2Kchecked 9 tiles in 1.0 s\n")
    run.close(0, 0.0)
    text = (tmp_path / "20261002T000000Z-install-2.log").read_text()
    assert "checking 9 tiles" in text and "checked 9 tiles in 1.0 s" in text
    assert "3/9" not in text and "\x1b" not in text


def test_a_failure_to_log_never_fails_the_run(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    blocked = tmp_path / "a-file"
    blocked.write_text("x")
    monkeypatch.setattr(runlog, "logs_dir", lambda owner=None: blocked / "logs")
    _machine(monkeypatch, tmp_path)
    rc = cli.main(["--catalog", str(FIXTURE_CATALOG), "install", "--dry-run", "fixture-apt"])
    captured = capsys.readouterr()
    assert rc == 0
    assert "note: no run log for this command" in captured.err
    assert "Dry run: nothing above was executed." in captured.out


def test_a_crash_is_recorded_and_still_propagates(
    monkeypatch: pytest.MonkeyPatch, _run_logs_in_tmp: Path
) -> None:
    def boom(args: object) -> int:
        raise RuntimeError("kaboom")

    monkeypatch.setattr(cli, "cmd_install", boom)
    # the parser captured cmd_install at build time, so parse afresh after the patch
    with pytest.raises(RuntimeError):
        cli.main(["install", "--dry-run", "fixture-apt"])
    text = _only_log(_run_logs_in_tmp).read_text()
    assert "crashed:" in text and "kaboom" in text
    assert "result" in text.splitlines()[-1]


# -- commands --------------------------------------------------------------------


def test_a_command_is_logged_with_its_output_and_exit_code(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    path = tmp_path / "20261002T000000Z-install-3.log"
    run = runlog._open(path, None)
    monkeypatch.setattr(runlog, "_active", run)
    result = SubprocessRunner(euid=0).run(
        Command(
            argv=(
                sys.executable,
                "-c",
                "import sys; print('to out'); print('to err', file=sys.stderr); sys.exit(3)",
            ),
            description="a fixture command",
        )
    )
    monkeypatch.setattr(runlog, "_active", None)
    run.close(1, 0.0)
    assert (result.returncode, result.stdout, result.stderr) == (3, "to out\n", "to err\n")
    text = path.read_text()
    assert re.search(r" cmd\s+\$ .*python", text)
    assert re.search(r" cmd-out\s+to out", text) and re.search(r" cmd-err\s+to err", text)
    assert re.search(r" cmd-end\s+exit=3 elapsed=[\d.]+s", text)


def test_a_command_is_fed_its_input_and_unlogged_runs_are_unchanged(tmp_path: Path) -> None:
    command = Command(
        argv=(sys.executable, "-c", "import sys; print(sys.stdin.read().upper())"),
        description="echo upper",
        stdin="hello",
    )
    plain = SubprocessRunner(euid=0).run(command)
    run = runlog._open(tmp_path / "20261002T000000Z-install-4.log", None)
    runlog._active = run
    try:
        logged = SubprocessRunner(euid=0).run(command)
    finally:
        runlog._active = None
        run.close(0, 0.0)
    assert plain == logged and logged.stdout == "HELLO\n"


# -- rotation --------------------------------------------------------------------


def _make(directory: Path, n: int, size: int = 10) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"20260101T0000{n:02d}Z-install-{n}.log"
    path.write_text("x" * size)
    return path


def test_rotation_keeps_the_newest_files_under_the_count(tmp_path: Path) -> None:
    files = [_make(tmp_path, n) for n in range(10)]
    removed = runlog.rotate(tmp_path, max_files=4)
    # room for the log about to be created: 3 remain
    assert removed == files[:7]
    assert sorted(p.name for p in tmp_path.iterdir()) == [p.name for p in files[7:]]


def test_rotation_keeps_the_newest_files_under_the_size(tmp_path: Path) -> None:
    files = [_make(tmp_path, n, size=100) for n in range(6)]
    runlog.rotate(tmp_path, max_files=100, max_bytes=250)
    assert sorted(p.name for p in tmp_path.iterdir()) == [p.name for p in files[4:]]


def test_rotation_never_removes_a_run_in_progress(tmp_path: Path) -> None:
    oldest = tmp_path / "20260101T000000Z-install-1.log"
    live = runlog._open(oldest, None)  # holds the flock, like a running install
    try:
        newer = [_make(tmp_path, n) for n in range(2, 8)]
        runlog.rotate(tmp_path, max_files=3)
        assert oldest.exists(), "the oldest file is the one still running"
        assert [p for p in newer if p.exists()] == newer[-1:]  # the running log holds a slot
    finally:
        live.close(0, 0.0)


def test_rotation_ignores_files_that_are_not_ours(tmp_path: Path) -> None:
    keep = tmp_path / "notes.txt"
    keep.write_text("mine")
    for n in range(5):
        _make(tmp_path, n)
    runlog.rotate(tmp_path, max_files=2)
    assert keep.exists()


def test_a_run_through_the_cli_applies_the_limits(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    _run_logs_in_tmp: Path,
) -> None:
    _machine(monkeypatch, tmp_path)
    for n in range(40):
        _make(_run_logs_in_tmp, n)
    cli.main(["--catalog", str(FIXTURE_CATALOG), "install", "--dry-run", "fixture-apt"])
    capsys.readouterr()
    assert len(list(_run_logs_in_tmp.glob("*.log"))) == runlog.MAX_FILES


# -- ownership -------------------------------------------------------------------


def test_logs_dir_follows_the_operator_not_root(
    real_logs_dir: object, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    assert real_logs_dir() == tmp_path / "hammunition" / "logs"  # type: ignore[operator]
    import pwd

    entry = pwd.struct_passwd(("op", "x", 1000, 1000, "", "/home/op", "/bin/sh"))
    monkeypatch.setattr(os, "geteuid", lambda: 0)
    monkeypatch.setattr(pwd, "getpwnam", lambda name: entry)
    assert real_logs_dir("op") == Path("/home/op/.local/state/hammunition/logs")  # type: ignore[operator]


# -- `hammunition logs` -------------------------------------------------------------


def _three_runs(directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "20261001T100000Z-install-11.log").write_text(
        "2026-10-01T10:00:00.000Z meta    command: install\n"
        "2026-10-01T10:00:09.000Z result  exit=0 ok elapsed=9.0s\n"
    )
    (directory / "20261001T110000Z-uninstall-12.log").write_text(
        "2026-10-01T11:00:00.000Z result  exit=1 failed elapsed=1.0s\n"
    )
    (directory / "20261001T120000Z-hardware-apply-13.log").write_text(
        "2026-10-01T12:00:00.000Z meta    command: hardware apply\n"
    )


def test_logs_lists_newest_first(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    _run_logs_in_tmp: Path,
) -> None:
    _three_runs(_run_logs_in_tmp)
    assert cli.main(["logs"]) == 0
    out = capsys.readouterr().out
    order = [out.index(w) for w in ("hardware-apply", "uninstall", "install")]
    assert order == sorted(order)
    assert "incomplete" in out and "failed" in out and "ok" in out


def test_logs_last_and_path(capsys: pytest.CaptureFixture[str], _run_logs_in_tmp: Path) -> None:
    _three_runs(_run_logs_in_tmp)
    newest = _run_logs_in_tmp / "20261001T120000Z-hardware-apply-13.log"
    assert cli.main(["logs", "--path"]) == 0
    assert capsys.readouterr().out == f"{newest}\n"
    assert cli.main(["logs", "--last"]) == 0
    assert capsys.readouterr().out == newest.read_text()


def test_logs_with_nothing_says_so(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["logs"]) == 0
    assert "No run logs yet" in capsys.readouterr().out
    assert cli.main(["logs", "--last"]) == 1


def test_logs_json_is_a_valid_document(
    capsys: pytest.CaptureFixture[str], _run_logs_in_tmp: Path
) -> None:
    _three_runs(_run_logs_in_tmp)
    assert cli.main(["logs", "--json"]) == 0
    doc = parse_one(capsys.readouterr().out)
    validate(doc)
    assert doc["kind"] == "logs" and doc["max_files"] == runlog.MAX_FILES
    assert [r["result"] for r in doc["runs"]] == ["incomplete", "failed", "ok"]
    assert doc["runs"][0]["exit_code"] is None and doc["runs"][2]["exit_code"] == 0
    assert doc["total_bytes"] == sum(r["size"] for r in doc["runs"])
    json.dumps(doc)


def test_doctor_reports_the_log_directory_and_the_newest_result(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    _run_logs_in_tmp: Path,
) -> None:
    _machine(monkeypatch, tmp_path)
    _three_runs(_run_logs_in_tmp)
    cli.main(["--catalog", str(FIXTURE_CATALOG), "doctor", "--json"])
    doc = parse_one(capsys.readouterr().out)
    check = next(c for c in doc["checks"] if c["name"] == "run logs")
    assert "3 run log(s)" in check["detail"] and "hardware-apply" in check["detail"]
    assert "incomplete" in check["detail"]


# -- review findings -------------------------------------------------------------


def test_a_child_writing_undecodable_bytes_cannot_hang_the_run(tmp_path: Path) -> None:
    """The reader thread must keep draining: a dead pump fills the 64 KiB pipe
    and the child blocks forever."""
    import threading

    run = runlog._open(tmp_path / "20261002T000000Z-install-5.log", None)
    runlog._active = run
    box: list[object] = []

    def go() -> None:
        box.append(
            SubprocessRunner(euid=0).run(
                Command(
                    argv=(
                        sys.executable,
                        "-c",
                        "import sys; sys.stdout.buffer.write(b'\\xff' * 300000 + b'\\n')",
                    ),
                    description="binary output",
                )
            )
        )

    worker = threading.Thread(target=go, daemon=True)
    worker.start()
    worker.join(30)
    runlog._active = None
    run.close(0, 0.0)
    assert not worker.is_alive(), "the run hung on undecodable output"
    assert box[0].returncode == 0  # type: ignore[attr-defined]


def test_station_values_are_scrubbed_from_everything_logged(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    _run_logs_in_tmp: Path,
) -> None:
    _machine(monkeypatch, tmp_path)
    from hammunition.station import Station, save_station

    save_station(Station(map_regions=("us/delaware",), mirror="http://nas.example.invalid:8080"))

    def chatty(args: object) -> int:
        print("regions: us/delaware at http://nas.example.invalid:8080/x")
        print("error: callsign 'N0CALL' does not look like one", file=sys.stderr)
        return 0

    monkeypatch.setattr(cli, "cmd_install", chatty)
    cli.main(["install", "--dry-run", "--callsign", "N0CALL", "fixture-apt"])
    captured = capsys.readouterr()
    assert "us/delaware" in captured.out and "N0CALL" in captured.err, "the terminal is untouched"
    text = _only_log(_run_logs_in_tmp).read_text()
    assert "us/delaware" not in text and "N0CALL" not in text and "nas.example" not in text
    assert text.count("<redacted>") >= 3


def test_crlf_and_split_carriage_returns_keep_their_text(tmp_path: Path) -> None:
    path = tmp_path / "20261002T000000Z-install-6.log"
    run = runlog._open(path, None)
    run.feed("out", "crlf line\r\nnext\n")
    run.feed("out", "split\r")
    run.feed("out", "\nafter\n")
    run.close(0, 0.0)
    lines = [x[33:] for x in path.read_text().splitlines() if x[25:32].strip() == "out"]
    assert lines == ["crlf line", "next", "split", "after"]


def test_one_run_log_stops_at_the_cap(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(runlog, "MAX_RUN_BYTES", 500)
    path = tmp_path / "20261002T000000Z-reference-serve-7.log"
    run = runlog._open(path, None)
    for n in range(200):
        run.write("out", f"request {n}")
    run.close(0, 0.0)
    text = path.read_text()
    assert len(text) < 1500 and text.count("log truncated") == 1
    assert "result" in text.splitlines()[-1]


def test_polled_and_readout_forms_leave_no_log(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    _run_logs_in_tmp: Path,
) -> None:
    _machine(monkeypatch, tmp_path)
    cli.main(["--catalog", str(FIXTURE_CATALOG), "update", "--json"])
    cli.main(["services"])
    capsys.readouterr()
    assert list(_run_logs_in_tmp.glob("*.log")) == []
