# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later
import json
import os
import pty
import select
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

from . import fake_hammunition as fake
from .helpers import load, make_shim

FAKE = Path(fake.__file__)


def test_status_comes_from_its_fixture() -> None:
    out, code = fake.respond(["hammunition", "status", "--json"]) or ("", -1)
    assert code == 0 and json.loads(out) == load("status")


def test_exit_codes_come_from_the_sidecar() -> None:
    out, code = fake.respond(["hammunition", "update", "--json"], suffix="-without") or ("", -1)
    assert code == 2 and json.loads(out)["kind"] == "error"


def test_install_dry_run_returns_a_plan_and_refused_names_return_the_refusal() -> None:
    out, code = fake.respond(["hammunition", "install", "station", "--dry-run", "--json"]) or (
        "",
        -1,
    )
    assert json.loads(out)["kind"] == "plan" and code == 0
    out, code = fake.respond(
        ["hammunition", "install", "no-such-unit-xyz", "--dry-run", "--json"]
    ) or ("", -1)
    assert json.loads(out)["outcome"] == "refused" and code == 2


def test_station_show_follows_the_station_variant() -> None:
    out, _ = fake.respond(["hammunition", "station", "show", "--json"], station="none") or ("", -1)
    assert json.loads(out)["callsign"] is None


def test_an_unmapped_argv_is_none() -> None:
    assert fake.respond(["hammunition", "hardware", "list", "--json"]) is None


def run_shim(
    tmp: Path, *args: str, stdin: int | None = subprocess.DEVNULL
) -> subprocess.CompletedProcess[str]:
    shim = make_shim(tmp)
    env = {**os.environ, "PATH": f"{shim}:{os.environ['PATH']}"}
    return subprocess.run(
        ["hammunition", *args], capture_output=True, text=True, env=env, stdin=stdin
    )


def test_a_real_install_without_a_tty_is_refused_like_the_engine(tmp_path: Path) -> None:
    done = run_shim(tmp_path, "install", "station")
    assert done.returncode == 3 and "no interactive terminal" in done.stderr


def test_an_unmapped_read_fails_loudly(tmp_path: Path) -> None:
    done = run_shim(tmp_path, "hardware", "list", "--json")
    assert done.returncode == 99 and "FAKE: unmapped" in done.stderr


def test_the_invocation_log_records_argv_tty_and_consent_looking_variables(tmp_path: Path) -> None:
    log = tmp_path / "log.jsonl"
    shim = make_shim(tmp_path)
    env = {
        **os.environ,
        "PATH": f"{shim}:{os.environ['PATH']}",
        "FAKE_HAMMUNITION_LOG": str(log),
        "HAMMUNITION_ACCEPT_RF_RESEARCH": "1",
    }
    subprocess.run(
        ["hammunition", "status", "--json"], env=env, capture_output=True, stdin=subprocess.DEVNULL
    )
    entry = json.loads(log.read_text().splitlines()[0])
    assert entry["argv"] == ["status", "--json"] and entry["tty"] is False
    assert "HAMMUNITION_ACCEPT_RF_RESEARCH" in entry["env"]


def test_the_script_runs_standalone_with_the_current_interpreter() -> None:
    done = subprocess.run([sys.executable, str(FAKE), "--version"], capture_output=True, text=True)
    assert done.returncode == 0 and done.stdout.startswith("hammunition ")


def run_on_pty(tmp: Path, args: list[str], typed: bytes | None) -> tuple[int, str]:
    """Run the shim with a pty as stdin and stdout; type `typed` (None: close the tty's input at once)."""
    shim = make_shim(tmp)
    env = {**os.environ, "PATH": f"{shim}:{os.environ['PATH']}"}
    pid, fd = pty.fork()
    if pid == 0:
        os.execvpe("hammunition", ["hammunition", *args], env)
    out = b""
    deadline = time.monotonic() + 10
    sent = False
    try:
        while time.monotonic() < deadline:
            ready, _, _ = select.select([fd], [], [], 0.2)
            if ready:
                try:
                    chunk = os.read(fd, 4096)
                except OSError:
                    break
                if not chunk:
                    break
                out += chunk
                if not sent and b": " in out:
                    sent = True
                    os.write(fd, typed if typed is not None else b"\x04")
        else:
            os.kill(pid, signal.SIGKILL)
            os.waitpid(pid, 0)
            raise AssertionError(f"timed out; output so far: {out!r}")
        _, status = os.waitpid(pid, 0)
    finally:
        os.close(fd)
    return os.waitstatus_to_exitcode(status), out.decode()


def test_a_typed_yes_on_a_tty_confirms_and_exits_0(tmp_path: Path) -> None:
    code, out = run_on_pty(tmp_path, ["install", "station"], b"yes\n")
    assert code == 0 and "confirmed" in out and "installed" in out


def test_anything_else_on_a_tty_is_declined_with_exit_3(tmp_path: Path) -> None:
    code, out = run_on_pty(tmp_path, ["install", "station"], b"no\n")
    assert code == 3 and "declined" in out and "installed" not in out


def test_end_of_input_on_a_tty_is_a_refusal(tmp_path: Path) -> None:
    code, out = run_on_pty(tmp_path, ["install", "station"], None)
    assert code == 3 and "confirmed" not in out


def test_hardware_apply_asks_on_a_tty_and_logs_its_argv(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    log = tmp_path / "log.jsonl"
    monkeypatch.setenv("FAKE_HAMMUNITION_LOG", str(log))
    code, out = run_on_pty(tmp_path, ["hardware", "apply"], b"yes\n")
    assert code == 0 and "udev" in out
    assert json.loads(log.read_text().splitlines()[0]) == {
        "argv": ["hardware", "apply"],
        "tty": True,
        "env": [],
    }


def test_hardware_apply_without_a_tty_is_refused(tmp_path: Path) -> None:
    done = run_shim(tmp_path, "hardware", "apply")
    assert done.returncode == 3 and "no interactive terminal" in done.stderr


def test_station_set_succeeds_and_is_logged(tmp_path: Path) -> None:
    log = tmp_path / "log.jsonl"
    shim = make_shim(tmp_path)
    env = {**os.environ, "PATH": f"{shim}:{os.environ['PATH']}", "FAKE_HAMMUNITION_LOG": str(log)}
    done = subprocess.run(
        ["hammunition", "station", "set", "--callsign", "N0TST"],
        env=env,
        capture_output=True,
        text=True,
        stdin=subprocess.DEVNULL,
    )
    assert done.returncode == 0 and "saved" in done.stdout
    assert json.loads(log.read_text().splitlines()[0])["argv"] == [
        "station",
        "set",
        "--callsign",
        "N0TST",
    ]
