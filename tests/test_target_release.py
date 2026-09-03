# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""D-038: a transaction apt can resolve only from the release the target
already installs from is resolved from there, disclosed by name -- and one
it cannot resolve at all is refused before anything runs, with apt's words.

The transcripts are a clean Parrot 7.3 on 2026-09-02, where five of fifteen
profiles passed the plan and then failed at the apt step: `libcurl4t64` is
installed from `parrot-backports` at 8.21, and the archive's default
`libcurl4-openssl-dev` (8.14) depends on `libcurl4t64 (= 8.14)`.
"""

from __future__ import annotations

import shlex
from pathlib import Path
from typing import Any

import pytest

from hammunition.backends.base import CommandResult, RecordingRunner

PARROT_REFUSAL = """\
E: Unable to correct problems, you have held broken packages.
E: The following information from --solver 3.0 may provide additional context:
   Unable to satisfy dependencies. Reached two conflicting decisions:
   1. libcurl4t64:amd64=8.14.1-2+deb13u5 is not selected for install
   2. libcurl4t64:amd64=8.14.1-2+deb13u5 is selected as a downgrade because:
      1. libcurl4-openssl-dev:amd64=8.14.1-2+deb13u5 is selected for install
      2. libcurl4-openssl-dev:amd64=8.14.1-2+deb13u5 Depends libcurl4t64 (= 8.14.1-2+deb13u5)
"""

PARROT_POLICY_ALL = """\
Package files:
 100 /var/lib/dpkg/status
     release a=now
 599 https://deb.parrot.sh/parrot echo-backports/main amd64 Packages
     release o=Parrot,a=parrot-backports,n=echo-backports,l=Parrot 7 Echo Parakeet,c=main,b=amd64
     origin deb.parrot.sh
 600 https://deb.parrot.sh/parrot echo/main amd64 Packages
     release o=Parrot,a=parrot,n=echo,l=Parrot 7 Echo Parakeet,c=main,b=amd64
     origin deb.parrot.sh
Pinned packages:
"""

PARROT_POLICY_LIBCURL = """\
libcurl4t64:
  Installed: 8.21.0-2~bpo13+1
  Candidate: 8.21.0-2~bpo13+1
  Version table:
 *** 8.21.0-2~bpo13+1 599
        599 https://deb.parrot.sh/parrot echo-backports/main amd64 Packages
        100 /var/lib/dpkg/status
     8.14.1-2+deb13u5 600
        600 https://deb.parrot.sh/parrot echo/main amd64 Packages
"""

PARROT_BACKPORTS_SIMULATION = """\
NOTE: This is only a simulation!
Inst libnghttp3-dev (1.8.0-1~bpo13+1 Parrot 7 Echo Parakeet:parrot-backports [amd64])
Inst libcurl4-openssl-dev (8.21.0-2~bpo13+1 Parrot 7 Echo Parakeet:parrot-backports [amd64])
Inst libkrb5-dev (1.21.3-5+deb13u1 Parrot 7 Echo Parakeet:parrot, Parrot 7 Echo Parakeet:parrot-security [amd64])
Inst curl-unit (1.0-1 Parrot 7 Echo Parakeet:parrot [amd64])
Conf libcurl4-openssl-dev (8.21.0-2~bpo13+1 Parrot 7 Echo Parakeet:parrot-backports [amd64])
"""


def _ok(stdout: str) -> CommandResult:
    return CommandResult(argv=(), returncode=0, stdout=stdout, stderr="")


def _failed(stderr: str) -> CommandResult:
    return CommandResult(argv=(), returncode=100, stdout="Reading package lists...", stderr=stderr)


def _parrot_apt(tmp_path: Path, *, retry_succeeds: bool = True, culprit_known: bool = True) -> Any:
    """An apt whose default resolution refuses the way Parrot's did."""
    from test_plan import _apt

    apt = _apt(tmp_path, {"curl-unit": None, "libcurl4-openssl-dev": None})
    packages = "curl-unit libcurl4-openssl-dev"
    responses = {
        f"apt-get install --simulate --yes -- {packages}": _failed(PARROT_REFUSAL),
        f"apt-get install --simulate --yes --target-release parrot-backports -- {packages}": (
            _ok(PARROT_BACKPORTS_SIMULATION) if retry_succeeds else _failed(PARROT_REFUSAL)
        ),
        "apt-cache policy": _ok(PARROT_POLICY_ALL),
        "apt-cache policy -- libcurl4t64": _ok(PARROT_POLICY_LIBCURL if culprit_known else ""),
    }
    apt.runner = RecordingRunner(responses)
    return apt


