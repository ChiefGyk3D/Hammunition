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
    Action,
    AptBackend,
    BackendError,
    Command,
    CommandResult,
    RecordingRunner,
    SourceBackend,
)
from hammunition.backends.apt import AptPackageState  # noqa: E402
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
from hammunition.execute import commands_for, execute, verify_effects  # noqa: E402
from hammunition.fetch import Fetcher  # noqa: E402
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


def _argv(step: Any) -> tuple[str, ...]:
    """The argv of a step that must be a Command.

    `commands_for` returns Command | Action now that a source build contributes
    in-process steps, so a test asserting on an argv says which it expects
    rather than assuming.
    """
    assert isinstance(step, Command), f"expected a Command, got {type(step).__name__}"
    return step.argv


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
    assert _argv(commands[0])[0] == "apt-get"
    assert _argv(commands[-1])[:2] == ("gpasswd", "--add")


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
    assert all(_argv(c)[0] != "gpasswd" for c in commands)


def test_refresh_runs_before_anything_else() -> None:
    commands = commands_for(_plan(), AptBackend(RecordingRunner()), refresh=True)
    assert _argv(commands[0]) == ("apt-get", "update")


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
# Effect verification (D-031): exit 0 is not evidence the change took
# ---------------------------------------------------------------------------


class _FakeProber:
    """A prober that returns a chosen apt state, so a package that did not land
    can be tested without an apt that refuses to install one."""

    def __init__(self, states: dict[str, AptPackageState]) -> None:
        self.states = states
        self.asked: list[str] = []

    def probe(self, packages: Any) -> dict[str, AptPackageState]:
        self.asked = list(packages)
        return {name: self.states[name] for name in packages if name in self.states}


def _installed(name: str) -> AptPackageState:
    return AptPackageState(name=name, installed="1.0", candidate="1.0")


def test_a_package_that_did_not_land_is_a_discrepancy() -> None:
    """apt-get exited 0; apt reports the package absent. That is the exact
    shape D-031 exists to catch, and it must not read as success."""
    prober = _FakeProber({})  # apt knows nothing about it afterwards
    verification = verify_effects(_plan(), prober)
    assert prober.asked == ["example"], "the effect check must actually re-probe apt"
    assert not verification.ok
    assert [c.subject for c in verification.discrepancies] == ["example"]


def test_a_package_confirmed_installed_verifies() -> None:
    verification = verify_effects(_plan(), _FakeProber({"example": _installed("example")}))
    assert verification.ok
    assert [c.subject for c in verification.confirmed] == ["example"]


def _deb_plan() -> InstallPlan:
    """A vendor .deb unit whose deb_package is `xunit`, with no apt work."""
    manifest = PackageManifest.model_validate(
        {
            "name": "vendored",
            "version": "1.0",
            "summary": "A vendor .deb that takes over a package name",
            "categories": ["digital-modes"],
            "install": [
                {
                    "install": {
                        "method": "binary",
                        "artifact": {"url": "https://example.invalid/x.deb", "sha256": "0" * 64},
                        "format": "deb",
                        "deb_package": "xunit",
                    }
                }
            ],
            "update": {"probe": {"method": "none"}},
            "documentation": {
                "what_it_does": "Stands in for wsjtx-improved.",
                "why_you_want_it": "Its .deb takes over the distro package's name.",
                "upstream_url": "https://example.invalid/",
            },
        }
    )
    return InstallPlan(
        target=TARGET,
        packages=(PlannedPackage(manifest=manifest, block=manifest.install[0], apt_packages=()),),
    )


def test_a_vendor_deb_that_did_not_land_is_a_discrepancy() -> None:
    """wsjtx-improved on Debian 13 (2026-09-03) ended `verified: true` with
    `checks: []`: the .deb's package is not in apt_to_install and the
    binaries check skips deb formats, so nothing was asked. `apt-get
    install ./file.deb` exiting 0 is the exit status; the effect is dpkg
    holding the declared deb_package, and that is what must be probed."""
    prober = _FakeProber({})
    verification = verify_effects(_deb_plan(), prober)
    assert prober.asked == ["xunit"], "the deb_package must be re-probed"
    assert not verification.ok
    assert [c.subject for c in verification.discrepancies] == ["xunit"]


