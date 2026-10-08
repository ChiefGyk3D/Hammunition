# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later
# ruff: noqa: F811

"""An offline source build has no network.  #381, Task 13 fix round 1.

Only the pinned tarball comes from the Bunker. A Makefile that runs curl must
fail, so every offline build command runs in a fresh network namespace
(``bwrap --unshare-net``, else ``unshare -rn``). With neither usable the offline
source build is refused at plan time. Online is untouched.
"""

from __future__ import annotations

import importlib
import shutil
import socket
import subprocess
import sys
import threading
from pathlib import Path
from subprocess import CompletedProcess
from typing import Any

import pytest

from bunker_fixtures import artifact
from hammunition import netiso
from hammunition.backends.base import Action, BackendError, Command
from hammunition.backends.source import SourceBackend
from hammunition.fetch import Fetcher
from hammunition.manifest.schema import PackageManifest
from hammunition.plan import InstallPlan, PlannedPackage, offline_payload_blockers
from test_offline_context import TARGET, apt_state, enrol_file_bunker, machine, run  # noqa: F401
from test_offline_guard import SRC_BODY, SRC_PIN, payload_catalog  # noqa: F401

cli = importlib.import_module("hammunition.cli.main")

BWRAP = ("bwrap", "--unshare-net", "--dev-bind", "/", "/", "--")


def _result(code: int) -> CompletedProcess[bytes]:
    return CompletedProcess(args=[], returncode=code, stdout=b"", stderr=b"")


# -- detection and wrapping ---------------------------------------------------


def test_wrap_is_exact_for_each_sandbox_and_privilege() -> None:
    argv = ("make", "-j2")
    assert netiso.wrap(argv, "bwrap", privileged=False) == (*BWRAP, "make", "-j2")
    assert netiso.wrap(argv, "bwrap", privileged=True) == (*BWRAP, "make", "-j2")
    assert netiso.wrap(argv, "unshare", privileged=False) == ("unshare", "-rn", "--", "make", "-j2")
    # Run as root through sudo, a user namespace is not needed (and "-r" would
    # map root to root for nothing).
    assert netiso.wrap(argv, "unshare", privileged=True) == ("unshare", "-n", "--", "make", "-j2")


def test_an_unknown_sandbox_is_refused() -> None:
    with pytest.raises(ValueError, match="sandbox"):
        netiso.wrap(("make",), "chroot", privileged=False)


@pytest.mark.parametrize(
    ("which", "codes", "expected"),
    [
        ({"bwrap", "unshare"}, {"bwrap": 0, "unshare": 0}, "bwrap"),
        ({"bwrap", "unshare"}, {"bwrap": 1, "unshare": 0}, "unshare"),
        ({"unshare"}, {"unshare": 0}, "unshare"),
        ({"bwrap"}, {"bwrap": 0}, "bwrap"),
        ({"bwrap", "unshare"}, {"bwrap": 1, "unshare": 1}, None),
        (set(), {}, None),
    ],
)
def test_detect_picks_the_first_sandbox_that_really_works(
    monkeypatch: pytest.MonkeyPatch, which: set[str], codes: dict[str, int], expected: str | None
) -> None:
    monkeypatch.setattr(
        "hammunition.netiso.shutil.which", lambda name: f"/bin/{name}" if name in which else None
    )
    asked: list[tuple[str, ...]] = []

    def fake(argv: Any, **kwargs: Any) -> CompletedProcess[bytes]:
        asked.append(tuple(argv))
        return _result(codes[argv[0]])

    assert netiso.detect(fake) == expected
    assert all(a[-1] == "true" for a in asked), "it probes with a harmless command"


