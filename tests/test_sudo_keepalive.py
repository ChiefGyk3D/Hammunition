# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""sudo's ticket kept valid for the length of one transaction (D-062, #137).

A `navigation` install waited 7.8 hours at a second sudo prompt: its first
root step cached the credential, a long operator-side conversion outlived
sudo's 15 minutes, and the next root step asked again with nobody watching.

Every test here runs a fake ``sudo`` on a PATH the test controls, recording
its argv; nothing runs the real one.
"""

from __future__ import annotations

import shutil
import sys
import time
from pathlib import Path
from typing import Any

import pytest

from fake_tools import calls, install_fakes
from hammunition.backends.base import Action, Command
from hammunition.sudo_ticket import (
    KEEPALIVE_INTERVAL,
    SudoKeepalive,
    keepalive_wanted,
)

ROOT = Command(argv=("apt-get", "install", "--", "x"), description="root", requires_root=True)
OPERATOR = Command(argv=("maptool",), description="convert", requires_root=False)
FETCH = Action(kind="fetch", description="fetch", detail="https://example.org/x", perform=str)


def _wait_for(predicate: Any, timeout: float = 5.0) -> None:
    deadline = time.monotonic() + timeout
    while not predicate():
        if time.monotonic() > deadline:
            raise AssertionError("condition not reached in time")
        time.sleep(0.005)


# --- when it is wanted -------------------------------------------------------


def test_wanted_when_root_steps_and_operator_steps_are_mixed_and_not_root() -> None:
    assert keepalive_wanted([ROOT, OPERATOR, ROOT], euid=1000)
    assert keepalive_wanted([FETCH, ROOT], euid=1000)


def test_not_wanted_without_a_root_step_or_an_operator_step_or_as_root() -> None:
    assert not keepalive_wanted([OPERATOR, FETCH], euid=1000)  # never needs sudo
    assert not keepalive_wanted([ROOT, ROOT], euid=1000)  # every step under sudo
    assert not keepalive_wanted([ROOT, OPERATOR], euid=0)  # already root: no sudo at all
    assert not keepalive_wanted([], euid=1000)


def test_the_default_interval_is_well_inside_sudos_default_fifteen_minutes() -> None:
    assert KEEPALIVE_INTERVAL == 240.0


# --- the ticket, through a fake sudo on PATH ------------------------------------


def test_validate_runs_sudo_v_once_and_refresh_runs_sudo_n_v_on_the_interval(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    log = install_fakes(monkeypatch, tmp_path / "bin", {"sudo": "exit 0"})
    keepalive = SudoKeepalive(interval=0.01)
    assert keepalive.validate()
    keepalive.start()
    _wait_for(lambda: keepalive.refreshes >= 3)
    assert keepalive.stop() is None

    argvs = [c for _, c in calls(log)]
    assert argvs[0] == "sudo -v"
    assert set(argvs[1:]) == {"sudo -n -v"}, "a refresh must never be able to prompt"
    assert len(argvs) >= 4


def test_refresh_stops_when_the_transaction_ends(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The ticket is not extended beyond the run: after stop() returns,
    nothing calls sudo again."""
    log = install_fakes(monkeypatch, tmp_path / "bin", {"sudo": "exit 0"})
    keepalive = SudoKeepalive(interval=0.01)
    assert keepalive.validate()
    keepalive.start()
    _wait_for(lambda: keepalive.refreshes >= 1)
    keepalive.stop()
    after_stop = len(calls(log))
    time.sleep(0.1)  # ten intervals
    assert len(calls(log)) == after_stop
    assert not keepalive.running


def test_the_context_manager_stops_the_refresh_when_the_body_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    log = install_fakes(monkeypatch, tmp_path / "bin", {"sudo": "exit 0"})
    keepalive = SudoKeepalive(interval=0.01)
    with pytest.raises(RuntimeError), keepalive:
        keepalive.start()
        _wait_for(lambda: keepalive.refreshes >= 1)
        raise RuntimeError("a step failed")
    after = len(calls(log))
    time.sleep(0.1)
    assert len(calls(log)) == after
    assert not keepalive.running