def _resolve_curl_unit(tmp_path: Path, apt: Any) -> Any:
    from test_plan import _manifest, _resolve

    unit = _manifest(
        name="curl-unit",
        install=[
            {
                "install": {
                    "method": "apt",
                    "packages": ["libcurl4-openssl-dev", "curl-unit"],
                }
            }
        ],
    )
    return _resolve(tmp_path, ["curl-unit"], apt=apt, catalog={"curl-unit": unit})


def _argvs(apt: Any) -> list[str]:
    return [shlex.join(c.argv) for c in apt.runner.commands]


def test_the_refused_downgrade_names_the_installed_package() -> None:
    from hammunition.backends.apt import downgrades_refused

    assert downgrades_refused(PARROT_REFUSAL) == ["libcurl4t64"]
    assert downgrades_refused("E: Unable to locate package nosuch") == []


def test_the_installed_archive_is_read_from_the_version_table(tmp_path: Path) -> None:
    apt = _parrot_apt(tmp_path)
    assert apt.installed_archive("libcurl4t64") == "parrot-backports"
    assert apt.installed_archive("nosuch") is None


def test_a_downgrade_refusal_is_retried_from_the_installed_release_and_disclosed(
    tmp_path: Path,
) -> None:
    apt = _parrot_apt(tmp_path)
    plan = _resolve_curl_unit(tmp_path, apt)
    assert plan.apt_release == "parrot-backports"
    # Only what comes from backports and nowhere else: libkrb5-dev is offered
    # by main and security at the same version and is not backports' doing.
    assert plan.apt_from_release == ("libcurl4-openssl-dev", "libnghttp3-dev")
    argvs = _argvs(apt)
    assert argvs.count("apt-cache policy -- libcurl4t64") == 1
    assert sum("--target-release parrot-backports" in a for a in argvs) == 1


def test_the_apt_step_then_carries_the_target_release(tmp_path: Path) -> None:
    """The plan's answer reaches the command that runs, and the operator sees
    it in the printed argv before it does."""
    from hammunition.backends.base import Command
    from hammunition.execute import commands_for

    apt = _parrot_apt(tmp_path)
    plan = _resolve_curl_unit(tmp_path, apt)
    steps = commands_for(plan, apt=apt, refresh=False)
    installs = [s for s in steps if isinstance(s, Command) and s.argv[:2] == ("apt-get", "install")]
    assert len(installs) == 1
    argv = installs[0].argv
    assert argv[: argv.index("--")] == (
        "apt-get",
        "install",
        "--yes",
        "--target-release",
        "parrot-backports",
    )
    assert "from parrot-backports" in installs[0].description


def test_a_transaction_that_resolves_by_default_carries_no_target_release(
    tmp_path: Path,
) -> None:
    from test_plan import _apt, _resolve

    apt = _apt(tmp_path, {"example": None})
    plan = _resolve(tmp_path, ["example"], apt=apt)
    assert plan.apt_release is None
    assert plan.apt_from_release == ()


def test_a_refusal_the_retry_does_not_cure_blocks_with_apts_own_words(tmp_path: Path) -> None:
    from hammunition.plan import PlanError

    apt = _parrot_apt(tmp_path, retry_succeeds=False)
    with pytest.raises(PlanError) as excinfo:
        _resolve_curl_unit(tmp_path, apt)
    text = str(excinfo.value)
    assert "apt: cannot resolve this transaction as one apt-get install" in text
    assert "is selected as a downgrade" in text
    assert "apt-get install --simulate" in text


def test_a_refusal_naming_no_installed_release_is_not_guessed_at(tmp_path: Path) -> None:
    """The culprit's origin cannot be read: nothing is tried, the refusal
    stands. `-t` for a release the machine does not install from would be
    the guess this rule exists to refuse."""
    from hammunition.plan import PlanError

    apt = _parrot_apt(tmp_path, culprit_known=False)
    with pytest.raises(PlanError):
        _resolve_curl_unit(tmp_path, apt)
    assert not [a for a in _argvs(apt) if "--target-release" in a]


def test_the_plan_prints_what_comes_from_the_release(tmp_path: Path) -> None:
    from hammunition.cli.main import render_plan

    apt = _parrot_apt(tmp_path)
    plan = _resolve_curl_unit(tmp_path, apt)
    text = "\n".join(render_plan(plan, [], euid=1000))
    assert "parrot-backports" in text
    assert "libcurl4-openssl-dev" in text
    assert "libnghttp3-dev" in text
    assert "D-038" in text