def test_a_vendor_deb_confirmed_installed_verifies() -> None:
    verification = verify_effects(_deb_plan(), _FakeProber({"xunit": _installed("xunit")}))
    assert verification.ok
    assert [c.subject for c in verification.confirmed] == ["xunit"]


def test_a_membership_absent_from_the_group_db_is_a_discrepancy() -> None:
    """gpasswd exited 0; the group database does not show the membership."""
    plan = _plan(
        packages=(),
        group_memberships=(
            GroupMembership(
                group="dialout",
                user="operator",
                package="example",
                description="serial access",
                detail="adds to dialout",
                reverse_hint=None,
            ),
        ),
    )
    absent = verify_effects(plan, None, group_lookup=lambda _u: frozenset())
    assert not absent.ok
    present = verify_effects(plan, None, group_lookup=lambda _u: frozenset({"dialout"}))
    assert present.ok


def _built_plan(tmp_path: Path) -> InstallPlan:
    """A git unit declaring one binary, planned against a fake target."""
    manifest = PackageManifest.model_validate(
        {
            "name": "builtish",
            "version": "1.0",
            "summary": "A build that declares what it installs",
            "categories": ["digital-modes"],
            "install": [
                {
                    "install": {
                        "method": "git",
                        "repo": "https://example.invalid/builtish",
                        "ref": "v1.0",
                        "build_system": "cmake",
                    }
                }
            ],
            "binaries": [{"produced": "Builtish", "install_as": "builtish"}],
            "update": {"probe": {"method": "none"}},
            "documentation": {
                "what_it_does": "Stands in for a source build.",
                "why_you_want_it": "To prove the effect check looks for its binary.",
                "upstream_url": "https://example.invalid/",
            },
        }
    )
    return InstallPlan(
        target=TARGET,
        packages=(PlannedPackage(manifest=manifest, block=manifest.install[0], apt_packages=()),),
    )


def test_a_declared_binary_that_was_never_installed_is_unconfirmed(tmp_path: Path) -> None:
    """js8call's `cmake --install` has no rule for its executable: it exits 0,
    writes an empty install manifest, and four targets reported the unit
    confirmed with no /usr/local/bin/js8call. The check is the file."""
    verification = verify_effects(_built_plan(tmp_path), None, prefix=tmp_path / "p")
    assert not verification.ok
    (check,) = verification.discrepancies
    assert check.kind == "binary"
    assert check.subject == "builtish:builtish"
    assert (
        "no executable at" in check.detail
        and str(tmp_path / "p" / "bin" / "builtish") in check.detail
    )


def test_a_declared_binary_present_and_executable_is_confirmed(tmp_path: Path) -> None:
    binary = tmp_path / "p" / "bin" / "builtish"
    binary.parent.mkdir(parents=True)
    binary.write_text("#!/bin/sh\n")
    not_executable = verify_effects(_built_plan(tmp_path), None, prefix=tmp_path / "p")
    assert not not_executable.ok, (
        "a file that cannot be run is not the binary the manifest promised"
    )
    binary.chmod(0o755)
    verification = verify_effects(_built_plan(tmp_path), None, prefix=tmp_path / "p")
    assert verification.ok
    assert verification.confirmed[0].kind == "binary"


def test_without_a_prefix_binaries_are_an_unasked_question(tmp_path: Path) -> None:
    """Symmetry with the prober: no prefix means the built half is absent from
    the checks, not reported as failed."""
    verification = verify_effects(_built_plan(tmp_path), None)
    assert verification.checks == ()


def test_execute_records_the_effect_check_in_transaction_end(tmp_path: Path) -> None:
    """The verdict lands in transaction_end — the record uninstall will trust —
    not only in the return value."""
    log = TransactionLog(tmp_path / "log.jsonl")
    report = execute(
        [Command(argv=("true",), description="ok")],
        RecordingRunner(),
        log=log,
        plan=_plan(),
        prober=_FakeProber({"example": _installed("example")}),
    )
    assert report.verified
    end = next(e for e in log.read() if e["event"] == "transaction_end")
    assert end["version"] == 2
    assert end["verified"] is True
    assert any(c["subject"] == "example" and c["confirmed"] for c in end["checks"])


