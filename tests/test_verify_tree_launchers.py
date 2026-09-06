# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later
"""The effect check covers installed trees and launchers (issue #27).

Until this file existed, `verify_effects` asked about binaries, apt packages
and group memberships and nothing else. A unit that installs a *tree* --
yaac's zip under ``<prefix>/share/hammunition/yaac``, mshv's built
directory, the two venv payloads -- declares no ``binaries``, so it ended
``verified: true`` with no check at all; and a launcher that the run wrote
into ``~/.local/bin`` was never read back. Both are exactly the D-031 shape:
``cp -aT`` exits 0 on a tree whose contents are not what the launcher
expects, and a wrapper is a file that may or may not be executable.

Every test here was watched red before the check existed.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from hammunition.distro import Target  # noqa: E402
from hammunition.execute import verify_effects  # noqa: E402
from hammunition.manifest.load import load_catalog  # noqa: E402
from hammunition.manifest.schema import (  # noqa: E402
    BinaryInstall,
    GitInstall,
    ManifestError,
    PackageManifest,
    SourceInstall,
    VenvInstall,
)
from hammunition.plan import InstallPlan, PlannedPackage  # noqa: E402

TARGET = Target(distro="debian", version="13", arch="x86_64")
CATALOG = REPO_ROOT / "catalog" / "packages"
SHA = "a" * 64

DOCS = {
    "what_it_does": "Stands in for a unit that installs a whole tree.",
    "why_you_want_it": "To prove the effect check reads the tree back.",
    "upstream_url": "https://example.invalid/",
}


def _tree_manifest(**overrides: Any) -> PackageManifest:
    """A binary zip installed whole, reached through a launcher -- yaac's shape."""
    install: dict[str, Any] = {
        "method": "binary",
        "artifact": {"url": "https://example.invalid/treeish.zip", "sha256": SHA},
        "format": "zip",
        "install_tree": True,
        "tree_marker": "Treeish.jar",
    }
    install.update(overrides.pop("install", {}))
    data: dict[str, Any] = {
        "name": "treeish",
        "version": "1.0",
        "summary": "A unit that is a directory",
        "categories": ["packet"],
        "install": [{"install": install}],
        "launchers": [
            {"name": "treeish", "exec": "exec java -jar Treeish.jar"},
        ],
        "update": {"probe": {"method": "none"}},
        "documentation": DOCS,
    }
    data.update(overrides)
    return PackageManifest.model_validate(data)


def _plan_for(manifest: PackageManifest) -> InstallPlan:
    return InstallPlan(
        target=TARGET,
        packages=(PlannedPackage(manifest=manifest, block=manifest.install[0], apt_packages=()),),
    )


def _lay_tree(prefix: Path, name: str, *files: str) -> Path:
    tree = prefix / "share" / "hammunition" / name
    tree.mkdir(parents=True, exist_ok=True)
    for relative in files:
        target = tree / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("")
    return tree


# ---------------------------------------------------------------------------
# Trees
# ---------------------------------------------------------------------------


def test_a_tree_without_its_marker_is_unconfirmed_by_name(tmp_path: Path) -> None:
    """The falsification: build the tree, leave out the file the launcher
    needs, and the check must go red naming that file."""
    prefix = tmp_path / "p"
    _lay_tree(prefix, "treeish", "lib/other.jar")
    verification = verify_effects(_plan_for(_tree_manifest()), None, prefix=prefix)
    assert not verification.ok
    (check,) = verification.discrepancies
    assert check.kind == "tree"
    assert check.subject == "treeish:Treeish.jar"
    assert str(prefix / "share" / "hammunition" / "treeish" / "Treeish.jar") in check.detail
    assert "exited 0" in check.detail


def test_a_tree_with_its_marker_is_confirmed(tmp_path: Path) -> None:
    prefix = tmp_path / "p"
    _lay_tree(prefix, "treeish", "Treeish.jar")
    verification = verify_effects(_plan_for(_tree_manifest()), None, prefix=prefix)
    assert verification.ok
    (check,) = verification.checks
    assert check.kind == "tree"
    assert str(prefix / "share" / "hammunition" / "treeish" / "Treeish.jar") in check.detail


def test_a_missing_tree_is_reported_as_the_marker_not_a_traceback(tmp_path: Path) -> None:
    prefix = tmp_path / "p"
    verification = verify_effects(_plan_for(_tree_manifest()), None, prefix=prefix)
    (check,) = verification.discrepancies
    assert check.kind == "tree"
    assert not check.confirmed


