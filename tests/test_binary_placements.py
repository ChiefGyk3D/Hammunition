# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""A prebuilt archive's files, spread to fixed places (hammunition-tray 0.5.0).

The tray's release published no .deb, so the tray units pin the tag's archive
and `placements` do what the .deb's file list would. A catalog is data, so the
places are an allow-list the schema enforces; every file is named, so the plan
prints each and the pinned archive is compared with the list; and removal rests
on the transaction log, never on a directory listing.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from hammunition.backends import Action, BackendError, BinaryBackend, Command, RecordingRunner
from hammunition.distro import Target
from hammunition.execute import build_effects_present, placed_files, verify_effects
from hammunition.fetch import Fetcher
from hammunition.manifest.load import load_catalog
from hammunition.manifest.schema import BinaryInstall, PackageManifest, Placement
from hammunition.plan import InstallPlan, PlannedPackage
from hammunition.state.uninstall import RemovalPaths, RemovalPlan, plan_removal

CATALOG = Path(__file__).resolve().parent.parent / "catalog" / "packages"
TARGET = Target(distro="debian", version="13", arch="x86_64")


def _manifest(name: str = "demo", **install: Any) -> PackageManifest:
    block: dict[str, Any] = {
        "method": "binary",
        "artifact": {"url": "https://example.invalid/demo.tar.gz", "sha256": "7" * 64},
        "format": "tarball",
        **install,
    }
    return PackageManifest.model_validate(
        {
            "name": name,
            "version": "1.0",
            "summary": "An archive whose files go to fixed places",
            "categories": ["device-support"],
            "install": [{"install": block}],
            "update": {"probe": {"method": "none"}},
            "documentation": {
                "what_it_does": "Stands in for a tray applet distributed as a source archive.",
                "why_you_want_it": "Because a release can precede its package.",
                "upstream_url": "https://example.invalid/",
            },
        }
    )


# ---------------------------------------------------------------------------
# The schema is the allow-list
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "dest",
    [
        "/etc/passwd",
        "/etc/cron.d/x",
        "/usr/bin/x",
        "/usr/share/polkit-1/actions/x.policy",
        "/usr/lib/systemd/system/x.service",
        "/usr/local/../etc/shadow",
        "/usr/local//x",
        "/usr/local/bin/",
        "relative/x",
        "/usr/local/",
    ],
)
def test_a_destination_outside_the_allow_list_does_not_load(dest: str) -> None:
    with pytest.raises(ValidationError):
        Placement(source="a/b", dest=dest)


@pytest.mark.parametrize("source", ["/etc/shadow", "../x", "a/../../x", ""])
def test_a_source_that_leaves_the_archive_does_not_load(source: str) -> None:
    with pytest.raises(ValidationError):
        Placement(source=source, dest="/usr/local/bin/x")


@pytest.mark.parametrize("mode", ["4755", "0666", "0600", "0777", "755"])
def test_nothing_placed_is_setuid_writable_or_private(mode: str) -> None:
    with pytest.raises(ValidationError):
        Placement(source="x", dest="/usr/local/bin/x", mode=mode)


def test_a_deb_has_no_archive_to_spread() -> None:
    with pytest.raises(ValidationError, match="unpack an archive"):
        _manifest(
            format="deb",
            deb_package="demo",
            placements=[{"source": "x", "dest": "/usr/local/bin/x"}],
        )


def test_the_same_destination_twice_does_not_load() -> None:
    with pytest.raises(ValidationError, match="twice"):
        _manifest(
            placements=[
                {"source": "a", "dest": "/usr/local/bin/x"},
                {"source": "b", "dest": "/usr/local/bin/x"},
            ]
        )


@pytest.mark.parametrize(
    "directory",
    [
        "/usr/local",
        "/usr/local/lib",
        "/usr/share/icons/hicolor/scalable/apps",
        "/usr/share/applications",
        "/etc/xdg/autostart",
        "/usr/share/plasma/plasmoids",
    ],
)
def test_a_shared_directory_is_never_removed_whole(directory: str) -> None:
    """`rm -rf` of a directory every program's files share would be the bug."""
    with pytest.raises(ValidationError):
        _manifest(
            placements=[{"source": "a", "dest": f"{directory}/x"}],
            placement_dirs=[directory],
        )