def test_execute_flags_an_unconfirmed_effect(tmp_path: Path) -> None:
    log = TransactionLog(tmp_path / "log.jsonl")
    report = execute(
        [Command(argv=("true",), description="ok")],
        RecordingRunner(),
        log=log,
        plan=_plan(),
        prober=_FakeProber({}),  # nothing landed
    )
    assert report.ok, "the command still exited 0"
    assert not report.verified, "but the effect was not confirmed"
    end = next(e for e in log.read() if e["event"] == "transaction_end")
    assert end["verified"] is False


def test_a_probe_failure_records_unverified_not_a_crash(tmp_path: Path) -> None:
    """If the re-probe itself fails, the run does not crash and does not claim
    success it cannot back up — it records the check as unverified."""

    class Broken:
        def probe(self, packages: Any) -> dict[str, AptPackageState]:
            raise BackendError("apt-cache policy failed")

    log = TransactionLog(tmp_path / "log.jsonl")
    report = execute(
        [Command(argv=("true",), description="ok")],
        RecordingRunner(),
        log=log,
        plan=_plan(),
        prober=Broken(),
    )
    assert report.ok
    assert not report.verified
    assert report.verification is not None
    assert report.verification.discrepancies[0].kind == "verification"


def test_no_prober_and_no_groups_records_no_verification(tmp_path: Path) -> None:
    """An older-shaped call with nothing to verify writes transaction_end
    without a verdict, rather than inventing `verified: true`."""
    log = TransactionLog(tmp_path / "log.jsonl")
    report = execute(
        [Command(argv=("true",), description="ok")],
        RecordingRunner(),
        log=log,
        plan=_plan(packages=()),
    )
    assert report.verification is None
    assert not report.verified
    end = next(e for e in log.read() if e["event"] == "transaction_end")
    assert "verified" not in end


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


# ---------------------------------------------------------------------------
# install, end to end through main() — the wiring both shipped M1 bugs lived in
# ---------------------------------------------------------------------------


def _mock_apt(monkeypatch: pytest.MonkeyPatch, *, populated: bool) -> None:
    """A target and an apt backend that need no real machine, so main()'s
    install path can be driven end to end. Resolution calls lists_populated(),
    probe() and simulate(); nothing here executes, because every test below is
    --dry-run.

    simulate() must be covered too: it is a real ``apt-get --simulate`` and
    unprivileged, so it runs during a dry run by design. Left to the machine,
    this test passed on every dev box and GitHub runner that has a ``git``
    package and failed inside all four target containers, whose apt lists are
    empty — the "test the matrix, not your machine" shape, again."""
    from hammunition.backends.apt import AptBackend, AptPackageState, AptSimulation

    monkeypatch.setattr(Target, "detect", classmethod(lambda cls: TARGET))
    monkeypatch.setattr(AptBackend, "lists_populated", lambda self: populated)
    monkeypatch.setattr(
        AptBackend,
        "probe",
        lambda self, pkgs: {
            p: AptPackageState(name=p, installed=None, candidate="1.0") for p in pkgs
        },
    )
    monkeypatch.setattr(
        AptBackend,
        "simulate",
        lambda self, pkgs, *, release=None: AptSimulation(
            ok=True, installs={p: frozenset({"stable"}) for p in pkgs}, release=release
        ),
    )


def test_install_dry_run_prints_the_plan_and_executes_nothing(
    monkeypatch: pytest.MonkeyPatch, capsys: Any
) -> None:
    """The dry-run early return, driven through main() — not resolve() in
    isolation. This is the seam the review found untested, where --refresh not
    reaching resolution and the sudo/env boundary both hid."""
    _mock_apt(monkeypatch, populated=True)
    rc = main(["--catalog", str(CATALOG), "install", "--dry-run", "git"])
    out = capsys.readouterr().out
    assert rc == EXIT_OK
    assert "git" in out
    assert "will install" in out
    assert "Dry run: nothing above was executed." in out
    # The transaction log write is disclosed in the plan, not left to surface
    # after the fact (#3).
    assert "Records:" in out
    assert "transaction log written to" in out


