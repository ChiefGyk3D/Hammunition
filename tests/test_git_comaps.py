# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""The git backend's build fields, as CoMaps uses them.  D-069.

A tag checked against the commit it must resolve to; submodules checked out
at their gitlinks and read back; a hash-pinned build Python on the PATH of the
prepare, configure and compile steps and nothing else; an upstream prepare
script whose files are checked, because CoMaps' symbol generation exits 0 with
none; and the files the install rule leaves out, installed after it. Every
command goes through a recording runner: nothing is cloned or built here.
"""

from __future__ import annotations

import hashlib
import os
import shutil
from collections.abc import Iterator
from contextlib import contextmanager
from io import BytesIO
from pathlib import Path
from typing import IO, Any

import pytest

from hammunition.backends import (
    Action,
    BackendError,
    Command,
    CommandResult,
    GitBackend,
    RecordingRunner,
)
from hammunition.fetch import Fetcher
from hammunition.manifest.schema import GitInstall, PackageManifest

COMMIT = "72632e4de65a98dfed827d8e447f0287168639d0"
OTHER = "0" * 40
WORLD = b"a world map, as far as this test is concerned\n"
PROTOBUF = "protobuf==3.20.3 --hash=sha256:" + "b" * 64


def _manifest(**install: Any) -> PackageManifest:
    block: dict[str, Any] = {
        "method": "git",
        "repo": "https://codeberg.org/comaps/comaps.git",
        "ref": "v2026.08.31-14",
        "commit": COMMIT,
        "build_system": "cmake",
        **install,
    }
    return PackageManifest.model_validate(
        {
            "name": "comaps",
            "version": "2026.08.31-14",
            "summary": "An offline map built from a pinned tag",
            "categories": ["navigation-maps"],
            "install": [{"install": block, "build_depends": ["cmake"]}],
            "update": {"probe": {"method": "github_tags"}},
            "documentation": {
                "what_it_does": "Does a thing for the purposes of testing the backend.",
                "why_you_want_it": "Because the git backend needs a manifest to act on.",
                "upstream_url": "https://example.invalid/",
            },
        }
    )


class _Transport:
    def __init__(self, body: bytes) -> None:
        self.body = body
        self.requested: list[str] = []

    @contextmanager
    def open(self, url: str) -> Iterator[IO[bytes]]:
        self.requested.append(url)
        yield BytesIO(self.body)


def _backend(
    tmp_path: Path, runner: Any | None = None, body: bytes = WORLD
) -> tuple[GitBackend, Any]:
    runner = runner or RecordingRunner()
    fetcher = Fetcher(tmp_path / "cache", transport=_Transport(body))
    backend = GitBackend(
        runner=runner,
        build_root=tmp_path / "build",
        prefix=Path("/usr/local"),
        jobs=3,
        fetcher=fetcher,
    )
    return backend, runner


def _steps(backend: GitBackend, manifest: PackageManifest) -> list[Action | Command]:
    return backend.steps(manifest, manifest.install[0])


def _argvs(steps: list[Action | Command]) -> list[tuple[str, ...]]:
    return [s.argv for s in steps if isinstance(s, Command)]


class _Answers:
    """A runner answering `rev-parse HEAD` and `submodule status`."""

    def __init__(self, head: str = COMMIT, status: str = "") -> None:
        self.head = head
        self.status = status
        self.commands: list[Command] = []

    def run(self, command: Command) -> CommandResult:
        self.commands.append(command)
        if command.argv[-2:] == ("rev-parse", "HEAD"):
            return CommandResult(command.argv, 0, self.head + "\n", "")
        if command.argv[-3:] == ("submodule", "status", "--recursive"):
            return CommandResult(command.argv, 0, self.status, "")
        return CommandResult(command.argv, 0, "", "")


def _perform(steps: list[Action | Command], kind: str) -> str:
    [action] = [s for s in steps if isinstance(s, Action) and s.kind == kind]
    return action.perform()


# -- the tag and its commit ---------------------------------------------------


def test_a_tag_at_its_commit_is_confirmed(tmp_path: Path) -> None:
    backend, _ = _backend(tmp_path, _Answers(head=COMMIT))
    steps = _steps(backend, _manifest())
    assert COMMIT in _perform(steps, "verify-pin")


def test_a_re_cut_tag_is_refused(tmp_path: Path) -> None:
    backend, _ = _backend(tmp_path, _Answers(head=OTHER))
    steps = _steps(backend, _manifest())
    with pytest.raises(BackendError) as caught:
        _perform(steps, "verify-pin")
    assert COMMIT in str(caught.value) and OTHER in str(caught.value)
    assert "re-cut" in str(caught.value)


def test_the_plan_line_names_the_commit(tmp_path: Path) -> None:
    backend, _ = _backend(tmp_path)
    [pin] = [
        s for s in _steps(backend, _manifest()) if isinstance(s, Action) and s.kind == "verify-pin"
    ]
    assert COMMIT in pin.detail


# -- submodules ---------------------------------------------------------------


GOOD = (
    " 1111111111111111111111111111111111111111 3party/boost (boost-1.85.0)\n"
    " 2222222222222222222222222222222222222222 3party/icu/icu (release-76-1)\n"
)


def test_without_submodules_nothing_is_asked(tmp_path: Path) -> None:
    backend, _ = _backend(tmp_path)
    argvs = _argvs(_steps(backend, _manifest()))
    assert not [a for a in argvs if "submodule" in a]


def test_submodules_are_fetched_shallow_after_the_pin(tmp_path: Path) -> None:
    backend, _ = _backend(tmp_path)
    steps = _steps(backend, _manifest(submodules=True))
    src = str(tmp_path / "build" / f"comaps-{'v2026.08.31-14'[:12]}" / "src")
    update = ("git", "-C", src, "submodule", "update", "--init", "--recursive", "--depth", "1")
    argvs = _argvs(steps)
    assert update in argvs
    kinds = [s.kind if isinstance(s, Action) else s.argv[:4] for s in steps]
    assert kinds.index("verify-pin") < kinds.index(update[:4])
    assert kinds.index(update[:4]) < kinds.index("verify-submodules")


def test_every_submodule_at_its_gitlink_is_confirmed(tmp_path: Path) -> None:
    backend, _ = _backend(tmp_path, _Answers(status=GOOD))
    outcome = _perform(_steps(backend, _manifest(submodules=True)), "verify-submodules")
    assert "2 submodule(s)" in outcome


@pytest.mark.parametrize(
    ("line", "why"),
    [
        ("-3333333333333333333333333333333333333333 3party/protobuf\n", "not checked out"),
        ("+3333333333333333333333333333333333333333 3party/protobuf (v3)\n", "not at"),
        ("U3333333333333333333333333333333333333333 3party/protobuf\n", "conflict"),
    ],
)
def test_a_submodule_off_its_gitlink_is_refused(tmp_path: Path, line: str, why: str) -> None:
    backend, _ = _backend(tmp_path, _Answers(status=GOOD + line))
    with pytest.raises(BackendError) as caught:
        _perform(_steps(backend, _manifest(submodules=True)), "verify-submodules")
    assert "3party/protobuf" in str(caught.value) and why in str(caught.value)


def test_no_submodules_at_all_is_refused(tmp_path: Path) -> None:
    """git exits 0 with nothing to do; the build would then fail far away."""
    backend, _ = _backend(tmp_path, _Answers(status=""))
    with pytest.raises(BackendError, match="no submodule"):
        _perform(_steps(backend, _manifest(submodules=True)), "verify-submodules")


# -- the build Python --------------------------------------------------------


def test_the_build_python_is_a_hashed_venv_in_the_build_directory(tmp_path: Path) -> None:
    backend, _ = _backend(tmp_path)
    steps = _steps(backend, _manifest(build_python=[PROTOBUF]))
    root = tmp_path / "build" / "comaps-v2026.08.31-"
    venv = root / "build-python"
    argvs = _argvs(steps)
    [create] = [a for a in argvs if a[1:3] == ("-m", "venv")]
    assert create[-1] == str(venv)
    [pip] = [a for a in argvs if a[0] == str(venv / "bin" / "pip")]
    assert "--require-hashes" in pip
    requirements = Path(pip[pip.index("-r") + 1])
    staged = _perform(steps, "requirements")
    assert "1 hash-pinned" in staged or "1 pinned" in staged
    assert requirements.read_text() == PROTOBUF + "\n"


def test_the_build_python_is_on_the_path_of_configure_and_compile_only(tmp_path: Path) -> None:
    backend, _ = _backend(tmp_path)
    steps = _steps(backend, _manifest(build_python=[PROTOBUF]))
    venv = tmp_path / "build" / "comaps-v2026.08.31-" / "build-python"
    commands = [s for s in steps if isinstance(s, Command)]
    configure = next(c for c in commands if c.argv[:2] == ("cmake", "--fresh"))
    compile_ = next(c for c in commands if c.argv[:2] == ("cmake", "--build"))
    install = next(c for c in commands if c.argv[:2] == ("cmake", "--install"))
    for command in (configure, compile_):
        assert command.env["VIRTUAL_ENV"] == str(venv)
        assert command.env["PATH"].startswith(f"{venv}/bin:")
    assert "VIRTUAL_ENV" not in install.env


def test_without_build_python_no_venv_is_made(tmp_path: Path) -> None:
    backend, _ = _backend(tmp_path)
    steps = _steps(backend, _manifest())
    assert not [a for a in _argvs(steps) if a[1:3] == ("-m", "venv")]
    configure = next(
        s for s in steps if isinstance(s, Command) and s.argv[:2] == ("cmake", "--fresh")
    )
    assert "VIRTUAL_ENV" not in configure.env


# -- the prepare script -------------------------------------------------------


PREPARE = {
    "script": "configure.sh",
    "args": ["--skip-map-download"],
    "env": {"SKIP_PYTHON_VENV": "1"},
    "produces": ["data/symbols/*/light/symbols.png", "data/drules_proto.bin"],
}


def test_the_prepare_script_runs_in_the_tree_before_configure(tmp_path: Path) -> None:
    backend, _ = _backend(tmp_path)
    steps = _steps(backend, _manifest(prepare=PREPARE, build_python=[PROTOBUF]))
    commands = [s for s in steps if isinstance(s, Command)]
    prepare = next(c for c in commands if c.argv[0] == "./configure.sh")
    assert prepare.argv == ("./configure.sh", "--skip-map-download")
    assert prepare.cwd is not None and prepare.cwd.name == "src"
    assert prepare.env["SKIP_PYTHON_VENV"] == "1"
    assert prepare.env["CMAKE_BUILD_PARALLEL_LEVEL"] == "3"
    assert "VIRTUAL_ENV" in prepare.env
    assert not prepare.requires_root
    order = [s.kind if isinstance(s, Action) else s.argv[0] for s in steps]
    assert order.index("./configure.sh") < order.index("check-prepared")
    assert order.index("check-prepared") < order.index("cmake")


def _tree(tmp_path: Path) -> Path:
    src = tmp_path / "build" / "comaps-v2026.08.31-" / "src"
    (src / "data" / "symbols" / "mdpi" / "light").mkdir(parents=True)
    return src


def test_what_the_script_produced_is_confirmed(tmp_path: Path) -> None:
    backend, _ = _backend(tmp_path)
    src = _tree(tmp_path)
    (src / "data" / "symbols" / "mdpi" / "light" / "symbols.png").write_bytes(b"png")
    (src / "data" / "drules_proto.bin").write_bytes(b"rules")
    outcome = _perform(_steps(backend, _manifest(prepare=PREPARE)), "check-prepared")
    assert "data/drules_proto.bin" in outcome


def test_a_script_that_exited_0_and_made_no_symbols_is_refused(tmp_path: Path) -> None:
    """generate_symbols.sh calls a bare `exit` when optipng is missing."""
    backend, _ = _backend(tmp_path)
    src = _tree(tmp_path)
    (src / "data" / "drules_proto.bin").write_bytes(b"rules")
    (src / "data" / "symbols" / "mdpi" / "light" / "symbols.png").write_bytes(b"")
    with pytest.raises(BackendError) as caught:
        _perform(_steps(backend, _manifest(prepare=PREPARE)), "check-prepared")
    message = str(caught.value)
    assert "data/symbols/*/light/symbols.png" in message
    assert "exited 0" in message


# -- extra files --------------------------------------------------------------


def _world(body: bytes = WORLD) -> dict[str, Any]:
    return {
        "artifact": {
            "url": "https://cdn-fi-1.comaps.app/maps/2026.06.28/260830/World.mwm",
            "sha256": hashlib.sha256(body).hexdigest(),
            "size": len(body),
        },
        "install_as": "share/comaps/data/World.mwm",
    }


BRANDS = {
    "from_tree": "data/categories_brands.txt",
    "install_as": "share/comaps/data/categories_brands.txt",
}


def test_extra_files_install_after_the_build_replacing_any_symlink(tmp_path: Path) -> None:
    backend, _ = _backend(tmp_path)
    steps = _steps(backend, _manifest(extra_files=[_world(), BRANDS]))
    commands = [s for s in steps if isinstance(s, Command)]
    install_at = next(i for i, c in enumerate(commands) if c.argv[:2] == ("cmake", "--install"))
    after = commands[install_at + 1 :]
    world = "/usr/local/share/comaps/data/World.mwm"
    assert ("rm", "-f", "--", world) in [c.argv for c in after]
    [put] = [
        c for c in after if c.argv[:4] == ("install", "-D", "-m", "0644") and c.argv[-1] == world
    ]
    assert put.requires_root
    assert after.index(next(c for c in after if c.argv == ("rm", "-f", "--", world))) < after.index(
        put
    )
    brands = next(
        c for c in after if c.argv[-1].endswith("categories_brands.txt") and c.argv[0] == "install"
    )
    assert brands.argv[-2].endswith("src/data/categories_brands.txt")


def test_an_extra_artifact_is_fetched_verified_and_sized(tmp_path: Path) -> None:
    backend, _ = _backend(tmp_path)
    steps = _steps(backend, _manifest(extra_files=[_world()]))
    [fetch] = [s for s in steps if isinstance(s, Action) and s.kind == "fetch"]
    assert "World.mwm" in fetch.description and str(len(WORLD)) in fetch.detail
    assert "verified" in fetch.perform()


def test_an_extra_artifact_of_the_wrong_size_is_refused(tmp_path: Path) -> None:
    """The digest matched, so the manifest's size is wrong: say so."""
    world = _world()
    world["artifact"]["size"] = len(WORLD) + 1
    backend, _ = _backend(tmp_path)
    [fetch] = [
        s
        for s in _steps(backend, _manifest(extra_files=[world]))
        if isinstance(s, Action) and s.kind == "fetch"
    ]
    with pytest.raises(BackendError, match="bytes"):
        fetch.perform()


