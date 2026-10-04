# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""The Reticulum units: `rns`, `lxmf` and `nomadnet`.  Track C, D-080.

Three hash-pinned venvs from PyPI, because no archive on any target carries
any of it (docs/reference/mesh-inventory.md, 2026-10-03). What these tests
hold is what an operator meets: the pins are real and complete, the licence is
said on the plan line, the shared instance is one service the engine renders,
and uninstall never touches the identity and configuration that are the
operator's.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from hammunition.backends import Command, VenvBackend
from hammunition.execute import _user_unit_path, user_service_removal_steps
from hammunition.manifest.load import load_catalog
from hammunition.manifest.schema import PackageManifest, VenvInstall
from hammunition.station import Station
from hammunition.userservice import header_for, plan_user_services

ROOT = Path(__file__).resolve().parent.parent
CATALOG = ROOT / "catalog" / "packages"
VENV = Path("/home/op/.local/share/hammunition/venvs/rns")


def _unit(name: str) -> PackageManifest:
    return load_catalog(CATALOG)[name]


def _venv(name: str) -> VenvInstall:
    (block,) = _unit(name).install
    assert isinstance(block.install, VenvInstall)
    return block.install


def pinned(unit: str, project: str) -> str:
    """The version `unit` pins `project` to, read from its requirement lines."""
    for line in _venv(unit).requirements:
        match = re.match(rf"{re.escape(project)}==(\S+)", line)
        if match:
            return match.group(1)
    raise AssertionError(f"{unit} does not pin {project}")


def pinned_projects(unit: str) -> set[str]:
    """Every project `unit`'s venv pins: the whole closure, nothing left to float."""
    names: set[str] = set()
    for line in _venv(unit).requirements:
        match = re.match(r"([A-Za-z0-9_.-]+)==", line)
        assert match, f"not a pinned requirement: {line[:40]}"
        names.add(match.group(1))
    return names


def hash_count(unit: str) -> int:
    return sum(line.count("--hash=sha256:") for line in _venv(unit).requirements)


# -- rns ---------------------------------------------------------------------


def test_rns_is_one_complete_hash_pinned_venv() -> None:
    block = _venv("rns")
    assert block.python == ">=3.11"
    assert pinned_projects("rns") == {"cffi", "cryptography", "pycparser", "pyserial", "rns"}
    assert pinned("rns", "rns") == "1.5.6" and _unit("rns").version == "1.5.6"
    for line in block.requirements:
        assert line.count("--hash=sha256:") >= 1, f"unhashed: {line[:40]}"
    # The inventory counted 165 hashes for this closure; fewer means a pin lost
    # files PyPI lists, and an arm64 or Python 3.14 target stops verifying.
    assert hash_count("rns") == 165


def test_rns_exposes_every_script_rns_declares_and_none_of_a_dependencys() -> None:
    assert _venv("rns").expose == [
        "rnsd",
        "rnstatus",
        "rnpath",
        "rnprobe",
        "rnid",
        "rncp",
        "rnx",
        "rnsh",
        "rnodeconf",
        "rnir",
        "rnpkg",
        "rngit",
        "rngcs",
        "git-remote-rns",
    ]


def test_there_is_no_separate_rnsh_unit() -> None:
    """`rns` 1.5.x installs its own `rnsh`; PyPI's `rnsh` 0.1.7 would be a second
    owner of the same command name (inventory, 2026-10-03)."""
    assert "rnsh" not in load_catalog(CATALOG)


def test_the_licence_is_on_the_plan_line_before_the_confirmation(tmp_path: Path) -> None:
    block = _venv("rns")
    assert block.licence is not None and block.licence.startswith("Reticulum License")
    assert block.licence_url == "https://github.com/markqvist/Reticulum/blob/master/LICENSE"
    backend = VenvBackend(venv_root=tmp_path / "venvs", bin_dir=tmp_path / "bin")
    pip = [
        s
        for s in backend.steps(_unit("rns"), block)
        if isinstance(s, Command) and "--require-hashes" in s.argv
    ]
    assert len(pip) == 1 and "licence: Reticulum License" in pip[0].description


