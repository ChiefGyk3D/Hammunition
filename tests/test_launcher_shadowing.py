# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""A generated launcher never takes the name of a binary on the PATH (issue #174).

Measured on the field laptop, 2026-09-30: ``~/.local/bin/rigctl``, the
libhamlib-utils launcher, sat ahead of hamlib's ``/usr/bin/rigctl`` because
``~/.local/bin`` comes first on Debian's PATH. The wrapper ignores its
arguments and runs ``rigctl -m 1``, so every guide's ``rigctl -l | grep`` opened
the dummy-rig shell and waited for Enter. Sixteen more catalog launchers had the
same shape (``hackrf_info``, ``rtl_test``, yagiuda's ``input``, ...), and
``~/.local/bin/gpa`` ran ``exec gpa``, which resolved to itself, forever.

Three places refuse or repair it: the schema (a launcher named like the command
it runs, or like a binary its own manifest installs), the generator (a name
found on the system PATH or in the unit's apt file list), and ``menus apply``
(removes a generated launcher that shadows a PATH binary). ``doctor`` names one.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from hammunition.backends.base import BackendError
from hammunition.launchers import (
    MARKER,
    desktop_entry,
    launcher_steps,
    search_path_outside,
    shadowing_launcher_steps,
    survey_shadowing_launchers,
    wrapper_body,
)
from hammunition.manifest.load import load_catalog
from hammunition.manifest.schema import AptInstall, ManifestError, PackageManifest

REPO_ROOT = Path(__file__).resolve().parent.parent
CATALOG = REPO_ROOT / "catalog" / "packages"


def manifest(**overrides: Any) -> PackageManifest:
    base: dict[str, Any] = {
        "name": "hamlibish",
        "version": "1.0",
        "summary": "Fixture shaped like libhamlib-utils",
        "categories": ["rig-control"],
        "install": [{"install": {"method": "apt", "packages": ["hamlibish"]}}],
        "launchers": [
            {
                "name": "rigctl-dummy",
                "exec": "rigctl -m 1",
                "title": "Rig control shell (rigctl)",
                "terminal": True,
            }
        ],
        "update": {"probe": {"method": "none"}, "strategy": "manual"},
        "documentation": {
            "what_it_does": "Exists so the shadowing checks have a unit to plan.",
            "why_you_want_it": "You do not; the suite does.",
            "upstream_url": "https://example.invalid/",
        },
    }
    base.update(overrides)
    return PackageManifest.model_validate(base)


def _executable(path: Path, body: str = "#!/bin/sh\necho real\n") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body)
    path.chmod(0o755)
    return path


def _no_files(_package: str) -> list[str]:
    return []


# ---------------------------------------------------------------------------
# The schema: a name that is the command it runs is a manifest defect
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "exec_line",
    ["rigctl -m 1", "exec rigctl", "  rigctl"],
)
def test_a_launcher_named_like_the_command_it_runs_is_refused(exec_line: str) -> None:
    """The issue's shape and gpa's: ``exec gpa`` named ``gpa`` exec'd itself."""
    with pytest.raises((ValidationError, ManifestError), match=r"rigctl.*rename"):
        manifest(launchers=[{"name": "rigctl", "exec": exec_line}])


def test_a_launcher_named_like_a_binary_its_manifest_installs_is_refused() -> None:
    with pytest.raises((ValidationError, ManifestError), match=r"hamclock.*binaries"):
        manifest(
            install=[
                {
                    "install": {
                        "method": "source",
                        "source": {"url": "https://example.invalid/h.tgz", "sha256": "a" * 64},
                        "build_system": "make",
                    }
                }
            ],
            binaries=[{"produced": "hamclock", "install_as": "hamclock"}],
            launchers=[{"name": "hamclock", "exec": "start-hamclock --backend x"}],
        )


def test_a_launcher_named_for_what_it_does_is_accepted() -> None:
    assert manifest().launchers[0].name == "rigctl-dummy"


