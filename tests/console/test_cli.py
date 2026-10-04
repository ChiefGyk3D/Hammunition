# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later
import io

import pytest

from hammunition.console.__main__ import main
from hammunition.console.helptext import KEYS, USAGE
from hammunition.interface.envelope import engine_version


class Tty(io.StringIO):
    def isatty(self) -> bool:
        return True


def run(
    args: list[str], *, tty: bool = True, term: str = "xterm", euid: int = 1000
) -> tuple[int, str, str]:
    out, err = Tty() if tty else io.StringIO(), io.StringIO()
    import contextlib

    with contextlib.redirect_stderr(err):
        code = main(
            args,
            stdin=Tty() if tty else io.StringIO(),
            stdout=out,
            environ={"TERM": term},
            euid=euid,
        )
    return code, out.getvalue(), err.getvalue()


def test_version() -> None:
    code, out, _ = run(["--version"], tty=False)
    assert (code, out.strip()) == (0, f"hammunition {engine_version()}")


def test_help_lists_every_key_and_the_exit_codes() -> None:
    code, out, _ = run(["--help"], tty=False)
    assert code == 0
    for keys, meaning in KEYS:
        assert keys in out and meaning in out
    assert "Exit codes" in out and USAGE.splitlines()[0] in out


def test_unknown_argument_is_refused() -> None:
    code, _, err = run(["--bogus"])
    assert code == 2 and "--bogus" in err and "--help" in err


def test_no_tty_is_refused_before_drawing() -> None:
    code, _, err = run([], tty=False)
    assert code == 2 and "terminal" in err


def test_dumb_terminal_is_refused() -> None:
    code, _, err = run([], term="dumb")
    assert code == 2 and "TERM" in err


def test_root_is_refused() -> None:
    code, _, err = run([], euid=0)
    assert code == 2 and "root" in err


@pytest.mark.parametrize("args", [["-y"], ["--yes"]])
def test_no_assume_yes_option_exists(args: list[str]) -> None:
    code, _, err = run(args)
    assert code == 2 and "unknown argument" in err