def test_the_shared_instance_is_one_plain_user_service() -> None:
    (svc,) = _unit("rns").user_services
    assert svc.name == "hammunition-rnsd"
    assert svc.exec == ["{venv}/bin/rnsd", "--service"]
    assert svc.restart == "on-failure"
    assert svc.is_plain  # no station value: Reticulum needs none, so nothing defers (D-035)
    # Not a TCP port: measured 2026-10-03, rnsd binds abstract Unix sockets
    # (@rns/default and @rns/default/rpc) and no TCP port. A `listens` entry would
    # print a loopback listener the plan does not have.
    assert svc.listens == []
    # A second rnsd does not exit, it attaches to the first (measured), so there
    # is no exit status to refuse a restart on.
    assert svc.restart_prevent_exit_status == []


def test_the_unit_file_runs_the_operators_venv_and_cannot_loop_forever() -> None:
    planned, deferrals, notes = plan_user_services(_unit("rns"), Station(), None, venv_dir=VENV)
    assert not deferrals and not notes
    (svc,) = planned
    assert svc.unit == "rns"
    assert svc.unit_body.startswith(header_for("rns"))
    assert f"ExecStart={VENV}/bin/rnsd --service\n" in svc.unit_body
    assert "Restart=on-failure" in svc.unit_body
    # A start limit bounds a crash loop: five tries in thirty seconds, then stop.
    assert "StartLimitIntervalSec=30" in svc.unit_body and "StartLimitBurst=5" in svc.unit_body
    assert "RestartPreventExitStatus" not in svc.unit_body


def test_uninstall_takes_the_service_and_never_the_operators_identity(tmp_path: Path) -> None:
    """~/.reticulum holds the operator's identity, interfaces and known destinations.
    The engine did not write them and does not remove them (D-080)."""
    unit = _unit("rns")
    assert unit.config_files == [] and unit.system_modifications == []
    path = _user_unit_path(tmp_path, "hammunition-rnsd")
    path.parent.mkdir(parents=True)
    path.write_text(header_for("rns") + "\n[Service]\nExecStart=/x\n")
    steps = user_service_removal_steps(["hammunition-rnsd"], home=tmp_path, units=["rns"])
    assert steps, "an installed service must be stopped and removed"
    text = " ".join(
        " ".join(
            [
                getattr(s, "description", ""),
                getattr(s, "detail", ""),
                " ".join(getattr(s, "argv", ())),
            ]
        )
        for s in steps
    ).lower()
    assert "hammunition-rnsd" in text
    assert ".reticulum" not in text and ".nomadnetwork" not in text


def test_the_page_says_what_an_operator_will_hit() -> None:
    docs = _unit("rns").documentation
    assert docs.known_problems is not None
    for phrase in (
        "not an OSI licence",
        "~/.reticulum/logfile",
        "starts at your next login",
        "connected to another shared local instance",
        "leaves `~/.reticulum` in place",
    ):
        assert phrase in docs.known_problems, phrase


@pytest.mark.parametrize("unit", ["rns"])
def test_the_unit_is_a_mesh_unit_and_updates_from_pypi(unit: str) -> None:
    manifest = _unit(unit)
    assert manifest.categories == ["mesh"]
    assert manifest.update.probe.method == "pypi"
    assert manifest.depends == ["python3-venv"]


# -- lxmf --------------------------------------------------------------------


def test_lxmf_is_a_complete_hash_pinned_venv_exposing_lxmd() -> None:
    block = _venv("lxmf")
    assert block.python == ">=3.11" and block.expose == ["lxmd"]
    assert pinned_projects("lxmf") == {
        "cffi",
        "cryptography",
        "lxmf",
        "pycparser",
        "pyserial",
        "rns",
    }
    assert pinned("lxmf", "lxmf") == "1.2.0" and _unit("lxmf").version == "1.2.0"
    assert hash_count("lxmf") == 167
    assert block.licence is not None and block.licence.startswith("Reticulum License")
    assert block.licence_url == "https://github.com/markqvist/LXMF/blob/master/LICENSE"