def test_a_launcher_running_a_private_path_may_share_its_name() -> None:
    """pygpsclient's launcher runs ``{venv}/bin/pygpsclient``: nothing on the
    PATH has that name, so the launcher is the command, not a shadow of one.
    A path that *is* on the PATH is the generator's to find."""
    m = manifest(launchers=[{"name": "pygpsclient", "exec": "exec {venv}/bin/pygpsclient"}])
    assert m.launchers[0].name == "pygpsclient"


def test_the_generator_refuses_a_launcher_named_like_the_path_it_runs(tmp_path: Path) -> None:
    system = tmp_path / "usr" / "bin"
    _executable(system / "rigctl")
    m = manifest(launchers=[{"name": "rigctl", "exec": f"{system / 'rigctl'} -m 1"}])
    with pytest.raises(BackendError, match="rename"):
        launcher_steps(
            m,
            bin_dir=tmp_path / "bin",
            applications_dir=tmp_path / "apps",
            search_path=str(system),
            executables=_no_files,
        )


# ---------------------------------------------------------------------------
# The generator: measured against the PATH outside ~/.local/bin and dpkg -L
# ---------------------------------------------------------------------------


def test_the_search_path_leaves_out_the_launcher_directory(tmp_path: Path) -> None:
    bin_dir = tmp_path / "home" / ".local" / "bin"
    system = tmp_path / "usr" / "bin"
    path = search_path_outside(bin_dir, f"{bin_dir}:{system}")
    assert str(bin_dir) not in path.split(os.pathsep)
    assert str(system) in path.split(os.pathsep)
    assert "/usr/bin" in path.split(os.pathsep), "the standard directories are always searched"


def test_the_generator_refuses_a_name_found_on_the_system_path(tmp_path: Path) -> None:
    system = tmp_path / "usr" / "bin"
    _executable(system / "rigctl-dummy")
    m = manifest()
    with pytest.raises(BackendError) as caught:
        launcher_steps(
            m,
            bin_dir=tmp_path / "bin",
            applications_dir=tmp_path / "apps",
            search_path=str(system),
            executables=_no_files,
        )
    message = str(caught.value)
    assert str(system / "rigctl-dummy") in message, message
    assert "rename" in message and "hamlibish" in message, message


def test_the_generator_refuses_a_name_the_units_apt_package_ships(tmp_path: Path) -> None:
    """Off the PATH (``/usr/sbin`` for an operator) and still the package's."""
    m = manifest()

    def ships(package: str) -> list[str]:
        assert package == "hamlibish"
        return ["/usr/sbin/rigctl-dummy"]

    with pytest.raises(BackendError, match=r"/usr/sbin/rigctl-dummy"):
        launcher_steps(
            m,
            bin_dir=tmp_path / "bin",
            applications_dir=tmp_path / "apps",
            search_path=str(tmp_path / "empty"),
            executables=ships,
        )


def test_an_old_wrapper_in_the_launcher_directory_is_not_a_clash(tmp_path: Path) -> None:
    bin_dir = tmp_path / "bin"
    _executable(bin_dir / "rigctl-dummy", f"#!/bin/sh\n{MARKER}hamlibish\nrigctl -m 1\n")
    steps = launcher_steps(
        manifest(),
        bin_dir=bin_dir,
        applications_dir=tmp_path / "apps",
        search_path=f"{bin_dir}:{tmp_path / 'empty'}",
        executables=_no_files,
    )
    assert [s.kind for s in steps] == ["wrapper", "desktop-entry"]


def test_a_clash_that_appears_after_the_plan_fails_the_step_and_writes_nothing(
    tmp_path: Path,
) -> None:
    """The plan ran before apt installed the package; the write runs after."""
    system = tmp_path / "usr" / "bin"
    system.mkdir(parents=True)
    bin_dir = tmp_path / "bin"
    steps = launcher_steps(
        manifest(),
        bin_dir=bin_dir,
        applications_dir=tmp_path / "apps",
        search_path=str(system),
        executables=_no_files,
    )
    _executable(system / "rigctl-dummy")
    with pytest.raises(BackendError, match="rename"):
        steps[0].perform()
    assert not (bin_dir / "rigctl-dummy").exists()


