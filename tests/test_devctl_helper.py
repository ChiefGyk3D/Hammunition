# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""The engine installs the tray's device helper from the tray's own archive.

D-056, amended 2026-10-02. Four properties, each with the check that would turn
red if it stopped being true:

* the wrapper and the polkit action are the tray's, byte for byte, rendered by
  the pinned archive's own code and compared here (skipped, with the reason,
  when the archive is not in the fetch cache);
* an installed helper that already answers is not fought, and the plan says
  whose it is;
* a tree any account can write is refused, one only its owner can write is
  confirmed, never by ``--yes``;
* the wrapper this engine writes answers ``--version`` with the contract line
  when run against the pinned code.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from hammunition.backends import Action, Command, SubprocessRunner
from hammunition.backends.placements import helper_steps
from hammunition.devctl_helper import (
    ENTRY_NAME,
    LIBDIR,
    WRAPPER_MARK,
    plan_helper,
    under_prefix,
    wrapper_script,
)
from hammunition.hardware import polkit
from hammunition.hardware.polkit import (
    HELPER_PATH,
    POLICY_PATH,
    WritabilityFinding,
    WritabilityRisk,
)
from hammunition.manifest.load import load_catalog
from hammunition.manifest.schema import BinaryInstall, DevctlHelper

CATALOG = Path(__file__).resolve().parent.parent / "catalog" / "packages"
CONTRACT_LINE = "hammunition-devctl contract 1"


@pytest.fixture(scope="module")
def helper_block() -> DevctlHelper:
    manifest = load_catalog(CATALOG)["hammunition-tray"]
    install = manifest.install[0].install
    assert isinstance(install, BinaryInstall) and install.devctl_helper is not None
    return install.devctl_helper


def _tray_render(tree: Path, *args: str) -> str:
    return subprocess.run(
        [sys.executable, str(tree / "scripts" / "render_helper_files.py"), *args],
        check=True,
        capture_output=True,
        text=True,
    ).stdout


# ---------------------------------------------------------------------------
# The files are the tray's own, byte for byte
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "interpreter",
    ["/home/op/src/Hammunition/.venv/bin/python", "/opt/an engine/venv/bin/python3.13"],
)
def test_the_wrapper_is_the_trays_wrapper_byte_for_byte(
    pinned_tray: Path, interpreter: str
) -> None:
    entry = f"{LIBDIR}/{ENTRY_NAME}"
    assert wrapper_script(interpreter, entry) == _tray_render(
        pinned_tray, "wrapper", interpreter, entry
    )


def test_the_policy_is_the_trays_policy_byte_for_byte(pinned_tray: Path) -> None:
    assert polkit.policy_xml() == _tray_render(pinned_tray, "policy")


def test_the_wrapper_carries_the_trays_mark_the_tray_installer_looks_for() -> None:
    assert WRAPPER_MARK in wrapper_script("/usr/bin/python3")
    assert WRAPPER_MARK == "# Installed by hammunition-tray (hammunition-devctl, D-056).\n"


def test_the_manifest_lists_exactly_the_modules_the_archive_ships(
    pinned_tray: Path, helper_block: DevctlHelper
) -> None:
    shipped = sorted(
        p.name for p in (pinned_tray / helper_block.source / "hammunition_devctl").glob("*.py")
    )
    assert sorted(helper_block.modules) == shipped, (
        "the catalog's devctl_helper.modules and the pinned archive disagree: a module added "
        "upstream would not be installed, and the helper would fail to import it as root"
    )
    assert (pinned_tray / helper_block.source / ENTRY_NAME).is_file()


# ---------------------------------------------------------------------------
# Whose helper is it?
# ---------------------------------------------------------------------------


def _helper(modules: list[str] | None = None) -> DevctlHelper:
    return DevctlHelper(modules=modules or ["__init__.py", "devctl.py"])


