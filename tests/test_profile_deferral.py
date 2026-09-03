# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""Q-017: a profile member the *target* does not offer is deferred by name and
the rest of the profile installs. Everything else still refuses (D-016).

The line is drawn at "true of the target, not of the operator or the engine":
no apt candidate on this release for the unit's own packages, no install
block for this distro/arch, a Node floor the distribution's package is below.
An engine gap (a backend that does not exist), a missing build dependency, a
retired unit, or a member the operator asked for *by name* are all still
blockers -- deferral that swallowed those would make them invisible.

Measured on Ubuntu 24.04 (2026-09-02): `listening` withheld nineteen
installable units over four the archive does not carry.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from hammunition.backends.apt import AptPackageState
from hammunition.plan import PlanError
from test_plan import TARGET, _apt, _manifest, _profile, _resolve


def _unit(name: str, **overrides: Any) -> Any:
    return _manifest(
        name=name, install=[{"install": {"method": "apt", "packages": [name]}}], **overrides
    )


def _catalog(*units: Any) -> dict[str, Any]:
    return {u.name: u for u in units}


def _deferred_names(plan: Any) -> list[str]:
    return [d.subject for d in plan.deferrals if d.kind == "package"]


# ---------------------------------------------------------------------------
# The rule
# ---------------------------------------------------------------------------


def test_a_profile_member_without_a_candidate_is_deferred_and_the_rest_installs(
    tmp_path: Path,
) -> None:
    catalog = _catalog(_unit("present"), _unit("absent"))
    profile = _profile(name="listening", packages=["present", "absent"])
    plan = _resolve(
        tmp_path,
        ["listening"],
        catalog=catalog,
        profiles={"listening": profile},
        known={"present": None},
    )
    assert [p.name for p in plan.packages] == ["present"]
    assert plan.apt_to_install == ("present",)
    assert _deferred_names(plan) == ["absent"]
    (deferral,) = plan.deferrals
    assert "no candidate" in deferral.why
    assert "debian 13" in deferral.why.lower()
    assert "listening" in deferral.what


def test_the_same_member_requested_by_name_is_still_refused(tmp_path: Path) -> None:
    """Nothing is hidden: asking for the unit itself gets the refusal in full."""
    catalog = _catalog(_unit("absent"))
    with pytest.raises(PlanError) as excinfo:
        _resolve(tmp_path, ["absent"], catalog=catalog, known={})
    assert "apt has no candidate for absent" in str(excinfo.value)


def test_requested_by_name_and_by_profile_is_refused_not_deferred(tmp_path: Path) -> None:
    catalog = _catalog(_unit("present"), _unit("absent"))
    profile = _profile(name="listening", packages=["present", "absent"])
    with pytest.raises(PlanError):
        _resolve(
            tmp_path,
            ["listening", "absent"],
            catalog=catalog,
            profiles={"listening": profile},
            known={"present": None},
        )


def test_a_profile_with_every_member_deferred_is_refused_naming_the_profile(
    tmp_path: Path,
) -> None:
    """Deferring everything is refusing with a happier face. Say so."""
    catalog = _catalog(_unit("absent"), _unit("gone"))
    profile = _profile(name="satellite", packages=["absent", "gone"])
    with pytest.raises(PlanError) as excinfo:
        _resolve(
            tmp_path, ["satellite"], catalog=catalog, profiles={"satellite": profile}, known={}
        )
    text = str(excinfo.value)
    assert "satellite" in text
    assert "no member" in text or "every member" in text


# ---------------------------------------------------------------------------
# Which gaps count as the target's
# ---------------------------------------------------------------------------


def test_no_install_block_for_this_target_is_a_deferral(tmp_path: Path) -> None:
    other = _manifest(
        name="elsewhere",
        install=[
            {
                "when": {"distro": ["ubuntu"]},
                "install": {"method": "apt", "packages": ["elsewhere"]},
            }
        ],
    )
    catalog = _catalog(_unit("present"), other)
    profile = _profile(name="p", packages=["present", "elsewhere"])
    plan = _resolve(
        tmp_path, ["p"], catalog=catalog, profiles={"p": profile}, known={"present": None}
    )
    assert [p.name for p in plan.packages] == ["present"]
    assert _deferred_names(plan) == ["elsewhere"]
    assert "no install block" in plan.deferrals[0].why