def test_an_extra_artifact_needs_a_fetcher(tmp_path: Path) -> None:
    backend = GitBackend(runner=RecordingRunner(), build_root=tmp_path, prefix=Path("/p"), jobs=1)
    with pytest.raises(BackendError, match="fetcher"):
        backend.steps(
            _manifest(extra_files=[_world()]), _manifest(extra_files=[_world()]).install[0]
        )


def test_the_block_type_is_git(tmp_path: Path) -> None:
    assert isinstance(_manifest().install[0].install, GitInstall)


def test_an_extra_file_left_a_symlink_fails_the_effect_check(tmp_path: Path) -> None:
    from hammunition.distro import Target
    from hammunition.execute import build_effects_present, verify_effects
    from hammunition.plan import InstallPlan, PlannedPackage

    m = _manifest(extra_files=[_world()])
    planned = PlannedPackage(manifest=m, block=m.install[0], apt_packages=())
    plan = InstallPlan(target=Target("debian", "13", "x86_64"), packages=(planned,))
    world = tmp_path / "share" / "comaps" / "data" / "World.mwm"
    world.parent.mkdir(parents=True)
    world.symlink_to("world_mwm/260830/World.mwm")
    [check] = [c for c in verify_effects(plan, None, prefix=tmp_path).checks if c.kind == "file"]
    assert not check.confirmed and "symlink" in check.detail
    assert build_effects_present(planned, prefix=tmp_path) is False
    world.unlink()
    world.write_bytes(WORLD)
    [check] = [c for c in verify_effects(plan, None, prefix=tmp_path).checks if c.kind == "file"]
    assert check.confirmed