def test_a_venv_payload_tree_is_checked_too(tmp_path: Path) -> None:
    """radiosonde_auto_rx and supersdr are venvs whose software is a tree the
    venv runs; the marker sits under the same shared prefix."""
    manifest = PackageManifest.model_validate(
        {
            "name": "payloadish",
            "version": "1.0",
            "summary": "A venv that runs a payload tree",
            "categories": ["sdr"],
            "install": [
                {
                    "install": {
                        "method": "venv",
                        "requirements": [f"numpy==2.0.0 --hash=sha256:{SHA}"],
                        "payload": {
                            "url": "https://example.invalid/payloadish.tar.gz",
                            "sha256": SHA,
                        },
                        "tree_marker": "auto_rx/auto_rx.py",
                    }
                }
            ],
            "launchers": [{"name": "payloadish", "exec": "exec {venv}/bin/python auto_rx.py"}],
            "update": {"probe": {"method": "none"}},
            "documentation": DOCS,
        }
    )
    prefix = tmp_path / "p"
    _lay_tree(prefix, "payloadish", "auto_rx/README.md")
    red = verify_effects(_plan_for(manifest), None, prefix=prefix)
    assert [c.subject for c in red.discrepancies] == ["payloadish:auto_rx/auto_rx.py"]
    _lay_tree(prefix, "payloadish", "auto_rx/auto_rx.py")
    assert verify_effects(_plan_for(manifest), None, prefix=prefix).ok


def test_without_a_prefix_trees_are_an_unasked_question(tmp_path: Path) -> None:
    """Symmetry with binaries and the prober: no prefix, no tree checks."""
    verification = verify_effects(_plan_for(_tree_manifest()), None)
    assert verification.checks == ()


# ---------------------------------------------------------------------------
# Launchers
# ---------------------------------------------------------------------------


def test_a_launcher_wrapper_that_was_never_written_is_unconfirmed(tmp_path: Path) -> None:
    prefix = tmp_path / "p"
    _lay_tree(prefix, "treeish", "Treeish.jar")
    launcher_bin = tmp_path / "bin"
    verification = verify_effects(
        _plan_for(_tree_manifest()), None, prefix=prefix, launcher_bin=launcher_bin
    )
    assert not verification.ok
    (check,) = verification.discrepancies
    assert check.kind == "launcher"
    assert check.subject == "treeish:treeish"
    assert str(launcher_bin / "treeish") in check.detail


def test_a_launcher_wrapper_must_be_executable(tmp_path: Path) -> None:
    prefix = tmp_path / "p"
    _lay_tree(prefix, "treeish", "Treeish.jar")
    launcher_bin = tmp_path / "bin"
    launcher_bin.mkdir()
    wrapper = launcher_bin / "treeish"
    wrapper.write_text("#!/bin/sh\n")
    wrapper.chmod(0o644)
    plan = _plan_for(_tree_manifest())
    red = verify_effects(plan, None, prefix=prefix, launcher_bin=launcher_bin)
    assert [c.kind for c in red.discrepancies] == ["launcher"]
    wrapper.chmod(0o755)
    green = verify_effects(plan, None, prefix=prefix, launcher_bin=launcher_bin)
    assert green.ok
    assert {c.kind for c in green.checks} == {"tree", "launcher"}


def test_a_launcher_working_directory_that_does_not_exist_is_unconfirmed(tmp_path: Path) -> None:
    """js8spotter, supersdr and radiosonde-auto-rx `cd` into the tree before
    running; a wrapper whose directory is absent fails on every click."""
    prefix = tmp_path / "p"
    _lay_tree(prefix, "treeish", "Treeish.jar")
    launcher_bin = tmp_path / "bin"
    launcher_bin.mkdir()
    wrapper = launcher_bin / "treeish"
    wrapper.write_text("#!/bin/sh\n")
    wrapper.chmod(0o755)
    workdir = prefix / "share" / "hammunition" / "treeish" / "run"
    manifest = _tree_manifest(
        launchers=[
            {
                "name": "treeish",
                "exec": "exec java -jar ../Treeish.jar",
                "working_directory": str(workdir),
            }
        ]
    )
    red = verify_effects(_plan_for(manifest), None, prefix=prefix, launcher_bin=launcher_bin)
    (check,) = red.discrepancies
    assert check.kind == "launcher"
    assert str(workdir) in check.detail
    workdir.mkdir()
    assert verify_effects(_plan_for(manifest), None, prefix=prefix, launcher_bin=launcher_bin).ok


def test_without_a_launcher_dir_launchers_are_an_unasked_question(tmp_path: Path) -> None:
    prefix = tmp_path / "p"
    _lay_tree(prefix, "treeish", "Treeish.jar")
    verification = verify_effects(_plan_for(_tree_manifest()), None, prefix=prefix)
    assert [c.kind for c in verification.checks] == ["tree"]


# ---------------------------------------------------------------------------
# The schema demands a marker wherever a tree is installed
# ---------------------------------------------------------------------------