def test_lxmd_is_not_a_service() -> None:
    """A propagation node stores other people's messages; running one is the
    operator's decision, made in the guide, never an install default."""
    unit = _unit("lxmf")
    assert unit.user_services == [] and unit.launchers == []
    assert unit.config_files == [] and unit.system_modifications == []


def test_the_lxmf_page_says_where_the_identity_lives_and_that_uninstall_keeps_it() -> None:
    docs = _unit("lxmf").documentation
    assert docs.known_problems is not None
    assert "~/.lxmd" in docs.known_problems and "leaves in place" in docs.known_problems
    assert "propagation node" in docs.known_problems


INVENTORY = ROOT / "docs" / "reference" / "mesh-venv-closures.txt"


def inventory_rns() -> str:
    """The `rns` version the closures inventory resolved every unit against."""
    match = re.search(r"^######## rns==(\S+)$", INVENTORY.read_text(), re.MULTILINE)
    assert match, "the inventory has no `rns==` section"
    return match.group(1)


@pytest.mark.parametrize("unit", ["lxmf", "nomadnet"])
def test_every_reticulum_venv_pins_the_same_rns(unit: str) -> None:
    """Each unit is its own venv with its own copy of `rns`, and the one that runs
    the shared instance must be the version every client was built against.
    Bump all three units in one commit (`rns`'s cadence_hint says how)."""
    assert pinned("rns", "rns") == inventory_rns()
    assert pinned(unit, "rns") == inventory_rns(), (
        f"{unit} pins rns {pinned(unit, 'rns')} but the inventory pins "
        f"{inventory_rns()}: resolve the three closures again together"
    )


# -- nomadnet ----------------------------------------------------------------


def test_nomadnet_is_a_complete_hash_pinned_venv_exposing_nomadnet() -> None:
    block = _venv("nomadnet")
    assert block.python == ">=3.11" and block.expose == ["nomadnet"]
    assert pinned_projects("nomadnet") == {
        "cffi",
        "cryptography",
        "lxmf",
        "nomadnet",
        "pycparser",
        "pyserial",
        "qrcode",
        "rns",
        "typing-extensions",
        "urwid",
        "wcwidth",
    }
    assert pinned("nomadnet", "nomadnet") == "1.4.4" and _unit("nomadnet").version == "1.4.4"
    assert hash_count("nomadnet") == 196
    assert pinned("nomadnet", "lxmf") == pinned("lxmf", "lxmf")


def test_nomadnet_is_gpl_by_its_shipped_text_and_the_page_says_the_classifier_disagrees() -> None:
    """The wheel's classifier says MIT and the licence text it ships is the GPL v3;
    the shipped text governs (maintainer's ruling, 2026-10-03)."""
    block = _venv("nomadnet")
    assert block.licence is not None and block.licence.startswith("GPL-3.0-only")
    assert block.licence_url == "https://github.com/markqvist/NomadNet/blob/master/LICENSE"
    problems = _unit("nomadnet").documentation.known_problems
    assert problems is not None
    assert "The licence statements disagree" in problems and "MIT" in problems
    assert "Reticulum License" not in (block.licence or "")


def test_the_menu_entry_is_a_terminal_launcher_that_does_not_shadow_the_wrapper() -> None:
    unit = _unit("nomadnet")
    (launcher,) = unit.launchers
    assert launcher.terminal and launcher.exec == "{venv}/bin/nomadnet"
    assert launcher.title == "NomadNet (Reticulum messaging and pages)"
    # Both land in ~/.local/bin; one name would have one overwrite the other.
    assert launcher.name == "nomadnet-terminal" and launcher.name not in _venv("nomadnet").expose
    assert unit.user_services == []


def test_nomadnet_leaves_the_operators_identity_and_messages() -> None:
    unit = _unit("nomadnet")
    assert unit.config_files == [] and unit.system_modifications == []
    problems = unit.documentation.known_problems
    assert problems is not None
    assert "~/.nomadnetwork" in problems and "leaves in place" in problems
