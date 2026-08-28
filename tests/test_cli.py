# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""The CLI and the executor.

The property worth asserting here is not that the output looks nice. It is that
``--dry-run`` cannot drift from what a real run does, because CLAUDE.md
requires the dry run to be *complete and accurate, not approximate*. The only
durable way to hold that is for both to consume the same list of commands, and
the test for it compares the printed transcript against that list rather than
against a fixture of expected text.
"""

from __future__ import annotations

import argparse
import os
import pwd
import sys
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from hammunition.backends import (  # noqa: E402
    AptBackend,
    BackendError,
    Command,
    CommandResult,
    RecordingRunner,
)
from hammunition.cli.main import (  # noqa: E402
    EXIT_CONSENT,
    EXIT_FAILED,
    EXIT_OK,
    EXIT_UNPLANNABLE,
    build_parser,
    cmd_status,
    main,
    operator,
    render_plan,
)
from hammunition.distro import Target  # noqa: E402
from hammunition.execute import commands_for, execute  # noqa: E402
from hammunition.manifest.schema import PackageManifest  # noqa: E402
from hammunition.plan import GroupMembership, InstallPlan, PlannedPackage  # noqa: E402
from hammunition.state import TransactionLog, log_path  # noqa: E402

TARGET = Target(distro="debian", version="13", arch="x86_64")

CATALOG = REPO_ROOT / "catalog"


def _manifest() -> PackageManifest:
    return PackageManifest.model_validate(
        {
            "name": "example",
            "version": "1.0",
            "summary": "An example package",
            "categories": ["digital-modes"],
            "install": [{"install": {"method": "apt", "packages": ["example"]}}],
            "update": {"probe": {"method": "apt_policy"}},
            "documentation": {
                "what_it_does": "Does an example thing for the purposes of testing.",
                "why_you_want_it": "Because the test suite requires a valid manifest.",
                "upstream_url": "https://example.invalid/",
            },
        }
    )


def _plan(**overrides: Any) -> InstallPlan:
    manifest = _manifest()
    base: dict[str, Any] = {
        "target": TARGET,
        "packages": (
            PlannedPackage(
                manifest=manifest,
                block=manifest.install[0],
                apt_packages=("example",),
            ),
        ),
    }
    base.update(overrides)
    return InstallPlan(**base)


# ---------------------------------------------------------------------------
# The dry run and the real run cannot drift
# ---------------------------------------------------------------------------


def test_the_rendered_plan_shows_every_command_that_would_run() -> None:
    plan = _plan()
    apt = AptBackend(RecordingRunner())
    commands = commands_for(plan, apt, current_groups=frozenset())
    text = "\n".join(render_plan(plan, commands, euid=0))
    for command in commands:
        assert command.display(euid=0) in text, "a command would run without being shown"


def test_group_membership_is_planned_after_installation() -> None:
    """Debian's wireshark-common creates the `wireshark` group at install time,
    so adding the operator first would fail on a group that does not exist."""
    plan = _plan(
        group_memberships=(
            GroupMembership(
                group="wireshark",
                user="operator",
                package="wireshark",
                description="capture without root",
                detail="adds to `wireshark`",
                reverse_hint=None,
            ),
        )
    )
    commands = commands_for(plan, AptBackend(RecordingRunner()), current_groups=frozenset())
    assert commands[0].argv[0] == "apt-get"
    assert commands[-1].argv[:2] == ("gpasswd", "--add")


def test_an_operator_already_in_the_group_is_not_added_again() -> None:
    """Idempotent: every operation is safe to re-run (CLAUDE.md)."""
    plan = _plan(
        group_memberships=(
            GroupMembership(
                group="dialout",
                user="operator",
                package="example",
                description="serial access",
                detail="adds to `dialout`",
                reverse_hint=None,
            ),
        )
    )
    commands = commands_for(
        plan, AptBackend(RecordingRunner()), current_groups=frozenset({"dialout"})
    )
    assert all(c.argv[0] != "gpasswd" for c in commands)


def test_refresh_runs_before_anything_else() -> None:
    commands = commands_for(_plan(), AptBackend(RecordingRunner()), refresh=True)
    assert commands[0].argv == ("apt-get", "update")


# ---------------------------------------------------------------------------
# Execution
# ---------------------------------------------------------------------------


def test_execution_stops_at_the_first_failure(tmp_path: Path) -> None:
    """D-016: a failure stops the run. It is never a warning to continue past."""
    first = Command(argv=("false",), description="fails", requires_root=False)
    second = Command(argv=("true",), description="never runs", requires_root=False)
    runner = RecordingRunner(
        {"false": CommandResult(argv=("false",), returncode=1, stdout="", stderr="boom")}
    )
    log = TransactionLog(tmp_path / "log.jsonl")
    report = execute([first, second], runner, log=log, plan=_plan())

    assert not report.ok
    assert report.failed is first
    assert second not in runner.commands, "a command after a failure was still run"


def test_a_command_is_logged_before_it_runs(tmp_path: Path) -> None:
    """A run killed mid-apt-get must leave a record that it was started. A log
    written only on success would hide exactly the state that matters."""
    command = Command(argv=("false",), description="fails", requires_root=False)
    runner = RecordingRunner(
        {"false": CommandResult(argv=("false",), returncode=1, stdout="", stderr="")}
    )
    log = TransactionLog(tmp_path / "log.jsonl")
    execute([command], runner, log=log, plan=_plan())

    events = [entry["event"] for entry in log.read()]
    assert events.index("command_begin") < events.index("command_end")
    assert "transaction_failed" in events
    assert "transaction_end" not in events


def test_a_missing_binary_fails_the_transaction_not_the_engine(tmp_path: Path) -> None:
    """A BackendError mid-run (no sudo in a minimal container, no gpasswd) is
    a failure of this transaction: same failed report, same
    transaction_failed record, same exit-code contract. The first shipped
    version let it escape as a raw traceback, leaving the log with a
    command_begin and no ending -- the log lying by omission."""

    class Refusing(RecordingRunner):
        def run(self, command: Command) -> CommandResult:
            super().run(command)
            raise BackendError("'sudo' is not on PATH")

    command = Command(argv=("apt-get", "install"), description="x", requires_root=True)
    log = TransactionLog(tmp_path / "log.jsonl")
    report = execute([command], Refusing(), log=log, plan=_plan())

    assert not report.ok
    assert report.failed is command
    assert "sudo" in report.stderr
    events = [entry["event"] for entry in log.read()]
    assert "transaction_failed" in events
    assert "transaction_end" not in events


def test_the_echoed_line_matches_the_process_table(tmp_path: Path) -> None:
    """An unprivileged run must echo `sudo apt-get ...`, because that is what
    is in the process table. The first version echoed the euid-0 rendering
    whoever was running."""
    command = Command(argv=("apt-get", "install"), description="x", requires_root=True)
    runner = RecordingRunner()
    log = TransactionLog(tmp_path / "log.jsonl")
    lines: list[str] = []
    execute([command], runner, log=log, plan=_plan(), echo=lines.append, euid=1000)
    shown = [line for line in lines if line.lstrip().startswith("$")]
    assert shown and "sudo" in shown[0]


def test_a_successful_transaction_is_closed(tmp_path: Path) -> None:
    log = TransactionLog(tmp_path / "log.jsonl")
    report = execute(
        [Command(argv=("true",), description="ok")], RecordingRunner(), log=log, plan=_plan()
    )
    assert report.ok
    assert [e["event"] for e in log.read()][-1] == "transaction_end"


def test_the_log_records_the_target_it_ran_against(tmp_path: Path) -> None:
    log = TransactionLog(tmp_path / "log.jsonl")
    execute([], RecordingRunner(), log=log, plan=_plan())
    begin = next(e for e in log.read() if e["event"] == "transaction_begin")
    assert begin["target"]["distro"] == "debian"


# ---------------------------------------------------------------------------
# The command line itself
# ---------------------------------------------------------------------------


def test_yes_is_documented_as_not_satisfying_a_consent_gate() -> None:
    """D-021. The help text is where an operator learns this before they try it."""
    install_help = _subparser_help(build_parser(), "install")
    assert "--yes" in install_help
    assert "consent gate" in install_help


def _subparser_help(parser: Any, name: str) -> str:
    for action in parser._actions:
        if hasattr(action, "choices") and action.choices and name in action.choices:
            help_text: str = action.choices[name].format_help()
            return help_text
    raise AssertionError(f"no subparser named {name!r}")


def test_list_runs_against_the_real_catalog(capsys: Any) -> None:
    assert main(["--catalog", str(CATALOG), "list", "profiles"]) == EXIT_OK
    out = capsys.readouterr().out
    assert "rf-security" in out


def test_show_prints_the_disclosure_for_a_gated_profile(capsys: Any) -> None:
    assert main(["--catalog", str(CATALOG), "show", "rf-research"]) == EXIT_OK
    out = capsys.readouterr().out
    assert "consent-gated" in out
    assert "authorization" in out


def test_show_of_an_unknown_profile_fails_rather_than_printing_nothing(capsys: Any) -> None:
    assert main(["--catalog", str(CATALOG), "show", "nosuch"]) == EXIT_UNPLANNABLE


def test_a_catalog_path_without_packages_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(SystemExit, match="does not look like a catalog"):
        main(["--catalog", str(tmp_path), "list"])


# ---------------------------------------------------------------------------
# The documentation is checked against the code, not trusted
# ---------------------------------------------------------------------------

CLI_DOC = REPO_ROOT / "docs" / "reference" / "cli.md"


def test_the_documented_exit_codes_match_the_code() -> None:
    """A table of exit codes is exactly the kind of prose that goes stale
    silently: scripts read these, and nothing else would notice a drift."""
    import re

    table = dict(re.findall(r"^\| (\d) \| (.+?) \|$", CLI_DOC.read_text(), re.MULTILINE))
    documented = {int(code) for code in table}
    implemented = {EXIT_OK, EXIT_FAILED, EXIT_UNPLANNABLE, EXIT_CONSENT}
    assert documented == implemented


def test_every_verb_is_documented() -> None:
    """A feature is not done until it is documented (CLAUDE.md), and the docs
    generator cannot reach argparse, so this is the check."""
    text = CLI_DOC.read_text()
    verbs = _subparser_names(build_parser())
    assert verbs, "no subcommands found"
    for verb in verbs:
        assert f"`hammunition {verb}" in text, f"{verb} is undocumented"


def test_every_install_flag_is_documented() -> None:
    text = CLI_DOC.read_text()
    install = _subparser(build_parser(), "install")
    flags = {
        option
        for action in install._actions
        for option in action.option_strings
        if option.startswith("--") and option != "--help"
    }
    for flag in flags:
        assert f"`{flag}" in text, f"{flag} is undocumented"


def _subparser(parser: Any, name: str) -> Any:
    for action in parser._actions:
        if hasattr(action, "choices") and action.choices and name in action.choices:
            return action.choices[name]
    raise AssertionError(f"no subparser named {name!r}")


def _subparser_names(parser: Any) -> list[str]:
    for action in parser._actions:
        if hasattr(action, "choices") and action.choices:
            return sorted(action.choices)
    return []


def pwd_struct(*, name: str, uid: int, home: str) -> pwd.struct_passwd:
    """Minimal stand-in for a `pwd.struct_passwd`, positional fields only."""
    return pwd.struct_passwd((name, "x", uid, uid, "", home, "/bin/sh"))


# ---------------------------------------------------------------------------
# Whose log is it
# ---------------------------------------------------------------------------


def test_the_log_follows_the_operator_when_running_as_root(monkeypatch: pytest.MonkeyPatch) -> None:
    """`sudo hammunition install` wrote its record where the operator cannot see it.

    The engine already resolves who the operator is, because `gpasswd` needs a
    name. The log did not use that answer, so it landed in /root while the
    group membership went to the right person — and `hammunition status`, run
    afterwards by that person, reported no transactions at all. Two answers to
    one question is how a log ends up wrong about the thing it exists to record.
    """
    monkeypatch.setattr(os, "geteuid", lambda: 0)
    monkeypatch.setattr(
        pwd, "getpwnam", lambda name: pwd_struct(name=name, uid=1000, home=f"/home/{name}")
    )
    assert log_path("operator") == Path(
        "/home/operator/.local/state/hammunition/transactions.jsonl"
    )


def test_the_log_ignores_the_operator_when_not_root(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Running as yourself, $XDG_STATE_HOME is yours and is honoured."""
    monkeypatch.setattr(os, "geteuid", lambda: 1000)
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    assert log_path("someone-else") == tmp_path / "hammunition" / "transactions.jsonl"