def test_install_refresh_on_empty_lists_is_plannable_through_main(
    monkeypatch: pytest.MonkeyPatch, capsys: Any
) -> None:
    """--refresh on a fresh machine must produce a plan, not the blocker that
    tells you to pass the flag you just passed. End to end, the bug #1 shape."""
    _mock_apt(monkeypatch, populated=False)
    rc = main(["--catalog", str(CATALOG), "install", "--dry-run", "--refresh", "git"])
    out = capsys.readouterr().out
    assert rc == EXIT_OK
    assert "apt-get update" in out  # the refresh command is in the plan
    assert "cannot be known" in out  # the disclosed loss of the candidate check
    assert "Dry run: nothing above was executed." in out


def test_install_without_refresh_on_empty_lists_is_blocked_through_main(
    monkeypatch: pytest.MonkeyPatch, capsys: Any
) -> None:
    """The other side: no --refresh on empty lists is still a blocker."""
    _mock_apt(monkeypatch, populated=False)
    rc = main(["--catalog", str(CATALOG), "install", "--dry-run", "git"])
    err = capsys.readouterr().err
    assert rc == EXIT_UNPLANNABLE
    assert "apt-get update" in err


def test_the_log_destination_is_disclosed_and_a_bad_owner_is_not_silent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """render_plan shows where the log goes, so a root run whose operator does
    not resolve — and whose log therefore falls back to /root — says so in the
    plan instead of doing it silently (#6)."""
    import pwd as _pwd

    from hammunition.state import log_path

    monkeypatch.setattr(os, "geteuid", lambda: 0)
    real = _pwd.getpwnam
    monkeypatch.setattr(
        _pwd, "getpwnam", lambda n: (_ for _ in ()).throw(KeyError(n)) if n == "typo" else real(n)
    )
    monkeypatch.delenv("XDG_STATE_HOME", raising=False)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: Path("/root")))
    dest = log_path("typo")
    assert str(dest).startswith("/root"), "an unresolved owner falls back to root's home"
    lines = render_plan(_plan(), [], euid=0, log_destination=dest, hands_log_to=None)
    text = "\n".join(lines)
    assert "Records:" in text
    assert str(dest) in text  # the /root path is visible, not silent


# ---------------------------------------------------------------------------
# Source builds reach the command list
# ---------------------------------------------------------------------------


def _source_plan(tmp_path: Path) -> InstallPlan:
    manifest = PackageManifest.model_validate(
        {
            "name": "example",
            "version": "1.0",
            "summary": "An example built from source",
            "categories": ["digital-modes"],
            "install": [
                {
                    "install": {
                        "method": "source",
                        "source": {
                            "url": "https://example.invalid/example-1.0.tar.gz",
                            "sha256": "b" * 64,
                        },
                        "build_system": "autotools",
                    },
                    "build_depends": ["libexample-dev"],
                }
            ],
            "update": {"probe": {"method": "none"}},
            "documentation": {
                "what_it_does": "Does an example thing for the purposes of testing.",
                "why_you_want_it": "Because the test suite requires a valid manifest.",
                "upstream_url": "https://example.invalid/",
            },
        }
    )
    return InstallPlan(
        target=TARGET,
        packages=(
            PlannedPackage(
                manifest=manifest,
                block=manifest.install[0],
                apt_packages=("libexample-dev",),
                build_only=("libexample-dev",),
            ),
        ),
    )


def _source_backend(tmp_path: Path) -> SourceBackend:
    return SourceBackend(Fetcher(tmp_path / "cache"), build_root=tmp_path / "build", jobs=2)


def test_every_fetch_runs_before_apt_and_apt_before_a_build(tmp_path: Path) -> None:
    """Order is not cosmetic, twice over. Every download is fetched and
    verified before the first thing that changes the machine, so a wrong
    sha256 or a dead URL (D-018) is a refusal on an untouched system rather
    than a failure after apt has installed a toolchain for a build that will
    never start. Then apt, because ./configure cannot succeed before
    build_depends are installed."""
    steps = commands_for(
        _source_plan(tmp_path),
        AptBackend(RecordingRunner()),
        source=_source_backend(tmp_path),
        refresh=True,
    )
    labels = [s.kind if isinstance(s, Action) else s.argv[0] for s in steps]
    assert labels == ["fetch", "apt-get", "apt-get", "extract", "./configure", "make", "make"]
    assert _argv(steps[1]) == ("apt-get", "update")