@pytest.mark.skipif(
    shutil.which("git") is None, reason="needs git on PATH (the container jobs have none)"
)
def test_the_weekly_ref_check_refuses_a_tag_off_its_commit(tmp_path: Path) -> None:
    """scripts/check_pin_reviews.py --verify-refs, against a local repository:
    a tag at its pinned commit passes, and a re-cut one is named."""
    import importlib.util
    import subprocess

    repo = tmp_path / "upstream"
    env = {
        "GIT_AUTHOR_NAME": "t",
        "GIT_AUTHOR_EMAIL": "t@example.invalid",
        "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@example.invalid",
        "PATH": os.environ["PATH"],
        "HOME": str(tmp_path),
    }
    for argv in (
        ("git", "init", "--quiet", str(repo)),
        ("git", "-C", str(repo), "commit", "--quiet", "--allow-empty", "-m", "one"),
        ("git", "-C", str(repo), "tag", "v1"),
    ):
        subprocess.run(argv, check=True, env=env, capture_output=True)
    head = subprocess.run(
        ("git", "-C", str(repo), "rev-parse", "HEAD"), check=True, capture_output=True, text=True
    ).stdout.strip()
    spec = importlib.util.spec_from_file_location(
        "check_pin_reviews",
        Path(__file__).resolve().parent.parent / "scripts" / "check_pin_reviews.py",
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.verify_ref(str(repo), "v1", head) is None
    problem = module.verify_ref(str(repo), "v1", "0" * 40)
    assert problem is not None and head in problem and "0" * 40 in problem


@pytest.mark.skipif(
    shutil.which("git") is None, reason="needs git on PATH (the container jobs have none)"
)
def test_the_ref_check_peels_an_annotated_tag_to_its_commit(tmp_path: Path) -> None:
    """An annotated tag is its own object. FETCH_HEAD after fetching it is the
    tag object's id, not the commit, so a check that compares that id reports
    every correctly pinned annotated tag as missing (librevna, nrsc5, pihpsdr,
    2026-10-02) and, worse, would accept a pin that is the tag object's id.
    The install checks out FETCH_HEAD and compares `rev-parse HEAD`, i.e. the
    commit; the check must compare the same thing."""
    import importlib.util
    import subprocess

    repo = tmp_path / "upstream"
    env = {
        "GIT_AUTHOR_NAME": "t",
        "GIT_AUTHOR_EMAIL": "t@example.invalid",
        "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@example.invalid",
        "PATH": os.environ["PATH"],
        "HOME": str(tmp_path),
    }
    for argv in (
        ("git", "init", "--quiet", str(repo)),
        ("git", "-C", str(repo), "commit", "--quiet", "--allow-empty", "-m", "one"),
        ("git", "-C", str(repo), "tag", "-a", "v1", "-m", "release"),
    ):
        subprocess.run(argv, check=True, env=env, capture_output=True)

    def rev(spec: str) -> str:
        return subprocess.run(
            ("git", "-C", str(repo), "rev-parse", spec), check=True, capture_output=True, text=True
        ).stdout.strip()

    commit, tag_object = rev("v1^{commit}"), rev("v1")
    assert commit != tag_object
    spec = importlib.util.spec_from_file_location(
        "check_pin_reviews",
        Path(__file__).resolve().parent.parent / "scripts" / "check_pin_reviews.py",
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.verify_ref(str(repo), "v1", commit) is None
    problem = module.verify_ref(str(repo), "v1", tag_object)
    assert problem is not None and commit in problem and tag_object in problem


def test_verify_only_checks_changed_manifests(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """The pull-request job passes the changed manifests. A manifest with no git
    block has nothing to fetch (no network here: reaching upstream would fail
    the test), a name not in the catalog is an error so a typo cannot pass, and
    a ref that does not resolve fails the run and is named."""
    import importlib.util

    root = Path(__file__).resolve().parent.parent
    spec = importlib.util.spec_from_file_location(
        "check_pin_reviews", root / "scripts" / "check_pin_reviews.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    from hammunition.manifest.load import load_catalog
    from hammunition.manifest.schema import GitInstall

    catalog = load_catalog(root / "catalog" / "packages")
    no_git = next(
        (
            n
            for n, m in sorted(catalog.items())
            if not any(isinstance(b.install, GitInstall) for b in m.install)
        ),
        None,
    )
    git_unit = next(
        (
            n
            for n, m in sorted(catalog.items())
            if any(isinstance(b.install, GitInstall) for b in m.install)
        ),
        None,
    )
    assert no_git and git_unit
    assert module.verify_only(catalog, [no_git]) == 0
    assert "0 git ref(s) checked" in capsys.readouterr().out
    assert module.verify_only(catalog, ["no-such-unit"]) == 1
    assert "ERROR" in capsys.readouterr().out
    monkeypatch.setattr(module, "verify_ref", lambda repo, ref, commit=None: "boom")
    assert module.verify_only(catalog, [git_unit]) == 1
    assert "MISSING" in capsys.readouterr().out
