# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""Live feedback while a command runs (#270).

The fake command (``tests/fixtures/live/slow_lines.py``) prints a line every
0.2 s for 2 s. ``driver.py`` runs it through the real executor and runner, as
``install`` does, in a child process whose stdout is a pseudo-terminal, a pipe,
or a pseudo-terminal under ``--verbose``. The child's run log is read back and
must be the same in all three: what the operator sees live never changes what
is logged (D-077).
"""

from __future__ import annotations

import os
import pty
import re
import select
import subprocess
import sys
import time
from pathlib import Path

import pytest

from hammunition.interface.plan_group import LONG_STEP_NOTE
from hammunition.progress import LiveStatus, elapsed_text

HERE = Path(__file__).resolve().parent
FIXTURES = HERE / "fixtures" / "live"
SRC = HERE.parent / "src"
ERASE = "\r\x1b[2K"
STATUS = re.compile(r"\r\x1b\[2K  … (\d+s|\d+m \d\ds)  (.*?)(?=\r|\Z)")


def _env(tmp_path: Path) -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if not k.startswith("HAMMUNITION")}
    env.update(PYTHONPATH=str(SRC), XDG_STATE_HOME=str(tmp_path / "state"), COLUMNS="100")
    return env


def _run(tmp_path: Path, *flags: str, tty: bool) -> tuple[str, list[str]]:
    """The child's stdout and its run log's command-output lines, stamps off."""
    env = _env(tmp_path)
    argv = [sys.executable, str(FIXTURES / "driver.py"), str(FIXTURES / "slow_lines.py"), *flags]
    if tty:
        master, slave = pty.openpty()
        env["FAKE_SUDO_TTY"] = os.ttyname(slave)
        proc = subprocess.Popen(argv, stdout=slave, env=env)
        os.close(slave)
        chunks: list[bytes] = []
        while True:
            ready, _, _ = select.select([master], [], [], 0.2)
            if ready:
                try:
                    data = os.read(master, 4096)
                except OSError:
                    break
                if not data:
                    break
                chunks.append(data)
            elif proc.poll() is not None:
                break
        proc.wait()
        os.close(master)
        out = b"".join(chunks).decode().replace("\r\n", "\n")
    else:
        done = subprocess.run(argv, capture_output=True, text=True, env=env, check=True)
        out = done.stdout
    assert proc.returncode in (None, 0) if tty else True
    logs = list((tmp_path / "state").rglob("*.log"))
    assert len(logs) == 1, logs
    lines = [
        re.sub(r"^\S+ ", "", line)
        for line in logs[0].read_text().splitlines()
        if " cmd-out " in line or " cmd-err " in line
    ]
    return out, lines


def test_a_terminal_sees_one_status_line_that_refreshes_and_is_erased(tmp_path: Path) -> None:
    out, _ = _run(tmp_path, tty=True)
    shown = STATUS.findall(out)
    assert len(shown) >= 2, out
    # it carries the latest line, cleaned of colour, and refreshes as lines arrive
    assert all("\x1b" not in text for _, text in shown)
    texts = [text for _, text in shown]
    assert texts[0].startswith("step ") and texts[-1] != texts[0]
    assert len(set(texts)) >= 2
    # it is erased when the command ends: the last control sequence is the erase
    # and nothing of the status line is left after it
    assert out.rstrip("\n").endswith("done")
    assert out.rindex(ERASE) > out.rindex("  … ")
    assert "\n  … " not in out, "the status line is in place, never a scrolling line"
    assert out.count("  $ ") == 1


def test_a_pipe_gets_no_status_line_and_the_transcript_is_unchanged(tmp_path: Path) -> None:
    out, _ = _run(tmp_path, tty=False)
    assert "…" not in out and "\r" not in out and "\x1b" not in out
    assert out.splitlines()[0].startswith("  $ ")
    assert out.splitlines()[-1] == "done"
    assert len(out.splitlines()) == 2


def test_verbose_streams_every_line_in_order(tmp_path: Path) -> None:
    out, _ = _run(tmp_path, "--verbose", tty=True)
    got = [line.strip() for line in out.splitlines() if line.strip().startswith(("step ", "fin"))]
    assert [g.replace("\x1b[32m", "").replace("\x1b[0m", "") for g in got] == [
        *(f"step {i} green" for i in range(10)),
        "finished",
    ]
    assert "  … " not in out, "verbose replaces the status line"


def test_the_run_log_is_identical_across_the_three_modes(tmp_path: Path) -> None:
    _, tty_lines = _run(tmp_path / "a", tty=True)
    _, pipe_lines = _run(tmp_path / "b", tty=False)
    _, verbose_lines = _run(tmp_path / "c", "--verbose", tty=True)
    assert len(tty_lines) == 11
    assert tty_lines == pipe_lines == verbose_lines


def test_a_long_step_says_so_at_step_start(tmp_path: Path) -> None:
    out, _ = _run(tmp_path, "--long", tty=False)
    lines = out.splitlines()
    assert lines[1] == f"    {LONG_STEP_NOTE}"
    plain, _ = _run(tmp_path / "p", tty=False)
    assert LONG_STEP_NOTE not in plain


# -- the writer itself ------------------------------------------------------


class _Stream:
    def __init__(self, tty: bool) -> None:
        self.text = ""
        self._tty = tty

    def isatty(self) -> bool:
        return self._tty

    def write(self, s: str) -> int:
        self.text += s
        return len(s)

    def flush(self) -> None:
        pass


def test_the_writer_is_inert_off_a_terminal() -> None:
    stream = _Stream(tty=False)
    live = LiveStatus(stream, after=0.0, interval=0.01)  # type: ignore[arg-type]
    assert not live.active
    with live.command():
        live.output("hello\n")
        time.sleep(0.05)
    assert stream.text == ""


def test_a_print_erases_the_status_line_first(capsys: pytest.CaptureFixture[str]) -> None:
    stream = _Stream(tty=True)
    live = LiveStatus(stream, after=0.0, interval=0.01)  # type: ignore[arg-type]
    with live.command():
        live.output("working\n")
        deadline = time.monotonic() + 2
        while "working" not in stream.text and time.monotonic() < deadline:
            time.sleep(0.01)
        live.print("warning: sudo", err=True)
        assert stream.text.endswith(ERASE)
    assert "warning: sudo" in capsys.readouterr().err
    assert stream.text.endswith(ERASE)


def test_the_status_line_is_cut_to_the_terminal_width(monkeypatch: pytest.MonkeyPatch) -> None:
    stream = _Stream(tty=True)
    monkeypatch.setattr(os, "get_terminal_size", lambda fd: os.terminal_size((40, 24)))
    stream.fileno = lambda: 1  # type: ignore[attr-defined]
    live = LiveStatus(stream, after=0.0, interval=0.01)  # type: ignore[arg-type]
    with live.command():
        live.output("x" * 200 + "\n")
        deadline = time.monotonic() + 2
        while "xxx" not in stream.text and time.monotonic() < deadline:
            time.sleep(0.01)
    drawn = [m for m in STATUS.findall(stream.text) if "x" in m[1]]
    assert drawn and all(len("  … " + a + "  " + b) < 40 for a, b in drawn)
    assert drawn[0][1].endswith("…")


@pytest.mark.parametrize(
    ("seconds", "text"), [(0, "0s"), (42.9, "42s"), (102, "1m 42s"), (3725, "1h 02m")]
)
def test_elapsed_text(seconds: float, text: str) -> None:
    assert elapsed_text(seconds) == text


def test_the_status_line_never_draws_over_a_sudo_prompt(tmp_path: Path) -> None:
    """A command run through sudo draws nothing until it has printed a line:
    the fake sudo prompts on the terminal for 3 s, well past the 0.5 s the
    test's writer waits, and the prompt must still be intact."""
    out, _ = _run(tmp_path, "--sudo", tty=True)
    prompt = out.index("[sudo] password for operator: ")
    first = out.index("  … ")
    assert prompt < first
    between = out[prompt:first]
    assert between.count("\x1b[2K") == 1, "only the first draw's own erase, after the prompt"
    assert between.endswith(ERASE)
    assert len(STATUS.findall(out)) >= 2, "the status line appears once the command prints"