def test_a_fetch_that_fails_leaves_apt_unrun(tmp_path: Path) -> None:
    """The property the order buys: nothing has been installed when a
    download fails verification, so there is nothing to explain or undo."""
    runner = RecordingRunner()
    apt = AptBackend(runner)
    steps = commands_for(_source_plan(tmp_path), apt, source=_source_backend(tmp_path))
    log = TransactionLog(tmp_path / "log.jsonl")
    # The URL is example.invalid: the fetch fails, which is the point.
    report = execute(steps, runner, log=log, plan=_source_plan(tmp_path))
    assert not report.ok
    assert isinstance(report.failed, Action) and report.failed.kind == "fetch"
    assert runner.commands == []


def test_a_source_build_without_a_backend_is_an_error_not_a_skip(tmp_path: Path) -> None:
    """Silently dropping the one step that installs the software would report a
    successful run that installed nothing."""
    with pytest.raises(BackendError, match="source build"):
        commands_for(_source_plan(tmp_path), AptBackend(RecordingRunner()), source=None)


def test_the_plan_marks_build_dependencies_as_such(tmp_path: Path) -> None:
    """`glfer needs GTK2` and `glfer is GTK2` are different claims."""
    plan = _source_plan(tmp_path)
    steps = commands_for(plan, AptBackend(RecordingRunner()), source=_source_backend(tmp_path))
    text = "\n".join(render_plan(plan, steps, euid=0))
    assert "libexample-dev  (to build)" in text


def test_an_in_process_step_is_logged_like_a_command(tmp_path: Path) -> None:
    """An Action fails the transaction on the same contract a Command does, and
    a run killed mid-extraction must leave a record that extraction started."""
    performed: list[str] = []

    def boom() -> str:
        performed.append("tried")
        raise BackendError("the archive was not what the manifest said")

    action = Action(kind="extract", description="Unpack it", detail="a -> b", perform=boom)
    log = TransactionLog(tmp_path / "log.jsonl")
    report = execute([action], RecordingRunner(), log=log, plan=_plan())

    assert performed == ["tried"]
    assert not report.ok
    assert report.failed is action
    events = [e["event"] for e in log.read()]
    assert "action_begin" in events
    assert "transaction_failed" in events
    assert "transaction_end" not in events


def test_a_successful_action_records_its_outcome(tmp_path: Path) -> None:
    action = Action(
        kind="fetch",
        description="Fetch it",
        detail="url -> path",
        perform=lambda: "downloaded 12 bytes, sha256 abc… verified",
    )
    log = TransactionLog(tmp_path / "log.jsonl")
    execute([action], RecordingRunner(), log=log, plan=_plan(packages=()))

    end = next(e for e in log.read() if e["event"] == "action_end")
    assert "verified" in end["outcome"]