def test_a_directory_removed_whole_must_hold_a_placement() -> None:
    with pytest.raises(ValidationError, match="holds none"):
        _manifest(
            placements=[{"source": "a", "dest": "/usr/local/bin/x"}],
            placement_dirs=["/usr/local/lib/hammunition-demo"],
        )


def test_the_helper_block_needs_a_package_that_can_import() -> None:
    with pytest.raises(ValidationError, match="lacks"):
        _manifest(devctl_helper={"modules": ["run.py"]})
    with pytest.raises(ValidationError, match=r"plain \.py"):
        _manifest(devctl_helper={"modules": ["__init__.py", "devctl.py", "../x.py"]})


# ---------------------------------------------------------------------------
# The steps
# ---------------------------------------------------------------------------


def _backend(tmp_path: Path, **kw: Any) -> BinaryBackend:
    return BinaryBackend(
        fetcher=Fetcher(tmp_path / "cache"),
        runner=RecordingRunner(),
        build_root=tmp_path / "build",
        prefix=tmp_path / "prefix",
        **kw,
    )


def test_a_placements_only_archive_is_installable_and_prints_each_file(tmp_path: Path) -> None:
    manifest = _manifest(
        placements=[
            {"source": "bin/tool", "dest": "/usr/local/bin/tool", "mode": "0755"},
            {"source": "share/x.desktop", "dest": "/usr/share/applications/x.desktop"},
        ]
    )
    backend = _backend(tmp_path)
    block = manifest.install[0]
    install = block.install
    assert isinstance(install, BinaryInstall)
    steps = backend.steps(manifest, block)
    src = backend.layout(manifest, install).src
    installs = [s.argv for s in steps if isinstance(s, Command) and s.argv[0] == "install"]
    assert installs == [
        ("install", "-D", "-m", "0755", f"{src}/bin/tool", f"{tmp_path}/prefix/bin/tool"),
        (
            "install",
            "-D",
            "-m",
            "0644",
            f"{src}/share/x.desktop",
            "/usr/share/applications/x.desktop",
        ),
    ]
    placed = [s for s in steps if isinstance(s, Command) and s.argv[:2] == ("install", "-D")]
    assert placed[1].requires_root, "/usr/share is root's, whoever runs the engine"


def test_an_archive_naming_nothing_to_install_is_still_refused(tmp_path: Path) -> None:
    manifest = _manifest()
    with pytest.raises(BackendError, match="no `placements`"):
        _backend(tmp_path).steps(manifest, manifest.install[0])


def test_the_planner_blocks_an_archive_that_installs_nothing_and_not_one_that_places_files() -> (
    None
):
    from hammunition.plan import _check_engine_capability

    nothing = _manifest()
    assert [b.subject for b in _check_engine_capability(nothing, nothing.install[0])] == ["demo"]
    places = _manifest(placements=[{"source": "a", "dest": "/usr/local/bin/a", "mode": "0755"}])
    assert _check_engine_capability(places, places.install[0]) == []
    helper = _manifest(devctl_helper={"modules": ["__init__.py", "devctl.py"]})
    assert _check_engine_capability(helper, helper.install[0]) == []


# ---------------------------------------------------------------------------
# The effect check
# ---------------------------------------------------------------------------


def _plan(manifest: PackageManifest) -> InstallPlan:
    return InstallPlan(
        target=TARGET,
        packages=(PlannedPackage(manifest=manifest, block=manifest.install[0], apt_packages=()),),
    )


def test_a_placed_file_that_is_not_there_is_an_unconfirmed_effect(tmp_path: Path) -> None:
    manifest = _manifest(placements=[{"source": "a", "dest": "/usr/local/bin/a", "mode": "0755"}])
    plan = _plan(manifest)
    prefix = tmp_path / "prefix"
    missing = verify_effects(plan, None, prefix=prefix)
    assert [c.confirmed for c in missing.checks if c.kind == "file"] == [False]
    (prefix / "bin").mkdir(parents=True)
    (prefix / "bin" / "a").write_text("x")
    there = verify_effects(plan, None, prefix=prefix)
    assert [c.confirmed for c in there.checks if c.kind == "file"] == [True]
    assert placed_files(manifest.install[0], prefix) == (prefix / "bin" / "a",)
    assert build_effects_present(plan.packages[0], prefix=prefix) is True