def test_install_tree_without_a_marker_is_a_manifest_error() -> None:
    with pytest.raises((ManifestError, ValidationError), match="tree_marker"):
        _tree_manifest(install={"tree_marker": None})


def test_a_marker_without_install_tree_is_a_manifest_error() -> None:
    with pytest.raises((ManifestError, ValidationError), match="tree_marker"):
        _tree_manifest(
            install={"install_tree": False, "tree_marker": "Treeish.jar"},
            binaries=[{"produced": "treeish", "install_as": "treeish"}],
        )


@pytest.mark.parametrize("marker", ["/etc/passwd", "../outside", "a/../../b", ""])
def test_a_marker_stays_inside_the_tree(marker: str) -> None:
    with pytest.raises((ManifestError, ValidationError), match="tree_marker"):
        _tree_manifest(install={"tree_marker": marker})


def test_a_venv_payload_without_a_marker_is_a_manifest_error() -> None:
    with pytest.raises((ManifestError, ValidationError), match="tree_marker"):
        PackageManifest.model_validate(
            {
                "name": "payloadish",
                "version": "1.0",
                "summary": "A venv that runs a payload tree",
                "categories": ["sdr"],
                "install": [
                    {
                        "install": {
                            "method": "venv",
                            "requirements": [f"numpy==2.0.0 --hash=sha256:{SHA}"],
                            "payload": {
                                "url": "https://example.invalid/payloadish.tar.gz",
                                "sha256": SHA,
                            },
                        }
                    }
                ],
                "update": {"probe": {"method": "none"}},
                "documentation": DOCS,
            }
        )


# ---------------------------------------------------------------------------
# The catalog: which units this reaches, pinned so a change is a decision
# ---------------------------------------------------------------------------


def _installs_a_tree(install: object) -> bool:
    if isinstance(install, SourceInstall | GitInstall | BinaryInstall):
        return install.install_tree
    return isinstance(install, VenvInstall) and install.payload is not None


def test_every_catalog_tree_names_its_marker() -> None:
    catalog = load_catalog(CATALOG)
    tree_units = {
        name
        for name, manifest in catalog.items()
        if any(_installs_a_tree(block.install) for block in manifest.install)
    }
    assert tree_units == {"js8spotter", "mshv", "yaac", "radiosonde-auto-rx", "supersdr"}, (
        "a unit started or stopped installing a tree; update this pin and check its marker"
    )
    for name in tree_units:
        for block in catalog[name].install:
            if _installs_a_tree(block.install):
                marker = getattr(block.install, "tree_marker", None)
                assert marker, f"{name}: a tree block with no tree_marker"


def test_every_catalog_launcher_working_directory_is_under_the_shared_prefix() -> None:
    """The launcher check reads `working_directory` back from disk, so the
    catalog's values must be paths the run actually creates: under
    /usr/local/share/hammunition/<name>, never a home directory or a guess."""
    catalog = load_catalog(CATALOG)
    launcher_units = {name for name, m in catalog.items() if m.launchers}
    assert launcher_units == {
        "ais-catcher",
        "hamclock-next",
        "js8spotter",
        "mshv",
        "openhamclock",
        "radiosonde-auto-rx",
        "supersdr",
        "yaac",
    }, "a unit gained or lost launchers; update this pin"
    for name in launcher_units:
        for launcher in catalog[name].launchers:
            if launcher.working_directory is None:
                continue
            assert launcher.working_directory.startswith(f"/usr/local/share/hammunition/{name}"), (
                f"{name}: launcher {launcher.name} runs in {launcher.working_directory}, "
                f"which no install step creates"
            )


# ---------------------------------------------------------------------------
# The run itself asks both questions and records the answers
# ---------------------------------------------------------------------------


def test_execute_records_tree_and_launcher_checks_in_transaction_end(tmp_path: Path) -> None:
    """A tree unit's run ends `verified: false` when the marker is missing --
    the state every 2026-09-04 campaign called `installed+confirmed`."""
    from hammunition.backends import Command, RecordingRunner
    from hammunition.execute import execute
    from hammunition.state import TransactionLog

    prefix = tmp_path / "p"
    _lay_tree(prefix, "treeish", "lib/other.jar")
    log = TransactionLog(tmp_path / "log.jsonl")
    report = execute(
        [Command(argv=("true",), description="ok")],
        RecordingRunner(),
        log=log,
        plan=_plan_for(_tree_manifest()),
        prefix=prefix,
        launcher_bin=tmp_path / "bin",
    )
    assert report.ok, "the command still exited 0"
    assert not report.verified
    end = next(e for e in log.read() if e["event"] == "transaction_end")
    assert end["verified"] is False
    assert {(c["kind"], c["confirmed"]) for c in end["checks"]} == {
        ("tree", False),
        ("launcher", False),
    }