def test_a_failing_refresh_is_reported_once_and_the_refresh_stops(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """sudo -n -v failing (ticket revoked, timestamp_timeout=0, sudoers
    changed) must never become a loop: one warning, no more refreshes, and
    the next root step prompts exactly as it did before D-062."""
    # Succeeds for sudo -v, fails for every sudo -n -v.
    log = install_fakes(
        monkeypatch, tmp_path / "bin", {"sudo": 'if [ "$1" = "-n" ]; then exit 1; fi; exit 0'}
    )
    warnings: list[str] = []
    keepalive = SudoKeepalive(interval=0.01, warn=warnings.append)
    assert keepalive.validate()
    keepalive.start()
    _wait_for(lambda: not keepalive.running)
    time.sleep(0.1)  # ten more intervals: nothing else may run
    failure = keepalive.stop()

    assert failure is not None
    assert failure.returncode == 1
    assert failure.refreshes == 0
    assert failure.argv == ("sudo", "-n", "-v")
    assert len(warnings) == 1
    assert "sudo -n -v" in warnings[0]
    assert [c for _, c in calls(log)] == ["sudo -v", "sudo -n -v"]


def test_a_failed_validation_starts_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    log = install_fakes(monkeypatch, tmp_path / "bin", {"sudo": "exit 1"})
    keepalive = SudoKeepalive(interval=0.01)
    assert not keepalive.validate()
    with pytest.raises(RuntimeError):
        keepalive.start()
    assert [c for _, c in calls(log)] == ["sudo -v"]


def test_sudo_missing_from_path_is_a_failed_validation_not_a_crash(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    monkeypatch.setenv("PATH", str(empty))
    assert not SudoKeepalive(interval=0.01).validate()


def test_the_refresh_never_passes_a_password_or_reads_stdin(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The refresh gets /dev/null on stdin: sudo -n cannot prompt, and there
    is nothing it could read if it tried. No -S, no askpass."""
    install_fakes(
        monkeypatch,
        tmp_path / "bin",
        {"sudo": f'if [ "$1" = "-n" ]; then cat > "{tmp_path}/stdin"; fi; exit 0'},
    )
    keepalive = SudoKeepalive(interval=0.01)
    assert keepalive.validate()
    keepalive.start()
    _wait_for(lambda: keepalive.refreshes >= 1)
    keepalive.stop()
    assert (tmp_path / "stdin").read_bytes() == b""


def test_the_suite_refuses_the_real_sudo(monkeypatch: pytest.MonkeyPatch) -> None:
    """Falsifies conftest's guard: with the system's sudo first on PATH, the
    keepalive is stopped before it can prompt on the developer's terminal."""
    from conftest import MachineQueried

    system = "/usr/bin:/bin:/usr/sbin:/sbin"
    if shutil.which("sudo", path=system) is None:
        pytest.skip("no sudo on this machine to refuse")
    monkeypatch.setenv("PATH", system)
    with pytest.raises(MachineQueried, match="real 'sudo'"):
        SudoKeepalive(interval=0.01).validate()


# --- the plan and the CLI -------------------------------------------------------


def _dry_run(
    monkeypatch: pytest.MonkeyPatch, capsys: Any, tmp_path: Path, *extra: str
) -> tuple[str, Path]:
    from hammunition.cli.main import main
    from test_cli import CATALOG, _mock_apt

    _mock_apt(monkeypatch, populated=True)
    monkeypatch.setattr("os.geteuid", lambda: 1000)
    log = install_fakes(monkeypatch, tmp_path / "bin", {"sudo": "exit 0"})
    rc = main(["--catalog", str(CATALOG), "install", "--dry-run", *extra, "acarsdec"])
    assert rc == 0
    return capsys.readouterr().out, log


def test_the_plan_says_the_ticket_is_kept_and_a_dry_run_never_runs_sudo(
    monkeypatch: pytest.MonkeyPatch, capsys: Any, tmp_path: Path
) -> None:
    out, log = _dry_run(monkeypatch, capsys, tmp_path)
    assert "sudo (D-062):" in out
    flat = " ".join(out.split())
    assert (
        "sudo's ticket is kept valid for the length of this transaction; "
        "it is not extended beyond it." in flat
    )
    assert "--no-sudo-keepalive turns this off" in flat
    # Disclosed before the commands, like every other section.
    assert out.index("sudo (D-062):") < out.index("Commands (")
    assert calls(log) == [], "a dry run must never run sudo, not even sudo -v"


def test_no_sudo_keepalive_says_the_run_may_prompt_again(
    monkeypatch: pytest.MonkeyPatch, capsys: Any, tmp_path: Path
) -> None:
    out, log = _dry_run(monkeypatch, capsys, tmp_path, "--no-sudo-keepalive")
    flat = " ".join(out.split())
    assert "kept valid for the length" not in flat
    assert "may ask for the password again" in flat
    assert "Do not leave the run unattended." in flat
    assert calls(log) == []


def test_the_json_plan_carries_the_same_disclosure(
    monkeypatch: pytest.MonkeyPatch, capsys: Any, tmp_path: Path
) -> None:
    import json

    out, _ = _dry_run(monkeypatch, capsys, tmp_path, "--json")
    sudo = json.loads(out)["install"]["sudo"]
    assert sudo["keepalive"] is True
    assert sudo["interval_seconds"] == 240
    assert sudo["text"].startswith("sudo's ticket is kept valid")


class _Log:
    def __init__(self) -> None:
        self.entries: list[dict[str, Any]] = []

    def append(self, entry: dict[str, Any]) -> None:
        self.entries.append(dict(entry))


def _report() -> Any:
    from hammunition.execute import ExecutionReport

    return ExecutionReport(completed=(), failed=None, stderr="")


def test_a_confirmed_run_validates_first_refreshes_during_and_stops_after(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: Any
) -> None:
    from hammunition.cli.main import run_with_sudo_ticket

    log_file = install_fakes(monkeypatch, tmp_path / "bin", {"sudo": "exit 0"})
    log = _Log()
    seen_at_start: list[list[str]] = []

    def run() -> Any:
        # sudo -v has already asked, before the first step.
        seen_at_start.append([c for _, c in calls(log_file)])
        _wait_for(lambda: len(calls(log_file)) >= 3)
        return _report()

    report = run_with_sudo_ticket(
        [ROOT, OPERATOR, ROOT],
        euid=1000,
        keepalive=True,
        log=log,  # type: ignore[arg-type]
        run=run,
        make_keepalive=lambda: SudoKeepalive(interval=0.01),
    )
    assert report.ok
    assert seen_at_start == [["sudo -v"]]
    after = len(calls(log_file))
    time.sleep(0.1)
    assert len(calls(log_file)) == after, "the ticket is not extended beyond the run"

    events = [e["event"] for e in log.entries]
    assert events == ["sudo_keepalive_begin", "sudo_keepalive_end"]
    assert log.entries[0]["validated"] is True
    assert log.entries[1]["refreshes"] >= 2
    assert log.entries[1]["failed"] is None
    assert "asking once, before the first step" in capsys.readouterr().out


def test_the_refresh_stops_when_the_transaction_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from hammunition.cli.main import run_with_sudo_ticket

    log_file = install_fakes(monkeypatch, tmp_path / "bin", {"sudo": "exit 0"})
    log = _Log()

    def run() -> Any:
        _wait_for(lambda: len(calls(log_file)) >= 2)
        raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        run_with_sudo_ticket(
            [ROOT, OPERATOR],
            euid=1000,
            keepalive=True,
            log=log,  # type: ignore[arg-type]
            run=run,
            make_keepalive=lambda: SudoKeepalive(interval=0.01),
        )
    after = len(calls(log_file))
    time.sleep(0.1)
    assert len(calls(log_file)) == after
    assert log.entries[-1]["event"] == "sudo_keepalive_end"


def test_a_failing_refresh_is_logged_once_and_the_run_carries_on(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: Any
) -> None:
    from hammunition.cli.main import run_with_sudo_ticket

    log_file = install_fakes(
        monkeypatch, tmp_path / "bin", {"sudo": 'if [ "$1" = "-n" ]; then exit 1; fi; exit 0'}
    )
    log = _Log()

    def run() -> Any:
        _wait_for(lambda: len(calls(log_file)) >= 2)
        time.sleep(0.1)
        return _report()

    report = run_with_sudo_ticket(
        [ROOT, OPERATOR],
        euid=1000,
        keepalive=True,
        log=log,  # type: ignore[arg-type]
        run=run,
        make_keepalive=lambda: SudoKeepalive(
            interval=0.01, warn=lambda m: print(f"warning: {m}", file=sys.stderr)
        ),
    )
    assert report.ok
    assert [c for _, c in calls(log_file)] == ["sudo -v", "sudo -n -v"]
    failed = log.entries[-1]["failed"]
    assert failed["argv"] == ["sudo", "-n", "-v"] and failed["returncode"] == 1
    assert capsys.readouterr().err.count("no longer being kept valid") == 1


def test_a_failed_sudo_v_runs_the_transaction_as_before(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: Any
) -> None:
    from hammunition.cli.main import run_with_sudo_ticket

    log_file = install_fakes(monkeypatch, tmp_path / "bin", {"sudo": "exit 1"})
    log = _Log()
    ran: list[bool] = []

    def run() -> Any:
        ran.append(True)
        return _report()

    run_with_sudo_ticket(
        [ROOT, OPERATOR],
        euid=1000,
        keepalive=True,
        log=log,  # type: ignore[arg-type]
        run=run,
        make_keepalive=lambda: SudoKeepalive(interval=0.01),
    )
    assert ran == [True]
    time.sleep(0.05)
    assert [c for _, c in calls(log_file)] == ["sudo -v"]
    assert [e["event"] for e in log.entries] == ["sudo_keepalive_begin"]
    assert log.entries[0]["validated"] is False
    assert "did not succeed" in capsys.readouterr().err


@pytest.mark.parametrize(
    ("keepalive", "euid", "steps"),
    [
        (False, 1000, [ROOT, OPERATOR]),  # --no-sudo-keepalive
        (True, 0, [ROOT, OPERATOR]),  # already root
        (True, 1000, [ROOT, ROOT]),  # nothing between the root steps
    ],
)
def test_no_sudo_at_all_when_opted_out_or_not_wanted(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    keepalive: bool,
    euid: int,
    steps: list[Command],
) -> None:
    from hammunition.cli.main import run_with_sudo_ticket

    log_file = install_fakes(monkeypatch, tmp_path / "bin", {"sudo": "exit 0"})
    log = _Log()
    run_with_sudo_ticket(
        steps,
        euid=euid,
        keepalive=keepalive,
        log=log,  # type: ignore[arg-type]
        run=_report,
        make_keepalive=lambda: SudoKeepalive(interval=0.01),
    )
    assert calls(log_file) == []
    assert log.entries == []


def test_the_events_go_through_the_real_transaction_log(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The log writer refuses credential-looking keys; these events must
    carry none, and read back as the reference page describes them."""
    import json

    from hammunition.cli.main import run_with_sudo_ticket
    from hammunition.state import TransactionLog

    install_fakes(monkeypatch, tmp_path / "bin", {"sudo": "exit 0"})
    log = TransactionLog(tmp_path / "transactions.jsonl")
    run_with_sudo_ticket(
        [ROOT, OPERATOR],
        euid=1000,
        keepalive=True,
        log=log,
        run=_report,
        make_keepalive=lambda: SudoKeepalive(interval=0.01),
    )
    entries = [json.loads(line) for line in log.path.read_text().splitlines()]
    assert [e["event"] for e in entries] == ["sudo_keepalive_begin", "sudo_keepalive_end"]
    assert entries[0]["interval_seconds"] == 0.01
    assert set(entries[1]) == {"event", "version", "timestamp", "refreshes", "failed"}
