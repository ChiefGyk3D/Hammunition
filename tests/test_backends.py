# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""The apt backend, and the properties the command types are supposed to carry.

Two apt behaviours have their own tests because both look like "the package
does not exist" and neither is: `apt-cache policy` exits 0 for a package it has
never heard of, and a machine with no package lists reports every package as
unknown. Getting either wrong turns a fixable situation into a confident lie.
"""

from __future__ import annotations

import shlex
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from pydantic import ValidationError  # noqa: E402

from hammunition.backends import (  # noqa: E402
    AptBackend,
    BackendError,
    Command,
    CommandResult,
    RecordingRunner,
    parse_policy,
)
from hammunition.cli.main import load_all  # noqa: E402
from hammunition.manifest.schema import AptInstall, ManifestError  # noqa: E402

POLICY = """\
rtl-sdr:
  Installed: (none)
  Candidate: 2.0.1-1
  Version table:
     2.0.1-1 500
        500 http://deb.debian.org/debian trixie/main amd64 Packages
tcpdump:
  Installed: 4.99.5-2
  Candidate: 4.99.5-2
  Version table:
 *** 4.99.5-2 500
"""

# A package apt knows of but has no installable version for — the shape a
# package removed from the archive but still referenced by another leaves.
NO_CANDIDATE = """\
ghost-package:
  Installed: (none)
  Candidate: (none)
  Version table:
"""


def _apt(tmp_path: Path, stdout: str, *, populated: bool = True) -> AptBackend:
    lists = tmp_path / ("lists-populated" if populated else "lists-empty")
    lists.mkdir(exist_ok=True)
    if populated:
        (lists / "deb.debian.org_debian_dists_trixie_main_binary-amd64_Packages").touch()
    runner = _StrictRunner()
    backend = AptBackend(runner, lists_dir=lists)
    # Scripted by argv, so the test asserts the backend asked the right question.
    runner.responses = {
        key: CommandResult(argv=(), returncode=0, stdout=stdout, stderr="")
        for key in _policy_keys(stdout)
    }
    return backend


class _StrictRunner(RecordingRunner):
    """A runner that refuses a command it has no script for.

    RecordingRunner's tolerant default -- empty success for anything -- is
    right for --dry-run and wrong for this fixture: when the backend grew the
    `--` guard, every scripted key stopped matching and probe() started
    returning {} while all the tests stayed green, because the canned POLICY
    text was simply never consumed. The exact failure CLAUDE.md's standing
    rule describes, in the suite written under that rule. A fixture whose
    responses can silently go unused is not a fixture, it is a hope.
    """

    def run(self, command: Command) -> CommandResult:
        key = shlex.join(command.argv)
        if key not in self.responses:
            raise AssertionError(f"unscripted command: {key!r}. Scripted: {sorted(self.responses)}")
        return super().run(command)


def _policy_keys(stdout: str) -> list[str]:
    names = [line.rstrip(":") for line in stdout.splitlines() if line and not line[0].isspace()]
    return ["apt-cache policy -- " + " ".join(names)]


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------


def test_none_becomes_none_not_the_string() -> None:
    """`"(none)"` is truthy. Carrying it around is how a not-installed package
    reads as installed."""
    states = parse_policy(POLICY)
    assert states["rtl-sdr"].installed is None
    assert states["rtl-sdr"].is_installed is False
    assert states["tcpdump"].installed == "4.99.5-2"
    assert states["tcpdump"].is_installed is True


def test_candidate_is_parsed_and_known_follows_it() -> None:
    states = parse_policy(POLICY)
    assert states["rtl-sdr"].candidate == "2.0.1-1"
    assert states["rtl-sdr"].known is True


def test_a_package_with_no_candidate_is_not_known() -> None:
    assert parse_policy(NO_CANDIDATE)["ghost-package"].known is False


def test_an_unknown_package_produces_no_stanza_at_all() -> None:
    """This is why absence, not exit status, is the test for existence."""
    assert "nosuchpkg" not in parse_policy(POLICY)


def test_multiple_stanzas_do_not_bleed_into_each_other() -> None:
    states = parse_policy(POLICY)
    assert set(states) == {"rtl-sdr", "tcpdump"}
    assert states["rtl-sdr"].installed is None


# ---------------------------------------------------------------------------
# Resolution
# ---------------------------------------------------------------------------


def test_probe_asks_apt_once_for_the_whole_set(tmp_path: Path) -> None:
    apt = _apt(tmp_path, POLICY)
    apt.probe(["rtl-sdr", "tcpdump"])
    runner = apt.runner
    assert isinstance(runner, RecordingRunner)
    assert len(runner.commands) == 1
    # `--` before the names: a package name cannot be an option, and the schema
    # already refuses one that looks like it. Both, because the failure is silent.
    assert runner.commands[0].argv == ("apt-cache", "policy", "--", "rtl-sdr", "tcpdump")


def test_probing_never_asks_for_privilege(tmp_path: Path) -> None:
    """A dry run has to work without sudo, so resolution must be unprivileged."""
    apt = _apt(tmp_path, POLICY)
    # Both names: the fixture scripts the exact argv, and asking for a subset
    # was previously answered by RecordingRunner's tolerant empty default --
    # this test never consumed POLICY at all until the runner became strict.
    apt.probe(["rtl-sdr", "tcpdump"])
    runner = apt.runner
    assert isinstance(runner, RecordingRunner)
    assert runner.commands[0].requires_root is False


def test_a_broken_apt_is_fatal_rather_than_an_empty_answer(tmp_path: Path) -> None:
    """Silently treating a failed probe as 'nothing exists' is the D-016 defect."""
    runner = RecordingRunner(
        {
            "apt-cache policy -- rtl-sdr": CommandResult(
                argv=(), returncode=100, stdout="", stderr="boom"
            )
        }
    )
    lists = tmp_path / "lists"
    lists.mkdir()
    with pytest.raises(BackendError, match="apt-cache policy failed"):
        AptBackend(runner, lists_dir=lists).probe(["rtl-sdr"])


def test_empty_lists_are_detectable(tmp_path: Path) -> None:
    """A fresh image has no lists and reports every package unknown."""
    assert _apt(tmp_path, POLICY, populated=False).lists_populated() is False
    assert _apt(tmp_path, POLICY, populated=True).lists_populated() is True


def test_a_missing_lists_directory_is_not_an_exception(tmp_path: Path) -> None:
    assert AptBackend(RecordingRunner(), lists_dir=tmp_path / "absent").lists_populated() is False


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


def test_installation_is_one_transaction_deduplicated_and_ordered() -> None:
    """One apt-get, so apt resolves the dependency set once and any conflict is
    reported before anything is unpacked."""
    commands = AptBackend(RecordingRunner()).install_commands(["tcpdump", "rtl-sdr", "tcpdump"])
    assert len(commands) == 1
    assert commands[0].argv == ("apt-get", "install", "--yes", "--", "rtl-sdr", "tcpdump")


def test_installing_nothing_produces_no_command() -> None:
    assert AptBackend(RecordingRunner()).install_commands([]) == []


def test_apt_never_opens_a_dialogue() -> None:
    """A blocked debconf prompt nobody can see is indistinguishable from a hang."""
    command = AptBackend(RecordingRunner()).install_commands(["a"])[0]
    assert command.env["DEBIAN_FRONTEND"] == "noninteractive"


def test_recommends_are_not_suppressed() -> None:
    """Deviating from what every target distribution does by default would be a
    silent behaviour change applied to the whole catalog. D-019 is a catalog
    membership question, settled in the catalog."""
    command = AptBackend(RecordingRunner()).install_commands(["a"])[0]
    assert "--no-install-recommends" not in command.argv


# ---------------------------------------------------------------------------
# Privilege, which the type carries rather than the call site
# ---------------------------------------------------------------------------


def test_sudo_is_added_only_when_root_is_needed_and_absent() -> None:
    privileged = Command(argv=("apt-get", "install"), description="x", requires_root=True)
    plain = Command(argv=("apt-cache", "policy"), description="x")

    assert privileged.argv_for(euid=1000)[0] == "sudo"
    assert privileged.argv_for(euid=0)[0] == "apt-get"
    assert plain.argv_for(euid=1000)[0] == "apt-cache"


def test_being_root_does_not_clear_the_requirement() -> None:
    """`requires_root` is a fact about the command, not about who is running it."""
    command = Command(argv=("apt-get",), description="x", requires_root=True)
    command.argv_for(euid=0)
    assert command.requires_root is True


def test_display_shows_exactly_what_will_run() -> None:
    """The operator's transcript, the log, and the process table must agree."""
    command = Command(
        argv=("apt-get", "install", "--yes", "a b"),
        description="x",
        requires_root=True,
        env={"DEBIAN_FRONTEND": "noninteractive"},
    )
    rendered = command.display(euid=1000)
    assert rendered.startswith("sudo env DEBIAN_FRONTEND=noninteractive apt-get install --yes ")
    assert "'a b'" in rendered, "a shell-unsafe argument must be quoted in the display"