def test_the_helper_check_asks_the_helper_itself(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from hammunition.hardware import polkit

    manifest = _manifest(devctl_helper={"modules": ["__init__.py", "devctl.py"]})
    plan = _plan(manifest)
    monkeypatch.setattr(polkit, "installed_helper_version", lambda *a, **k: None)
    bad = verify_effects(plan, None, prefix=tmp_path)
    assert [c.confirmed for c in bad.checks if c.kind == "helper"] == [False]
    monkeypatch.setattr(
        polkit, "installed_helper_version", lambda *a, **k: "hammunition-devctl contract 1"
    )
    good = verify_effects(plan, None, prefix=tmp_path)
    assert [c.confirmed for c in good.checks if c.kind == "helper"] == [True]


# ---------------------------------------------------------------------------
# Uninstall rests on the log
# ---------------------------------------------------------------------------


def _paths(tmp_path: Path) -> RemovalPaths:
    return RemovalPaths(
        prefix=tmp_path / "prefix",
        venv_root=tmp_path / "venvs",
        bin_dir=tmp_path / "bin",
        applications_dir=tmp_path / "apps",
    )


def _touch(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("x")


def _remove(
    tmp_path: Path, names: list[str], catalog: dict[str, PackageManifest], attributed: set[str]
) -> RemovalPlan:
    return plan_removal(
        names,
        catalog=catalog,
        profiles={},
        target=TARGET,
        attributed=frozenset(),
        states={},
        paths=_paths(tmp_path),
        attributed_files=frozenset(attributed),
    )


def test_only_what_the_log_attributes_is_removed(tmp_path: Path) -> None:
    manifest = _manifest(
        placements=[
            {"source": "a", "dest": "/usr/local/bin/ours", "mode": "0755"},
            {"source": "b", "dest": "/usr/local/bin/theirs", "mode": "0755"},
        ]
    )
    prefix = tmp_path / "prefix"
    _touch(prefix / "bin" / "ours")
    _touch(prefix / "bin" / "theirs")
    plan = _remove(tmp_path, ["demo"], {"demo": manifest}, {str(prefix / "bin" / "ours")})
    assert [(a.kind, a.path.name, a.basis) for a in plan.artifacts["demo"]] == [
        ("binary", "ours", "log")
    ]
    assert plan.left_unattributed["demo"] == [str(prefix / "bin" / "theirs")]


def test_a_directory_goes_whole_only_when_a_file_in_it_is_attributed(tmp_path: Path) -> None:
    manifest = _manifest(
        placements=[{"source": "a", "dest": "/usr/local/share/hammunition-demo/a"}],
        placement_dirs=["/usr/local/share/hammunition-demo"],
    )
    prefix = tmp_path / "prefix"
    _touch(prefix / "share" / "hammunition-demo" / "a")
    none = _remove(tmp_path, ["demo"], {"demo": manifest}, set())
    assert "demo" not in none.artifacts or all(a.kind != "tree" for a in none.artifacts["demo"])
    some = _remove(
        tmp_path, ["demo"], {"demo": manifest}, {str(prefix / "share" / "hammunition-demo" / "a")}
    )
    kinds = [(a.kind, a.path) for a in some.artifacts["demo"]]
    assert kinds == [
        ("binary", prefix / "share/hammunition-demo/a"),
        ("tree", prefix / "share/hammunition-demo"),
    ]


# ---------------------------------------------------------------------------
# The tray units: the helper goes only when nobody left installed still needs it
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def tray_units() -> dict[str, PackageManifest]:
    catalog = load_catalog(CATALOG)
    return {n: catalog[n] for n in ("hammunition-tray", "hammunition-tray-qt")}


def _helper_attributions(prefix: Path) -> set[str]:
    return {
        str(prefix / "lib/hammunition-devctl/hammunition-devctl"),
        str(prefix / "libexec/hammunition-devctl"),
        "/usr/share/polkit-1/actions/com.chiefgyk3d.hammunition.devctl.policy",
    }


def _lay_out_helper(prefix: Path) -> None:
    _touch(prefix / "lib/hammunition-devctl/hammunition-devctl")
    _touch(prefix / "libexec/hammunition-devctl")


def test_uninstalling_the_only_tray_unit_removes_the_helper_this_engine_installed(
    tmp_path: Path, tray_units: dict[str, PackageManifest]
) -> None:
    prefix = tmp_path / "prefix"
    _lay_out_helper(prefix)
    plan = _remove(tmp_path, ["hammunition-tray"], tray_units, _helper_attributions(prefix))
    removed = {(a.kind, a.path) for a in plan.artifacts["hammunition-tray"]}
    assert ("tree", prefix / "lib/hammunition-devctl") in removed
    assert ("binary", prefix / "libexec/hammunition-devctl") in removed
    assert not plan.kept_shared


def test_the_helper_stays_while_the_other_tray_unit_is_still_installed(
    tmp_path: Path, tray_units: dict[str, PackageManifest]
) -> None:
    prefix = tmp_path / "prefix"
    _lay_out_helper(prefix)
    # hammunition-tray-qt's launcher script is on disk: it is installed.
    _touch(prefix / "bin" / "hammunition-tray-qt")
    plan = _remove(tmp_path, ["hammunition-tray"], tray_units, _helper_attributions(prefix))
    removed = {a.path for a in plan.artifacts.get("hammunition-tray", [])}
    assert prefix / "lib/hammunition-devctl" not in removed
    assert prefix / "libexec/hammunition-devctl" not in removed
    assert str(prefix / "libexec/hammunition-devctl") in plan.kept_shared["hammunition-tray"]


def test_removing_both_tray_units_together_removes_the_helper(
    tmp_path: Path, tray_units: dict[str, PackageManifest]
) -> None:
    prefix = tmp_path / "prefix"
    _lay_out_helper(prefix)
    _touch(prefix / "bin" / "hammunition-tray-qt")
    plan = _remove(
        tmp_path,
        ["hammunition-tray", "hammunition-tray-qt"],
        tray_units,
        _helper_attributions(prefix),
    )
    everything = {a.path for removals in plan.artifacts.values() for a in removals}
    assert prefix / "lib/hammunition-devctl" in everything


def test_a_helper_another_installer_placed_is_never_removed(
    tmp_path: Path, tray_units: dict[str, PackageManifest]
) -> None:
    """The log does not attribute the entry script, so it is not ours."""
    prefix = tmp_path / "prefix"
    _lay_out_helper(prefix)
    plan = _remove(tmp_path, ["hammunition-tray"], tray_units, set())
    removed = {a.path for a in plan.artifacts.get("hammunition-tray", [])}
    assert prefix / "lib/hammunition-devctl" not in removed
    assert str(prefix / "libexec/hammunition-devctl") in plan.left_unattributed["hammunition-tray"]


def test_the_removal_steps_are_the_commands_the_attribution_replay_reads(
    tmp_path: Path, tray_units: dict[str, PackageManifest]
) -> None:
    from hammunition.execute import artifact_removal_steps

    prefix = tmp_path / "prefix"
    _lay_out_helper(prefix)
    plan = _remove(tmp_path, ["hammunition-tray"], tray_units, _helper_attributions(prefix))
    argvs = [s.argv for s in artifact_removal_steps(plan) if isinstance(s, Command)]
    assert ("rm", "-f", "--", str(prefix / "libexec/hammunition-devctl")) in argvs
    # files before the tree, so each is un-attributed by its own rm -f
    assert argvs.index(
        ("rm", "-f", "--", str(prefix / "lib/hammunition-devctl/hammunition-devctl"))
    ) < argvs.index(("rm", "-rf", "--", str(prefix / "lib/hammunition-devctl")))
    assert not [
        s for s in artifact_removal_steps(plan) if isinstance(s, Action) and s.kind == "remove-venv"
    ]