def _write_wrapper(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def _answers(monkeypatch: pytest.MonkeyPatch, line: str | None) -> None:
    monkeypatch.setattr(polkit, "installed_helper_version", lambda *a, **k: line)


NO_OWNER = lambda _path: None  # noqa: E731


def test_nothing_installed_means_install(tmp_path: Path) -> None:
    got = plan_helper(
        _helper(),
        wrapper_path=tmp_path / "libexec" / "h",
        owner_of=NO_OWNER,
        interpreter="/usr/bin/python3",
    )
    assert got.install and got.owner == "nobody yet" and not got.refresh


def test_a_package_that_owns_the_policy_is_never_overwritten(tmp_path: Path) -> None:
    got = plan_helper(
        _helper(),
        wrapper_path=tmp_path / "h",
        owner_of=lambda path: "hammunition-devctl" if path == POLICY_PATH else None,
        interpreter="/usr/bin/python3",
    )
    assert not got.install
    assert "hammunition-devctl package (apt)" in got.owner


def test_a_helper_the_trays_installer_placed_that_answers_is_left_alone(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    wrapper = tmp_path / "libexec" / "hammunition-devctl"
    _write_wrapper(wrapper, wrapper_script("/usr/bin/python3"))
    _answers(monkeypatch, CONTRACT_LINE)
    got = plan_helper(
        _helper(), wrapper_path=wrapper, owner_of=NO_OWNER, interpreter="/usr/bin/python3"
    )
    assert not got.install
    assert "hammunition-tray's own installer" in got.owner
    assert got.version == CONTRACT_LINE


def test_a_helper_this_engine_installed_earlier_is_refreshed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    wrapper = tmp_path / "libexec" / "hammunition-devctl"
    _write_wrapper(wrapper, wrapper_script("/usr/bin/python3"))
    _answers(monkeypatch, CONTRACT_LINE)
    got = plan_helper(
        _helper(),
        attributed_files={str(wrapper)},
        wrapper_path=wrapper,
        owner_of=NO_OWNER,
        interpreter="/usr/bin/python3",
    )
    assert got.install and got.refresh and "earlier run of this engine" in got.owner


def test_an_unmarked_helper_that_answers_is_left_alone(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    wrapper = tmp_path / "hammunition-devctl"
    _write_wrapper(wrapper, "#!/bin/sh\necho 'hammunition-devctl contract 1'\n")
    _answers(monkeypatch, CONTRACT_LINE)
    got = plan_helper(
        _helper(), wrapper_path=wrapper, owner_of=NO_OWNER, interpreter="/usr/bin/python3"
    )
    assert not got.install and "did not mark" in got.owner


def test_a_contract_below_the_floor_is_not_good_enough_to_leave(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    wrapper = tmp_path / "hammunition-devctl"
    _write_wrapper(wrapper, wrapper_script("/usr/bin/python3"))
    _answers(monkeypatch, CONTRACT_LINE)
    floor_two = DevctlHelper(modules=["__init__.py", "devctl.py"], min_contract=2)
    got = plan_helper(
        floor_two, wrapper_path=wrapper, owner_of=NO_OWNER, interpreter="/usr/bin/python3"
    )
    assert got.install, "contract 1 does not satisfy a pin that needs 2"


def test_the_engines_old_wrapper_is_replaced_that_is_the_hand_over(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    wrapper = tmp_path / "hammunition-devctl"
    _write_wrapper(
        wrapper,
        "#!/bin/sh\n# Installed by `hammunition hardware apply` (D-056). Do not edit\n"
        'exec /x/python -I -m hammunition.cli.devctl "$@"\n',
    )
    _answers(monkeypatch, None)
    got = plan_helper(
        _helper(), wrapper_path=wrapper, owner_of=NO_OWNER, interpreter="/usr/bin/python3"
    )
    assert got.install and "hardware apply" in got.owner


def test_a_foreign_wrapper_that_answers_nothing_is_not_replaced(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    wrapper = tmp_path / "hammunition-devctl"
    _write_wrapper(wrapper, "#!/bin/sh\nexec /opt/somebody/else\n")
    _answers(monkeypatch, None)
    got = plan_helper(
        _helper(), wrapper_path=wrapper, owner_of=NO_OWNER, interpreter="/usr/bin/python3"
    )
    assert not got.install and "something other than the tray or this engine" in got.owner


# ---------------------------------------------------------------------------
# The gates are `hardware apply`'s
# ---------------------------------------------------------------------------


def _findings(
    monkeypatch: pytest.MonkeyPatch,
    *,
    interpreter: WritabilityRisk | None,
    package: WritabilityRisk | None,
) -> None:
    calls = iter([interpreter, package])

    def fake(path: object, **kw: object) -> WritabilityFinding | None:
        risk = next(calls)
        return None if risk is None else WritabilityFinding(str(path), risk)

    monkeypatch.setattr(polkit, "writable_including_symlink_target", fake)


def test_a_tree_any_account_can_write_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _findings(monkeypatch, interpreter=WritabilityRisk.GROUP_OR_OTHER_WRITABLE, package=None)
    got = plan_helper(
        _helper(), wrapper_path=tmp_path / "h", owner_of=NO_OWNER, interpreter="/v/bin/python"
    )
    assert got.must_refuse and not got.needs_confirmation


def test_a_venv_only_its_owner_can_write_is_confirmed_never_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _findings(
        monkeypatch,
        interpreter=WritabilityRisk.OWNED_BY_NON_ROOT,
        package=WritabilityRisk.OWNED_BY_NON_ROOT,
    )
    got = plan_helper(
        _helper(), wrapper_path=tmp_path / "h", owner_of=NO_OWNER, interpreter="/v/bin/python"
    )
    assert got.needs_confirmation and not got.must_refuse
    assert len(got.confirmable_paths) == 2


def test_a_helper_left_alone_is_never_gated(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Nothing is written, so no interpreter is baked in and none is checked."""
    _findings(monkeypatch, interpreter=WritabilityRisk.GROUP_OR_OTHER_WRITABLE, package=None)
    got = plan_helper(
        _helper(),
        wrapper_path=tmp_path / "h",
        owner_of=lambda _p: "hammunition-devctl",
        interpreter="/v/bin/python",
    )
    assert not got.install and not got.must_refuse and not got.confirmable_paths


# ---------------------------------------------------------------------------
# The steps
# ---------------------------------------------------------------------------


def _steps(tmp_path: Path, **kw: object) -> list[Action | Command]:
    helper = _helper(["__init__.py", "devctl.py", "run.py"])
    plan = plan_helper(
        helper,
        wrapper_path=tmp_path / "none",
        owner_of=NO_OWNER,
        interpreter="/engine/venv/bin/python",
    )
    return helper_steps(
        name="hammunition-tray",
        helper=helper,
        plan=plan,
        src=tmp_path / "src",
        staging=tmp_path / "stage",
        prefix=tmp_path / "prefix",
        policy_dest=tmp_path / "polkit" / "x.policy",
        **kw,  # type: ignore[arg-type]
    )


def test_the_plan_prints_every_file_root_will_run_and_the_interpreter(tmp_path: Path) -> None:
    steps = _steps(tmp_path)
    commands = [s for s in steps if isinstance(s, Command)]
    installs = [c.argv for c in commands if c.argv[:2] == ("install", "-D")]
    prefix = tmp_path / "prefix"
    assert installs == [
        (
            "install",
            "-D",
            "-m",
            "0755",
            f"{tmp_path}/src/devctl/hammunition-devctl",
            f"{prefix}/lib/hammunition-devctl/hammunition-devctl",
        ),
        (
            "install",
            "-D",
            "-m",
            "0644",
            f"{tmp_path}/src/devctl/hammunition_devctl/__init__.py",
            f"{prefix}/lib/hammunition-devctl/hammunition_devctl/__init__.py",
        ),
        (
            "install",
            "-D",
            "-m",
            "0644",
            f"{tmp_path}/src/devctl/hammunition_devctl/devctl.py",
            f"{prefix}/lib/hammunition-devctl/hammunition_devctl/devctl.py",
        ),
        (
            "install",
            "-D",
            "-m",
            "0644",
            f"{tmp_path}/src/devctl/hammunition_devctl/run.py",
            f"{prefix}/lib/hammunition-devctl/hammunition_devctl/run.py",
        ),
        (
            "install",
            "-D",
            "-m",
            "0755",
            f"{tmp_path}/stage/wrapper",
            f"{prefix}/libexec/hammunition-devctl",
        ),
        ("install", "-D", "-m", "0644", f"{tmp_path}/stage/policy", f"{tmp_path}/polkit/x.policy"),
    ]
    stage = next(s for s in steps if isinstance(s, Action) and s.kind == "devctl-stage")
    assert "/engine/venv/bin/python" in stage.detail, (
        "the interpreter is disclosed before it is written"
    )


def test_every_file_install_is_in_the_form_the_uninstall_attribution_reads(tmp_path: Path) -> None:
    """`install -D -m MODE SRC DEST`, six words: the shape
    files_installed_by_hammunition attributes, so removal rests on the log."""
    for step in _steps(tmp_path):
        if isinstance(step, Command) and step.argv[:2] == ("install", "-D"):
            assert step.argv[2] == "-m" and len(step.argv) == 6


def test_old_modules_are_cleared_before_the_new_ones_land(tmp_path: Path) -> None:
    argvs = [s.argv for s in _steps(tmp_path) if isinstance(s, Command)]
    clear = argvs.index(
        ("rm", "-rf", "--", f"{tmp_path}/prefix/lib/hammunition-devctl/hammunition_devctl")
    )
    first_module = next(i for i, a in enumerate(argvs) if a[-1].endswith("/__init__.py"))
    assert clear < first_module


def test_a_helper_left_alone_is_one_step_that_names_the_owner(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _answers(monkeypatch, CONTRACT_LINE)
    helper = _helper()
    plan = plan_helper(
        helper,
        wrapper_path=tmp_path / "none",
        owner_of=lambda _p: "hammunition-devctl",
        interpreter="/x/python",
    )
    steps = helper_steps(
        name="hammunition-tray",
        helper=helper,
        plan=plan,
        src=tmp_path,
        staging=tmp_path / "s",
        prefix=tmp_path,
    )
    assert len(steps) == 1 and isinstance(steps[0], Action)
    assert steps[0].kind == "devctl-helper-kept"
    assert "hammunition-devctl package (apt)" in steps[0].detail
    assert "installs nothing of it" in steps[0].detail


def test_the_verify_step_fails_loudly_when_the_wrapper_answers_nothing(tmp_path: Path) -> None:
    steps = _steps(tmp_path, probe=lambda _path: None)
    verify = steps[-1]
    assert isinstance(verify, Action) and verify.kind == "devctl-verify"
    from hammunition.backends import BackendError

    # What the install steps would have written, so the read-back reaches the probe.
    wrapper = tmp_path / "prefix" / "libexec" / "hammunition-devctl"
    wrapper.parent.mkdir(parents=True)
    wrapper.write_text(
        wrapper_script(
            "/engine/venv/bin/python",
            str(tmp_path / "prefix/lib/hammunition-devctl/hammunition-devctl"),
        )
    )
    (tmp_path / "polkit").mkdir()
    (tmp_path / "polkit" / "x.policy").write_text(polkit.policy_xml())
    with pytest.raises(BackendError, match="does not answer --version"):
        verify.perform()


def test_under_prefix_is_the_identity_for_the_real_prefix() -> None:
    assert under_prefix(HELPER_PATH, Path("/usr/local")) == Path(HELPER_PATH)
    assert under_prefix(POLICY_PATH, Path("/tmp/x")) == Path(POLICY_PATH)


# ---------------------------------------------------------------------------
# Run it: the wrapper this engine writes, against the pinned tree
# ---------------------------------------------------------------------------


_ROOT_SKIP = pytest.mark.skipif(
    os.geteuid() == 0,
    reason=(
        "run as root, the helper refuses a tree below a world-writable directory (/tmp) -- "
        "its own safety gate, which this test cannot satisfy from a temporary directory; the "
        "unprivileged `make check` run is the one that proves the answer"
    ),
)


@_ROOT_SKIP
def test_the_installed_wrapper_answers_the_contract_line_against_the_pinned_tree(
    pinned_tray: Path, pinned_tray_archive: Path, helper_block: DevctlHelper, tmp_path: Path
) -> None:
    """The steps run for real into a temporary prefix: stage, copy, wrapper,
    policy, then `--version` through the wrapper, the way pkexec's caller does."""
    prefix = tmp_path / "prefix"
    policy = tmp_path / "polkit" / "act.policy"
    plan = plan_helper(
        helper_block,
        wrapper_path=prefix / "libexec" / "hammunition-devctl",
        owner_of=NO_OWNER,
        interpreter=sys.executable,
    )
    assert plan.install
    steps = helper_steps(
        name="hammunition-tray",
        helper=helper_block,
        plan=plan,
        src=pinned_tray,
        staging=tmp_path / "stage",
        prefix=prefix,
        policy_dest=policy,
        probe=_run_version,
        archive=lambda: pinned_tray_archive,
    )
    assert any(isinstance(s, Action) and s.kind == "devctl-source-verify" for s in steps)
    runner = SubprocessRunner()
    outcomes = []
    for step in steps:
        if isinstance(step, Action):
            outcomes.append(step.perform())
        else:
            result = runner.run(step)
            assert result.ok, f"{step.argv}: {result.stderr}"
    wrapper = prefix / "libexec" / "hammunition-devctl"
    assert (
        subprocess.run(
            [str(wrapper), "--version"], capture_output=True, text=True, check=True, cwd="/"
        ).stdout.strip()
        == CONTRACT_LINE
    )
    assert outcomes[-1].endswith(f"answers {CONTRACT_LINE!r}")
    assert wrapper.read_text() == wrapper_script(
        sys.executable, str(prefix / "lib" / "hammunition-devctl" / ENTRY_NAME)
    )
    assert policy.read_text() == polkit.policy_xml()
    assert (wrapper.stat().st_mode & 0o777) == 0o755
    assert not os.access(
        prefix / "lib" / "hammunition-devctl" / "hammunition_devctl" / "run.py", os.X_OK
    )
    assert sorted(
        p.name for p in (prefix / "lib" / "hammunition-devctl" / "hammunition_devctl").iterdir()
    ) == sorted(helper_block.modules)


def _run_version(path: str) -> str | None:
    proc = subprocess.run([path, "--version"], capture_output=True, text=True, check=False, cwd="/")
    line = proc.stdout.strip()
    return (
        line if proc.returncode == 0 and line.startswith("hammunition-devctl contract ") else None
    )


def test_the_constants_repeated_to_keep_the_module_a_leaf_equal_the_polkit_modules() -> None:
    """devctl_helper repeats the two paths so the backends can import it without
    importing `hammunition.hardware`; this is what stops the copies drifting."""
    from hammunition import devctl_helper

    assert devctl_helper.HELPER_PATH == polkit.HELPER_PATH
    assert devctl_helper.POLICY_PATH == polkit.POLICY_PATH


# ---------------------------------------------------------------------------
# Review findings (2026-10-02): the staging directory, the copy, and a package
# ---------------------------------------------------------------------------


def test_staging_never_writes_or_unlinks_through_a_symlink(tmp_path: Path) -> None:
    """Run as root the engine writes into the operator's build directory: a
    symlink put where the staging directory should be must not send that
    write, or the `unlink` before it, anywhere else."""
    victim = tmp_path / "victim"
    victim.mkdir()
    (victim / "wrapper").write_text("must survive")
    (tmp_path / "stage").symlink_to(victim)
    stage = next(s for s in _steps(tmp_path) if isinstance(s, Action) and s.kind == "devctl-stage")
    stage.perform()
    assert (victim / "wrapper").read_text() == "must survive"
    assert not (tmp_path / "stage").is_symlink()
    assert (tmp_path / "stage" / "wrapper").read_text().startswith("#!/bin/sh")
    assert ((tmp_path / "stage").stat().st_mode & 0o777) == 0o700
    assert ((tmp_path / "stage" / "wrapper").stat().st_mode & 0o777) == 0o600


def test_a_package_helper_that_answers_no_contract_is_refused_at_plan_time(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _answers(monkeypatch, None)
    helper = _helper()
    plan = plan_helper(
        helper,
        wrapper_path=tmp_path / "none",
        owner_of=lambda _p: "hammunition-devctl",
        interpreter="/x/python",
    )
    assert plan.problem is not None and "never writes over a package's file" in plan.problem
    from hammunition.backends import BackendError

    with pytest.raises(BackendError, match="upgrade or remove hammunition-devctl"):
        helper_steps(
            name="t",
            helper=helper,
            plan=plan,
            src=tmp_path,
            staging=tmp_path / "s",
            prefix=tmp_path,
        )


def _run_through(steps: list[Action | Command], *, stop_before: str | None = None) -> None:
    runner = SubprocessRunner()
    for step in steps:
        if isinstance(step, Action):
            if step.kind == stop_before:
                return
            step.perform()
        else:
            result = runner.run(step)
            assert result.ok, f"{step.argv}: {result.stderr}"


def _real_steps(
    tmp_path: Path, pinned_tray: Path, pinned_tray_archive: Path, helper_block: DevctlHelper
) -> list[Action | Command]:
    prefix = tmp_path / "prefix"
    plan = plan_helper(
        helper_block,
        wrapper_path=prefix / "libexec" / "hammunition-devctl",
        owner_of=NO_OWNER,
        interpreter=sys.executable,
    )
    return helper_steps(
        name="hammunition-tray",
        helper=helper_block,
        plan=plan,
        src=pinned_tray,
        staging=tmp_path / "stage",
        prefix=prefix,
        policy_dest=tmp_path / "polkit" / "act.policy",
        probe=_run_version,
        archive=lambda: pinned_tray_archive,
    )


def test_code_that_changed_between_unpack_and_copy_stops_before_the_wrapper(
    tmp_path: Path, pinned_tray: Path, pinned_tray_archive: Path, helper_block: DevctlHelper
) -> None:
    """The archive is hashed when fetched; what root copies is the unpacked tree
    in the operator's cache. The installed files are read back against the
    archive's own bytes before the wrapper polkit authorises exists."""
    from hammunition.backends import BackendError

    tampered = pinned_tray / "devctl" / "hammunition_devctl" / "devctl.py"
    original = tampered.read_bytes()
    tampered.write_bytes(original + b"\nimport os; os.system('id')\n")
    try:
        steps = _real_steps(tmp_path, pinned_tray, pinned_tray_archive, helper_block)
        with pytest.raises(
            BackendError, match=r"differs from devctl/hammunition_devctl/devctl\.py"
        ):
            _run_through(steps)
    finally:
        tampered.write_bytes(original)
    assert not (tmp_path / "prefix" / "libexec" / "hammunition-devctl").exists(), (
        "the wrapper must not exist when the code failed its check"
    )


def test_a_wrapper_swapped_after_staging_fails_the_final_check(
    tmp_path: Path, pinned_tray: Path, pinned_tray_archive: Path, helper_block: DevctlHelper
) -> None:
    from hammunition.backends import BackendError

    steps = _real_steps(tmp_path, pinned_tray, pinned_tray_archive, helper_block)
    _run_through(steps, stop_before="devctl-verify")
    wrapper = tmp_path / "prefix" / "libexec" / "hammunition-devctl"
    wrapper.write_text("#!/bin/sh\nexec /bin/sh\n")
    verify = steps[-1]
    assert isinstance(verify, Action) and verify.kind == "devctl-verify"
    with pytest.raises(BackendError, match="is not what was staged for it"):
        verify.perform()