def test_a_node_floor_the_distribution_is_below_is_a_deferral(tmp_path: Path) -> None:
    from test_node_backend import manifest as node_manifest

    node = node_manifest()
    catalog = _catalog(_unit("present"), node)
    profile = _profile(name="propagation", packages=["present", "nodeunit"])

    apt = _apt(tmp_path, {"present": None, "npm": None})
    real_probe = apt.probe

    def probe(packages: Any) -> Any:
        states = real_probe(packages)
        if "nodejs" in packages:
            states["nodejs"] = AptPackageState("nodejs", installed=None, candidate="18.19.1+dfsg-6")
        return states

    apt.probe = probe  # type: ignore[method-assign]
    plan = _resolve(
        tmp_path, ["propagation"], catalog=catalog, profiles={"propagation": profile}, apt=apt
    )
    assert [p.name for p in plan.packages] == ["present"]
    assert _deferred_names(plan) == ["nodeunit"]
    assert "18.19" in plan.deferrals[0].why
    # The deferred unit's tool dependencies do not ride along.
    assert plan.apt_to_install == ("present",)


def test_a_dependent_of_a_deferred_member_is_deferred_with_it(tmp_path: Path) -> None:
    """pythonprop depends on voacapl; 24.04 carries neither. Both defer, and
    the dependent says why."""
    catalog = _catalog(_unit("present"), _unit("voacapl"), _unit("pythonprop", depends=["voacapl"]))
    profile = _profile(name="propagation", packages=["present", "voacapl", "pythonprop"])
    plan = _resolve(
        tmp_path,
        ["propagation"],
        catalog=catalog,
        profiles={"propagation": profile},
        known={"present": None, "pythonprop": None},
    )
    assert [p.name for p in plan.packages] == ["present"]
    assert sorted(_deferred_names(plan)) == ["pythonprop", "voacapl"]
    dependent = next(d for d in plan.deferrals if d.subject == "pythonprop")
    assert "voacapl" in dependent.why


def test_a_named_request_whose_catalog_dependency_is_unavailable_is_refused(
    tmp_path: Path,
) -> None:
    catalog = _catalog(_unit("voacapl"), _unit("pythonprop", depends=["voacapl"]))
    with pytest.raises(PlanError) as excinfo:
        _resolve(tmp_path, ["pythonprop"], catalog=catalog, known={"pythonprop": None})
    assert "voacapl" in str(excinfo.value)


# ---------------------------------------------------------------------------
# What is NOT the target's gap, and still blocks
# ---------------------------------------------------------------------------


def test_an_engine_gap_still_blocks_the_profile(tmp_path: Path) -> None:
    """A member refused for what the *engine* cannot do is not a target gap
    and is never deferred. Planning without a repository backend is the
    fixture for it now that D-040 exists (`tests/test_apt_repos.py` covers
    the planned case); the shape holds for any engine-side refusal."""
    code = _unit(
        "code",
        apt_repos=[
            {
                "name": "vscode",
                "uri": "https://packages.example.invalid/repos/code",
                "suites": ["stable"],
                "components": ["main"],
                "key_url": "https://packages.example.invalid/keys/example.asc",
                "key_fingerprint": "0123456789ABCDEF0123456789ABCDEF01234567",
                "rationale": "The editor is published only from the vendor's own repository, which this fixture stands in for.",
            }
        ],
    )
    catalog = _catalog(_unit("present"), code)
    profile = _profile(name="workstation", packages=["present", "code"])
    with pytest.raises(PlanError) as excinfo:
        _resolve(
            tmp_path,
            ["workstation"],
            catalog=catalog,
            profiles={"workstation": profile},
            known={"present": None, "code": None},
        )
    assert "third-party apt repositories" in str(excinfo.value)