def test_env_rides_inside_the_sudo_boundary() -> None:
    """Default sudoers has env_reset and DEBIAN_FRONTEND is not in env_keep,
    so a variable merged into the *parent* environment dies at the sudo
    boundary and apt runs interactive -- a debconf question opens a prompt
    that capture_output has swallowed, and the run hangs with nothing on
    screen. The variable has to be argv, inside the escalation:
    `sudo env DEBIAN_FRONTEND=noninteractive apt-get ...`."""
    command = Command(
        argv=("apt-get", "install", "--yes", "--", "wireshark"),
        description="x",
        requires_root=True,
        env={"DEBIAN_FRONTEND": "noninteractive"},
    )
    escalated = command.argv_for(euid=1000)
    assert escalated[:3] == ("sudo", "env", "DEBIAN_FRONTEND=noninteractive")
    assert escalated[3:] == command.argv
    # Running as root there is no boundary to cross; the process env carries it.
    assert command.argv_for(euid=0) == command.argv
    assert command.display(euid=0).startswith("DEBIAN_FRONTEND=noninteractive apt-get ")
    # And the display agrees with the escalated argv exactly.
    assert command.display(euid=1000).split(" -- ")[0] == (
        "sudo env DEBIAN_FRONTEND=noninteractive apt-get install --yes"
    )


# ---------------------------------------------------------------------------
# A package name is a package name
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "name",
    [
        "-o",
        "--reinstall",
        "APT::Get::AllowUnauthenticated=true",
        "a",  # Debian policy 5.6.1: at least two characters
        "Wireshark",  # and lower case only
        "rtl sdr",
        "../etc/passwd",
    ],
)
def test_a_manifest_cannot_smuggle_an_apt_option_as_a_package(name: str) -> None:
    """These strings become argv for a root-privileged apt-get.

    D-009 opens the catalog to community and local tiers, so manifests will
    arrive from people this project has not met. The pre-flight probe happens
    to catch the option-shaped ones — apt-cache consumes them and returns no
    stanza, so "asked for, not returned" reports them unobtainable — but that
    is an incidental property of one code path rather than an invariant, and
    this project's posture elsewhere is to make the bad state unrepresentable.
    """
    with pytest.raises((ManifestError, ValidationError)):
        AptInstall(packages=[name])


@pytest.mark.parametrize("name", ["rtl-sdr", "libhamlib4", "gcc-14", "libc6:i386", "g++"])
def test_real_package_names_are_accepted(name: str) -> None:
    assert AptInstall(packages=[name]).packages == [name]


def test_the_whole_catalog_passes_the_package_name_rule() -> None:
    """Not a hypothetical: if this ever fails, a real manifest is wrong."""
    packages, _ = load_all(Path(__file__).resolve().parent.parent / "catalog")
    assert packages


# ---------------------------------------------------------------------------
# The probe pipeline, end to end through the fixture
# ---------------------------------------------------------------------------


def test_probe_actually_consumes_the_scripted_policy_text(tmp_path: Path) -> None:
    """The whole probe -> parse pipeline, through the same argv the backend
    really emits. This is the test that was missing when the fixture died:
    it goes red if the backend's argv and the fixture's keys ever drift
    apart again, instead of probe() quietly returning {}."""
    states = _apt(tmp_path, POLICY).probe(["rtl-sdr", "tcpdump"])
    assert states["rtl-sdr"].known is True
    assert states["rtl-sdr"].is_installed is False
    assert states["tcpdump"].installed == "4.99.5-2"