# ---------------------------------------------------------------------------
# menus apply and doctor: a launcher from before the fix
# ---------------------------------------------------------------------------


def _old_rigctl(bin_dir: Path, apps: Path) -> None:
    """What the field laptop holds: the launcher under hamlib's own name."""
    _executable(
        bin_dir / "rigctl",
        f"#!/bin/sh\n{MARKER}libhamlib-utils\nrigctl -m 1\n",
    )
    apps.mkdir(parents=True, exist_ok=True)
    (apps / "hammunition-rigctl.desktop").write_text(
        "[Desktop Entry]\nType=Application\nName=Rig control shell (rigctl)\n"
        f"Exec={bin_dir / 'rigctl'}\nX-Hammunition-Package=libhamlib-utils\n"
    )


def test_the_survey_names_a_generated_launcher_that_shadows_a_path_binary(
    tmp_path: Path,
) -> None:
    bin_dir, apps, system = tmp_path / "bin", tmp_path / "apps", tmp_path / "usr" / "bin"
    _old_rigctl(bin_dir, apps)
    _executable(system / "rigctl")
    _executable(bin_dir / "mytool")  # not ours: no marker
    _executable(system / "mytool")
    _executable(bin_dir / "rigctl-dummy", f"#!/bin/sh\n{MARKER}libhamlib-utils\nrigctl -m 1\n")
    found = survey_shadowing_launchers(bin_dir, search_path=f"{bin_dir}:{system}")
    assert found == ((str(bin_dir / "rigctl"), str(system / "rigctl")),)


def test_menus_apply_removes_the_shadowing_launcher_and_writes_the_renamed_one(
    tmp_path: Path,
) -> None:
    from hammunition.menus import missing_launcher_steps

    bin_dir, apps, system = tmp_path / "bin", tmp_path / "apps", tmp_path / "usr" / "bin"
    _old_rigctl(bin_dir, apps)
    _executable(system / "rigctl")
    (apps / "hammunition-other.desktop").write_text("[Desktop Entry]\nName=other\n")

    steps = shadowing_launcher_steps(bin_dir, apps, search_path=str(system))
    renamed = manifest(name="libhamlib-utils")
    steps += missing_launcher_steps(
        [renamed],
        bin_dir=bin_dir,
        applications_dir=apps,
        prefix=tmp_path / "prefix",
        installed=lambda _package: True,
        search_path=str(system),
        executables=_no_files,
    )
    shown = [step.display() for step in steps]
    assert any("rigctl" in line and "shadows" in line for line in shown), shown
    outcomes = [step.perform() for step in steps]
    assert f"removed {bin_dir / 'rigctl'}" in outcomes, outcomes
    assert f"removed {apps / 'hammunition-rigctl.desktop'}" in outcomes, outcomes
    assert f"wrote {bin_dir / 'rigctl-dummy'}" in outcomes, outcomes
    assert not (bin_dir / "rigctl").exists()
    assert (bin_dir / "rigctl-dummy").is_file()
    assert (apps / "hammunition-rigctl-dummy.desktop").is_file()
    assert (apps / "hammunition-other.desktop").is_file(), "only the shadowing launcher's entry"
    assert (system / "rigctl").is_file()


def test_menus_apply_leaves_a_file_without_the_marker_alone(tmp_path: Path) -> None:
    bin_dir, system = tmp_path / "bin", tmp_path / "usr" / "bin"
    _executable(bin_dir / "rigctl", '#!/bin/sh\nexec /opt/my/rigctl "$@"\n')
    _executable(system / "rigctl")
    assert shadowing_launcher_steps(bin_dir, tmp_path / "apps", search_path=str(system)) == []