def test_detect_survives_a_probe_that_raises_or_hangs(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("hammunition.netiso.shutil.which", lambda name: f"/bin/{name}")

    def broken(argv: Any, **kwargs: Any) -> CompletedProcess[bytes]:
        if argv[0] == "bwrap":
            raise OSError("exec format error")
        raise subprocess.TimeoutExpired(argv, 10)

    assert netiso.detect(broken) is None


# -- the source backend -------------------------------------------------------


def _manifest() -> PackageManifest:
    return PackageManifest.model_validate(
        {
            "name": "thing",
            "version": "1.0",
            "summary": "A thing built from source",
            "categories": ["digital-modes"],
            "install": [
                {
                    "install": {
                        "method": "source",
                        "source": SRC_PIN.model_dump(exclude_none=True),
                        "build_system": "autotools",
                    }
                }
            ],
            "update": {"probe": {"method": "none"}},
            "documentation": {
                "what_it_does": "Does a thing for the purposes of testing the backend.",
                "why_you_want_it": "Because the source backend needs a manifest to act on.",
                "upstream_url": "https://example.invalid/",
            },
        }
    )


def _backend(tmp_path: Path, *, offline: bool, isolation: str | None) -> SourceBackend:
    fetcher = Fetcher(
        tmp_path / "cache", offline=offline, mirror="http://bunker.invalid" if offline else None
    )
    return SourceBackend(
        fetcher,
        build_root=tmp_path / "build",
        prefix=tmp_path / "prefix",
        isolation=isolation,
    )


def _commands(backend: SourceBackend) -> list[Command]:
    manifest = _manifest()
    return [s for s in backend.steps(manifest, manifest.install[0]) if isinstance(s, Command)]


@pytest.mark.parametrize("kind", ["bwrap", "unshare"])
def test_every_offline_build_command_runs_inside_the_sandbox(tmp_path: Path, kind: str) -> None:
    commands = _commands(_backend(tmp_path, offline=True, isolation=kind))
    assert [c.argv[-3:] for c in commands if "configure" in " ".join(c.argv)]
    for command in commands:
        prefix = netiso.wrap(("X",), kind, privileged=command.requires_root)[:-1]
        assert command.argv[: len(prefix)] == prefix, command.argv
    # the real build command is still there, after the sandbox
    assert any(
        c.argv[len(netiso.wrap(("X",), kind, privileged=c.requires_root)) - 1] == "./configure"
        for c in commands
    )


def test_the_sandbox_is_part_of_the_plan_text(tmp_path: Path) -> None:
    commands = _commands(_backend(tmp_path, offline=True, isolation="unshare"))
    assert any(
        c.display(euid=1000).startswith("cd ") and "unshare -rn -- " in c.display(euid=1000)
        for c in commands
    )


def test_the_root_install_step_is_sandboxed_under_sudo(tmp_path: Path) -> None:
    backend = SourceBackend(
        Fetcher(tmp_path / "cache", offline=True, mirror="http://bunker.invalid"),
        build_root=tmp_path / "build",
        isolation="unshare",
    )  # the default prefix needs root
    manifest = _manifest()
    install = [s for s in backend.steps(manifest, manifest.install[0]) if isinstance(s, Command)][
        -1
    ]
    assert install.requires_root
    assert install.argv[:4] == ("unshare", "-n", "--", "make")
    assert install.argv_for(euid=1000)[0] == "sudo"


def test_online_builds_are_not_sandboxed_even_when_a_sandbox_is_known(tmp_path: Path) -> None:
    for isolation in (None, "bwrap", "unshare"):
        for command in _commands(
            _backend(tmp_path / str(isolation), offline=False, isolation=isolation)
        ):
            assert command.argv[0] not in {"bwrap", "unshare"}, command.argv


def test_the_unpack_and_tree_steps_are_not_wrapped(tmp_path: Path) -> None:
    manifest = _manifest()
    steps = _backend(tmp_path, offline=True, isolation="bwrap").steps(manifest, manifest.install[0])
    assert [s.kind for s in steps if isinstance(s, Action)][:2] == ["fetch", "extract"]


def test_offline_with_no_sandbox_the_backend_refuses_to_plan_a_build(tmp_path: Path) -> None:
    with pytest.raises(BackendError, match="network isolation"):
        _commands(_backend(tmp_path, offline=True, isolation=None))


# -- plan time -----------------------------------------------------------------


def _planned() -> PlannedPackage:
    manifest = _manifest()
    return PlannedPackage(manifest, manifest.install[0], (), requested_by=("requested",))


def test_the_plan_refuses_an_offline_source_build_without_isolation() -> None:
    plan = InstallPlan(TARGET, (_planned(),))
    found = offline_payload_blockers(
        plan, frozenset(), cached=lambda a: True, deb_unmet=lambda u: [], isolated=False
    )
    assert [b.subject for b in found] == ["thing"]
    assert (
        "network" in found[0].reason and "bwrap" in found[0].reason and "unshare" in found[0].reason
    )
    ok = offline_payload_blockers(
        plan, frozenset(), cached=lambda a: True, deb_unmet=lambda u: [], isolated=True
    )
    assert ok == []
    built = offline_payload_blockers(
        plan, frozenset({"thing"}), cached=lambda a: True, deb_unmet=lambda u: [], isolated=False
    )
    assert built == []


def test_cli_offline_install_refuses_a_source_unit_when_no_sandbox_works(
    payload_catalog: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    apt_state(monkeypatch, installed="1.0")
    enrol_file_bunker(
        tmp_path, [artifact("fixture-src", f"{SRC_PIN.sha256}/fixture-src-1.0.tar.gz", SRC_BODY)]
    )
    monkeypatch.setattr(cli.netiso, "detect", lambda *a, **k: None)
    rc, out, err = run(capsys, payload_catalog, "install", "--offline", "--dry-run", "fixture-src")
    assert rc == cli.EXIT_UNPLANNABLE and out == ""
    assert "fixture-src" in err and "no network isolation" in err


def test_cli_offline_install_plans_the_sandboxed_build_when_one_works(
    payload_catalog: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    apt_state(monkeypatch, installed="1.0")
    enrol_file_bunker(
        tmp_path, [artifact("fixture-src", f"{SRC_PIN.sha256}/fixture-src-1.0.tar.gz", SRC_BODY)]
    )
    monkeypatch.setattr(cli.netiso, "detect", lambda *a, **k: "unshare")
    rc, out, err = run(capsys, payload_catalog, "install", "--offline", "--dry-run", "fixture-src")
    assert rc == 0, err
    assert "unshare -rn -- ./configure" in out and "unshare -n -- make install" in out
    assert "network" in out.lower()


def test_cli_online_install_does_not_probe_or_wrap(
    payload_catalog: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    apt_state(monkeypatch, installed="1.0")

    def never(*a: object, **k: object) -> None:
        raise AssertionError("an online run probed for a sandbox")

    monkeypatch.setattr(cli.netiso, "detect", never)
    rc, out, err = run(capsys, payload_catalog, "install", "--dry-run", "fixture-src")
    assert rc == 0, err
    assert "unshare" not in out and "bwrap" not in out


# -- a real socket --------------------------------------------------------------

PROBE = (
    "import socket,sys\n"
    "s=socket.socket()\n"
    "s.settimeout(3)\n"
    "try:\n"
    "    s.connect(('127.0.0.1',int(sys.argv[1])))\n"
    "    print('connected')\n"
    "except OSError:\n"
    "    print('blocked')\n"
)


def _listening() -> tuple[socket.socket, int]:
    server = socket.socket()
    server.bind(("127.0.0.1", 0))
    server.listen(4)
    threading.Thread(target=lambda: [server.accept() for _ in range(4)], daemon=True).start()
    return server, server.getsockname()[1]


def test_a_real_sandbox_blocks_a_socket_the_unsandboxed_command_can_open() -> None:
    kind = netiso.detect()
    if kind is None:
        pytest.skip("neither bwrap --unshare-net nor unshare -rn works on this machine")
    server, port = _listening()
    try:
        argv = (sys.executable, "-I", "-c", PROBE, str(port))
        plain = subprocess.run(argv, capture_output=True, text=True, timeout=30, check=False)
        assert plain.stdout.strip() == "connected", plain
        boxed = subprocess.run(
            netiso.wrap(argv, kind, privileged=False),
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        assert boxed.stdout.strip() == "blocked", boxed
    finally:
        server.close()
    assert shutil.which(kind) is not None