def test_a_bad_callsign_is_an_error_message_not_a_traceback(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """StationError from operator input gets the validator's message and the
    planning exit code. Found on the first Parrot VM run that passed
    --callsign N0CALL: the run ended in a raw traceback."""
    code = main(["install", "linbpq", "--dry-run", "--callsign", "N0CALL"])
    assert code == EXIT_UNPLANNABLE
    err = capsys.readouterr().err
    assert "does not look like a callsign" in err
    assert "Traceback" not in err


# ---------------------------------------------------------------------------
# Suggestion groups (Q-015 #1): detect, respect, offer, never block
# ---------------------------------------------------------------------------


def _suggesting_profile() -> Any:
    from hammunition.manifest.schema import ProfileManifest

    return ProfileManifest.model_validate(
        {
            "name": "suggestive",
            "summary": "Fixture profile with a mail-client suggestion",
            "packages": ["example"],
            "suggests_one_of": [
                {
                    "name": "mail-client",
                    "reason": "Winlink messages land in a mailbox and a human reads them there.",
                    "detect_commands": ["definitely-not-a-binary-xyz"],
                    "options": ["optiona", "optionb"],
                }
            ],
            "documentation": {
                "what_it_installs": "One fixture package, plus whatever gets chosen.",
                "why_together": "They exist to exercise the suggestion machinery.",
                "deliberately_excludes": "Everything real.",
                "manual_configuration": "Nothing at all.",
            },
        }
    )


def test_a_detected_command_is_respected_and_nothing_offered(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import shutil as shutil_module

    from hammunition.cli.main import _apply_suggestions

    monkeypatch.setattr(shutil_module, "which", lambda c: "/usr/bin/found")
    extra, notes = _apply_suggestions(
        ["suggestive"], {"suggestive": _suggesting_profile()}, assume_yes=False
    )
    assert extra == []
    assert any("already installed — respected" in n for n in notes)


def test_yes_skips_the_offer_with_a_note_never_blocking(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import shutil as shutil_module

    from hammunition.cli.main import _apply_suggestions

    monkeypatch.setattr(shutil_module, "which", lambda c: None)
    extra, notes = _apply_suggestions(
        ["suggestive"], {"suggestive": _suggesting_profile()}, assume_yes=True
    )
    assert extra == []
    assert any("skipped" in n and "optiona, optionb" in n for n in notes)


def test_an_interactive_choice_adds_the_chosen_option(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import builtins
    import shutil as shutil_module
    import sys as sys_module

    from hammunition.cli.main import _apply_suggestions

    main_module = sys_module.modules["hammunition.cli.main"]
    monkeypatch.setattr(shutil_module, "which", lambda c: None)
    monkeypatch.setattr(main_module, "is_interactive", lambda: True)
    monkeypatch.setattr(builtins, "input", lambda prompt="": "2")
    extra, notes = _apply_suggestions(
        ["suggestive"], {"suggestive": _suggesting_profile()}, assume_yes=False
    )
    assert extra == ["optionb"]
    assert any("you chose optionb" in n for n in notes)


def test_skip_is_always_an_answer(monkeypatch: pytest.MonkeyPatch) -> None:
    import builtins
    import shutil as shutil_module
    import sys as sys_module

    from hammunition.cli.main import _apply_suggestions

    main_module = sys_module.modules["hammunition.cli.main"]
    monkeypatch.setattr(shutil_module, "which", lambda c: None)
    monkeypatch.setattr(main_module, "is_interactive", lambda: True)
    monkeypatch.setattr(builtins, "input", lambda prompt="": "s")
    extra, notes = _apply_suggestions(
        ["suggestive"], {"suggestive": _suggesting_profile()}, assume_yes=False
    )
    assert extra == []
    assert any("skipped by choice" in n for n in notes)


def test_plan_state_says_will_build_for_a_source_unit_with_no_apt_work(tmp_path: Path) -> None:
    """ "already installed" is apt's answer and only apt's. A git unit whose
    apt list is empty (or whose build deps are all present) is about to be
    built, and the summary line must say so -- sdrangel's .deb block read
    "already installed" one line above its fetch and install (2026-09-02)."""
    plan = _built_plan(tmp_path)
    text = "\n".join(render_plan(plan, (), euid=1000))
    assert "builtish" in text
    assert "will build" in text
    assert "already installed" not in text


def test_main_line_buffers_stdout_so_a_redirected_install_log_is_not_empty_until_exit() -> None:
    """A whole-profile install redirected to a file showed 0 bytes for the
    forty minutes it ran (Kali VM, 2026-09-02). The `$ command` headers
    sat in Python's block buffer while the children wrote straight to the
    same descriptor -- an empty, then out-of-order, log. Proven with a real
    pipe rather than a mock: the child prints help and is read before it
    exits only if the write was flushed at the newline."""
    import subprocess

    script = (
        "import sys\n"
        "from hammunition.cli.main import main\n"
        # Bare `main([])` prints help and *returns*; --version would raise
        # SystemExit and flush at interpreter exit, proving nothing.
        "main([])\n"
        # Block until the parent has read the line; if the version line was
        # still buffered here, the parent's readline would hang instead.
        "sys.stdin.readline()\n"
    )
    proc = subprocess.Popen(
        [sys.executable, "-c", script],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        text=True,
    )
    try:
        assert proc.stdout is not None and proc.stdin is not None
        # A hung readline would fail the suite by timeout rather than assert;
        # so it is polled instead, and 5 s is a hundred times what it needs.
        import selectors

        selector = selectors.DefaultSelector()
        selector.register(proc.stdout, selectors.EVENT_READ)
        assert selector.select(timeout=5), "nothing arrived: stdout is block-buffered"
        assert proc.stdout.readline().startswith("usage:")
    finally:
        if proc.stdin is not None:
            proc.stdin.write("\n")
            proc.stdin.close()
        proc.wait(timeout=10)