# ---------------------------------------------------------------------------
# The catalog
# ---------------------------------------------------------------------------


def _first_command(exec_line: str) -> str:
    words = exec_line.split()
    if words[:1] == ["exec"]:
        words = words[1:]
    return words[0]


def test_no_catalog_launcher_is_named_like_the_command_it_runs() -> None:
    """Static, so it runs everywhere, CI included: the schema refuses this at
    load, and this names every offender at once if that validator is lost."""
    offenders = [
        f"{name}: {launcher.name}"
        for name, m in load_catalog(CATALOG).items()
        for launcher in m.launchers
        if (
            "/" not in _first_command(launcher.exec)
            and launcher.name == _first_command(launcher.exec)
        )
        or launcher.name in {b.install_as for b in m.binaries}
    ]
    assert offenders == []


def _dpkg_files(package: str) -> list[str] | None:
    try:
        run = subprocess.run(
            ["dpkg-query", "-L", package], capture_output=True, text=True, check=False
        )
    except FileNotFoundError:
        return None
    return run.stdout.splitlines() if run.returncode == 0 else None


def test_no_catalog_launcher_is_named_like_a_binary_its_apt_package_ships() -> None:
    """Measured from the package contents, on the machine running the suite.

    The repository holds no per-package file lists (the udev sweep keeps only
    rule pairs), so this reads ``dpkg-query -L`` for each apt package the
    catalog's launcher units name **that is installed here**, and, for every
    launcher, ``/usr/bin`` and ``/usr/sbin`` on this machine. On the field
    laptop, where the whole catalog is installed, that covers every one; on a
    CI runner it covers what the runner has, which is why the static test
    above exists. The same question was asked of the archive once, by hand,
    on 2026-09-30: ``apt-get download`` of the 22 apt packages those units
    name on Parrot 7 and ``dpkg-deb -c`` of each found 158 executable names,
    the fifteen old apt launcher names among them and none of the new ones.

    Falsified 2026-09-30 on the field laptop by naming libhamlib-utils'
    launcher ``rigctld`` (a binary the package ships that the launcher does
    not run, so the schema lets it through): red, naming
    ``/usr/bin/rigctld``. Named ``rigctl`` again, the catalog fails to load.
    """
    offenders: list[str] = []
    measured = 0
    for name, m in sorted(load_catalog(CATALOG).items()):
        if not m.launchers:
            continue
        shipped: set[str] = set()
        for block in m.install:
            if not isinstance(block.install, AptInstall):
                continue
            for package in block.install.packages:
                files = _dpkg_files(package)
                if files is None:
                    continue
                measured += 1
                shipped |= {line for line in files if "/bin/" in line or "/sbin/" in line}
        for launcher in m.launchers:
            clashes = sorted(
                {f for f in shipped if Path(f).name == launcher.name}
                | {
                    str(Path(d) / launcher.name)
                    for d in ("/usr/bin", "/usr/sbin")
                    if (Path(d) / launcher.name).exists()
                }
            )
            if clashes:
                offenders.append(f"{name}: launcher {launcher.name} shadows {clashes}")
    assert offenders == [], offenders
    if measured == 0:
        pytest.skip("no catalog launcher unit's apt package is installed here to measure")


def test_the_desktop_entry_keeps_the_title_under_the_new_name(tmp_path: Path) -> None:
    """D-054: the menu shows what it does; the rename is the file's, not the title's."""
    m = load_catalog(CATALOG)["libhamlib-utils"]
    (launcher,) = m.launchers
    assert launcher.name == "rigctl-dummy"
    entry = desktop_entry(m, launcher, tmp_path / "rigctl-dummy")
    assert "Name=Rig control shell (rigctl)\n" in entry
    assert wrapper_body(m, launcher).splitlines()[2] == "rigctl -m 1"