def test_root_installing_for_root_keeps_the_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """A genuine root-only box is not a sudo invocation and needs no redirect."""
    monkeypatch.setattr(os, "geteuid", lambda: 0)
    monkeypatch.setattr(pwd, "getpwnam", lambda name: pwd_struct(name=name, uid=0, home="/root"))
    monkeypatch.delenv("XDG_STATE_HOME", raising=False)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: Path("/root")))
    assert log_path("root") == Path("/root/.local/state/hammunition/transactions.jsonl")


def test_the_operator_is_resolved_the_same_way_everywhere(monkeypatch: pytest.MonkeyPatch) -> None:
    """One answer, used by both the group change and the log."""
    monkeypatch.setenv("SUDO_USER", "operator")
    monkeypatch.setenv("USER", "root")
    assert operator(argparse.Namespace(user=None)) == "operator"
    assert operator(argparse.Namespace(user="explicit")) == "explicit"
    # `status` has no --user flag at all, and must still reach the same answer.
    assert operator(argparse.Namespace()) == "operator"


def _fake_root_ownership(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make every stat report a root-owned file, whoever actually runs pytest.

    ``_give_to_owner`` only touches files whose ``st_uid`` is 0 -- the ones
    root itself just created. With ``geteuid`` faked to 0 but the files really
    created by whoever runs the suite, that guard is environment-dependent:
    true under the local container harness (pytest runs as root there), false
    on a CI runner (uid 1000 creates uid-1000 files, the guard never fires,
    and both assertions below test nothing). Both tests fake the third fact
    the same way they fake the first two, instead of inheriting it from the
    invoking user -- which is how they passed local verification and failed
    the same commit's own CI.
    """
    real_stat = os.stat

    def as_root(path: object, **kwargs: object) -> os.stat_result:
        result = real_stat(path, **kwargs)  # type: ignore[arg-type]
        values = list(result)
        values[4] = 0  # st_uid
        values[5] = 0  # st_gid
        return os.stat_result(values)

    monkeypatch.setattr(os, "stat", as_root)


def test_a_root_written_log_is_handed_to_its_operator(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Created as root in somebody's home, it must end up owned by them.

    Not verifiable end to end in this project's own container harness: rootless
    podman with no /etc/subuid runs with `ignore_chown_errors`, where `chown`
    to another uid cannot succeed at all. So the call is asserted here and the
    failure path is asserted below — claiming a working chown on the strength
    of code that suppresses its own errors is the exact thing D-031 forbids.
    """
    calls: list[tuple[Path, int, int]] = []
    monkeypatch.setattr(os, "geteuid", lambda: 0)
    monkeypatch.setattr(
        pwd, "getpwnam", lambda name: pwd_struct(name=name, uid=1000, home=str(tmp_path))
    )
    monkeypatch.setattr(os, "chown", lambda path, uid, gid: calls.append((Path(path), uid, gid)))
    _fake_root_ownership(monkeypatch)

    log = TransactionLog(tmp_path / ".local" / "state" / "hammunition" / "t.jsonl", owner="radioop")
    log.append({"event": "test", "version": 1})

    assert log.ownership_error is None
    # The file and every directory made on the way to it, not just the last.
    assert {path.name for path, _, _ in calls} >= {"t.jsonl", "hammunition", "state", ".local"}
    assert all((uid, gid) == (1000, 1000) for _, uid, gid in calls)


def test_a_chown_that_cannot_happen_is_reported_not_swallowed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """`fail loudly, never silently degrade` applies to the failure log itself."""

    def refuse(path: object, uid: int, gid: int) -> None:
        raise PermissionError(1, "Operation not permitted")

    monkeypatch.setattr(os, "geteuid", lambda: 0)
    monkeypatch.setattr(
        pwd, "getpwnam", lambda name: pwd_struct(name=name, uid=1000, home=str(tmp_path))
    )
    monkeypatch.setattr(os, "chown", refuse)
    _fake_root_ownership(monkeypatch)

    log = TransactionLog(tmp_path / ".local" / "state" / "hammunition" / "t.jsonl", owner="radioop")
    log.append({"event": "test", "version": 1})

    assert log.ownership_error is not None
    assert "radioop" in log.ownership_error
    assert "chown" in log.ownership_error


# ---------------------------------------------------------------------------
# status reports the outcome, not just the intent
# ---------------------------------------------------------------------------


def _status_log(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, tail: list[dict[str, object]]
) -> str:
    """Write a transaction log (begin + given tail), run cmd_status, return stdout."""
    import io
    from contextlib import redirect_stdout

    monkeypatch.setattr(Target, "detect", classmethod(lambda cls: TARGET))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    monkeypatch.delenv("SUDO_USER", raising=False)
    monkeypatch.setenv("USER", "root")  # operator() -> "root", falsy owner path uses XDG
    log = TransactionLog(log_path())
    log.append({"event": "transaction_begin", "version": 1, "apt_packages": ["a", "b", "c"]})
    for entry in tail:
        log.append({"version": 1, **entry})
    args = argparse.Namespace(catalog=CATALOG, user=None)
    buf = io.StringIO()
    with redirect_stdout(buf):
        cmd_status(args)
    return buf.getvalue()


def test_status_reports_a_failed_transaction_as_failed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A run that died on package 3 of 20 must not read as 20 covered. This was
    the bug: cmd_status looked only at transaction_begin."""
    out = _status_log(tmp_path, monkeypatch, [{"event": "transaction_failed", "completed": 2}])
    assert "FAILED" in out
    assert "after 2 command(s)" in out


def test_status_reports_a_completed_transaction(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    out = _status_log(tmp_path, monkeypatch, [{"event": "transaction_end", "completed": 3}])
    assert "completed 3 command(s)" in out
    assert "FAILED" not in out


def test_status_reports_an_interrupted_transaction(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A begin with no terminal event (killed mid-run) is neither success nor
    failure, and must not be reported as either."""
    out = _status_log(tmp_path, monkeypatch, [{"event": "command_begin", "argv": ["apt-get"]}])
    assert "did not record an ending" in out
    assert "FAILED" not in out
    assert "completed" not in out