def test_a_missing_build_dependency_still_blocks(tmp_path: Path) -> None:
    """A build dependency apt cannot find is a manifest defect, not a target gap."""
    built = _manifest(
        name="built",
        install=[
            {
                "install": {
                    "method": "source",
                    "source": {
                        "url": "https://example.invalid/built-1.0.tar.gz",
                        "sha256": "0" * 64,
                    },
                    "build_system": "make",
                },
                "build_depends": ["libfftw2-dev"],
            }
        ],
        binaries=[{"produced": "built", "install_as": "built"}],
    )
    catalog = _catalog(_unit("present"), built)
    profile = _profile(name="p", packages=["present", "built"])
    with pytest.raises(PlanError) as excinfo:
        _resolve(tmp_path, ["p"], catalog=catalog, profiles={"p": profile}, known={"present": None})
    assert "libfftw2-dev (build_depends)" in str(excinfo.value)


def test_a_retired_member_still_blocks(tmp_path: Path) -> None:
    dead = _unit(
        "dead",
        status="retired",
        status_reason="gone",
        status_date="2026-01-01",
        status_verdict="tested",
        retire_reason="world_changed",
    )
    catalog = _catalog(_unit("present"), dead)
    profile = _profile(name="p", packages=["present", "dead"])
    with pytest.raises(PlanError):
        _resolve(
            tmp_path,
            ["p"],
            catalog=catalog,
            profiles={"p": profile},
            known={"present": None, "dead": None},
        )


# ---------------------------------------------------------------------------
# It is reported: plan, log, status
# ---------------------------------------------------------------------------


def test_the_plan_prints_the_deferred_member_under_will_not_happen(tmp_path: Path) -> None:
    from hammunition.cli.main import render_plan

    catalog = _catalog(_unit("present"), _unit("absent"))
    profile = _profile(name="listening", packages=["present", "absent"])
    plan = _resolve(
        tmp_path,
        ["listening"],
        catalog=catalog,
        profiles={"listening": profile},
        known={"present": None},
    )
    text = "\n".join(render_plan(plan, [], euid=1000))
    assert "Will NOT happen" in text
    assert "absent: " in text
    assert "no candidate" in text


def test_the_transaction_log_records_the_deferral(tmp_path: Path) -> None:
    from hammunition.execute import commands_for, execute
    from hammunition.state.log import TransactionLog

    catalog = _catalog(_unit("present"), _unit("absent"))
    profile = _profile(name="listening", packages=["present", "absent"])
    apt = _apt(tmp_path, {"present": None})
    plan = _resolve(
        tmp_path, ["listening"], catalog=catalog, profiles={"listening": profile}, apt=apt
    )
    log = TransactionLog(tmp_path / "t.jsonl")
    execute(commands_for(plan, apt=apt, refresh=False), apt.runner, log=log, plan=plan)
    begin = next(e for e in log.read() if e["event"] == "transaction_begin")
    assert begin["deferred"] == [
        {
            "kind": "package",
            "subject": "absent",
            "what": plan.deferrals[0].what,
            "why": plan.deferrals[0].why,
        }
    ]


def test_status_reports_what_the_last_transaction_deferred(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    import argparse

    from hammunition.cli.main import cmd_status
    from hammunition.distro import Target
    from hammunition.state import TransactionLog, log_path

    monkeypatch.setattr(Target, "detect", classmethod(lambda cls: TARGET))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    monkeypatch.delenv("SUDO_USER", raising=False)
    monkeypatch.setenv("USER", "root")  # operator() -> "root": falsy owner, XDG path
    log = TransactionLog(log_path())
    log.append(
        {
            "event": "transaction_begin",
            "version": 2,
            "packages": ["present"],
            "apt_packages": ["present"],
            "deferred": [
                {
                    "kind": "package",
                    "subject": "absent",
                    "what": "will not be installed (profile listening)",
                    "why": "apt on Debian 13 has no candidate for absent",
                }
            ],
        }
    )
    log.append({"event": "transaction_end", "version": 2, "completed": 1})
    rc = cmd_status(argparse.Namespace(catalog=None, user=None))
    out = capsys.readouterr().out
    assert rc == 0
    assert "deferred" in out.lower()
    assert "absent" in out
    assert "no candidate" in out
