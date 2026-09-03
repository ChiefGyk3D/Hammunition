# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""The binary backend, and the archive it actually unpacks.

Eight units in the dispositions wait on this backend and nothing else — three
of D-008's packet core among them — which is what justified writing it
(**D-014**). Most of what follows is about the properties that make installing
somebody else's prebuilt binary defensible at all:

* **Nothing is unverified.** `sha256` is mandatory in the schema and the
  fetcher refuses a mismatch. It matters more here than for a source build,
  because nobody is going to read a `.deb`.
* **A `.deb` goes through apt, never `dpkg -i`.** apt resolves the package's
  dependencies; dpkg installs it and leaves them broken, which is the classic
  way to wedge a machine with a vendor package.
* **An archive that names no `binaries` is refused.** Unpacking one would leave
  a directory in a cache and install nothing, while reporting success.
* **AppImage is refused by name**, because SCOPE.md puts it post-1.0 and a
  silent skip would hide the gap.

The end-to-end test serves a real zip over loopback and executes what it
installed, for the same reason `test_source_build_end_to_end.py` does: a plan
can be perfectly well-formed and still install nothing.
"""

from __future__ import annotations

import hashlib
import http.server
import shutil
import socketserver
import subprocess
import sys
import threading
import zipfile
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from hammunition.backends import (  # noqa: E402
    Action,
    BackendError,
    BinaryBackend,
    Command,
    RecordingRunner,
    SubprocessRunner,
)
from hammunition.distro import Target  # noqa: E402
from hammunition.execute import execute  # noqa: E402
from hammunition.fetch import Fetcher  # noqa: E402
from hammunition.manifest.schema import BinaryInstall, PackageManifest  # noqa: E402
from hammunition.plan import InstallPlan, PlannedPackage  # noqa: E402
from hammunition.state import TransactionLog  # noqa: E402

TARGET = Target(distro="debian", version="13", arch="x86_64")

SCRIPT = "#!/bin/sh\necho 'hammunition installed this'\n"


def _manifest(
    url: str, sha256: str, fmt: str, *, binaries: list[dict[str, str]]
) -> PackageManifest:
    return PackageManifest.model_validate(
        {
            "name": "prebuilt",
            "version": "1.0",
            "summary": "Something upstream already built for us",
            "categories": ["packet"],
            "install": [
                {
                    "install": {
                        "method": "binary",
                        "artifact": {"url": url, "sha256": sha256},
                        "format": fmt,
                        **({"deb_package": "xunit"} if fmt == "deb" else {}),
                    }
                }
            ],
            "binaries": binaries,
            "update": {"probe": {"method": "none"}},
            "documentation": {
                "what_it_does": "Stands in for QtTermTCP, which ships as a prebuilt binary.",
                "why_you_want_it": "Because eight real units install exactly this way.",
                "upstream_url": "https://example.invalid/",
            },
        }
    )


@pytest.fixture
def served_zip(tmp_path: Path) -> Iterator[tuple[str, str]]:
    """Serve a zip containing one executable. Yields (url, sha256)."""
    root = tmp_path / "www"
    root.mkdir()
    archive = root / "prebuilt.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        info = zipfile.ZipInfo("prebuilt-1.0/bin/prebuilt")
        info.external_attr = 0o755 << 16
        zf.writestr(info, SCRIPT)
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()

    class Handler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args: object, **kwargs: object) -> None:
            super().__init__(*args, directory=str(root), **kwargs)  # type: ignore[arg-type]

        def log_message(self, *args: object) -> None:
            """Quiet: the assertions are the output."""

    with socketserver.TCPServer(("127.0.0.1", 0), Handler) as httpd:
        port = httpd.server_address[1]
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        try:
            yield f"http://127.0.0.1:{port}/prebuilt.zip", digest
        finally:
            httpd.shutdown()
            thread.join(timeout=5)


def _backend(tmp_path: Path, runner: Any = None) -> BinaryBackend:
    return BinaryBackend(
        fetcher=Fetcher(tmp_path / "cache"),
        runner=runner or RecordingRunner(),
        build_root=tmp_path / "build",
        prefix=tmp_path / "prefix",
    )


# ---------------------------------------------------------------------------
# What it refuses
# ---------------------------------------------------------------------------


def test_an_appimage_is_refused_by_name(tmp_path: Path) -> None:
    """SCOPE.md puts AppImage post-1.0. Refusing by name keeps the gap visible;
    a silent skip would report a successful run that installed nothing."""
    manifest = _manifest(
        "https://example.invalid/x.AppImage",
        "0" * 64,
        "appimage",
        binaries=[{"produced": "x", "install_as": "x"}],
    )
    block = manifest.install[0].install
    assert isinstance(block, BinaryInstall)
    with pytest.raises(BackendError, match="appimage"):
        _backend(tmp_path).steps(manifest, block)


def test_an_archive_naming_no_binaries_is_refused(tmp_path: Path) -> None:
    """Unpacking it would leave a directory in a cache and install nothing."""
    manifest = _manifest("https://example.invalid/x.zip", "0" * 64, "zip", binaries=[])
    block = manifest.install[0].install
    assert isinstance(block, BinaryInstall)
    with pytest.raises(BackendError, match="names no `binaries`"):
        _backend(tmp_path).steps(manifest, block)


def test_a_single_executable_needs_exactly_one_name(tmp_path: Path) -> None:
    manifest = _manifest(
        "https://example.invalid/x",
        "0" * 64,
        "executable",
        binaries=[{"produced": "a", "install_as": "a"}, {"produced": "b", "install_as": "b"}],
    )
    block = manifest.install[0].install
    assert isinstance(block, BinaryInstall)
    with pytest.raises(BackendError, match="exactly one"):
        _backend(tmp_path).steps(manifest, block)


# ---------------------------------------------------------------------------
# The .deb path
# ---------------------------------------------------------------------------


def test_a_deb_goes_through_apt_and_not_dpkg(tmp_path: Path) -> None:
    """dpkg -i installs the package and leaves its dependencies broken. That is
    the classic way a vendor .deb wedges a machine, and it is why this shells
    out to apt with the file path."""
    manifest = _manifest(
        "https://example.invalid/x.deb",
        "0" * 64,
        "deb",
        binaries=[],
    )
    block = manifest.install[0].install
    assert isinstance(block, BinaryInstall)
    runner = RecordingRunner()
    backend = _backend(tmp_path, runner)
    steps = backend.steps(manifest, block)

    kinds = [s.kind for s in steps if isinstance(s, Action)]
    assert kinds == ["fetch", "install-deb"]
    assert all(isinstance(s, Action) for s in steps), "the .deb path renders no bare Command"

    # Drive the install action directly with a known path.
    fetched = {"path": tmp_path / "thing.deb"}
    backend._install_deb("prebuilt", fetched)
    argv = runner.commands[-1].argv
    assert argv[0] == "apt-get" and "install" in argv
    assert "dpkg" not in argv[0]
    assert str(fetched["path"]) in argv


def test_a_deb_is_simulated_with_the_apt_step_after_its_fetch_and_before_apt_installs(
    tmp_path: Path,
) -> None:
    """The plan's own simulate (D-038) cannot include a file that has not
    been downloaded. So the transaction fetches first, then asks apt about
    the apt packages and the .deb *together*, then installs -- a vendor
    package built for another release is refused with nothing changed."""
    from hammunition.backends import AptBackend
    from hammunition.execute import commands_for

    manifest = _manifest("https://example.invalid/x.deb", "0" * 64, "deb", binaries=[])
    backend = _backend(tmp_path)
    plan = InstallPlan(
        target=TARGET,
        packages=(
            PlannedPackage(manifest=manifest, block=manifest.install[0], apt_packages=("libdep",)),
        ),
        apt_release="stable",
    )
    steps = commands_for(plan, AptBackend(RecordingRunner()), binary=backend)
    labels = [s.kind if isinstance(s, Action) else s.argv[0] for s in steps]
    assert labels == ["fetch", "apt-get", "apt-get", "install-deb"]
    simulate = steps[1]
    assert isinstance(simulate, Command)
    block = manifest.install[0].install
    assert isinstance(block, BinaryInstall)
    deb = str(backend.fetcher.path_for(block.artifact))
    assert simulate.argv == (
        "apt-get",
        "install",
        "--simulate",
        "--yes",
        "--target-release",
        "stable",
        "--",
        deb,
        "libdep",
    )
    assert not simulate.requires_root
    assert ".deb" in simulate.description


def test_apt_refusing_a_deb_is_an_error_not_a_pass(tmp_path: Path) -> None:
    """A vendor .deb built for a different release is the usual cause, and apt
    refusing it is the correct outcome."""
    from hammunition.backends import CommandResult

    class Refusing(RecordingRunner):
        def run(self, command: Command) -> CommandResult:
            super().run(command)
            return CommandResult(
                argv=command.argv, returncode=100, stdout="", stderr="unmet dependencies"
            )

    backend = _backend(tmp_path, Refusing())
    with pytest.raises(BackendError, match="unmet dependencies"):
        backend._install_deb("prebuilt", {"path": tmp_path / "x.deb"})


# ---------------------------------------------------------------------------
# End to end, over a real socket
# ---------------------------------------------------------------------------


needs_a_shell = pytest.mark.skipif(shutil.which("sh") is None, reason="needs /bin/sh")


@needs_a_shell
def test_a_prebuilt_archive_is_fetched_verified_unpacked_and_installed(
    tmp_path: Path, served_zip: tuple[str, str]
) -> None:
    url, digest = served_zip
    manifest = _manifest(
        url, digest, "zip", binaries=[{"produced": "bin/prebuilt", "install_as": "prebuilt"}]
    )
    block = manifest.install[0].install
    assert isinstance(block, BinaryInstall)
    backend = _backend(tmp_path)
    plan = InstallPlan(
        target=TARGET,
        packages=(PlannedPackage(manifest=manifest, block=manifest.install[0], apt_packages=()),),
    )
    log = TransactionLog(tmp_path / "log.jsonl")

    report = execute(backend.steps(manifest, block), SubprocessRunner(), log=log, plan=plan)

    assert report.ok, report.stderr
    # D-031: the run reporting success is not the evidence. The binary is.
    installed = tmp_path / "prefix" / "bin" / "prebuilt"
    assert installed.is_file(), f"nothing was installed into {tmp_path / 'prefix'}"
    output = subprocess.run([str(installed)], capture_output=True, text=True, check=True)
    assert "hammunition installed this" in output.stdout


def test_a_tampered_artifact_installs_nothing(tmp_path: Path, served_zip: tuple[str, str]) -> None:
    """What is served is not what the manifest declared, so nothing is unpacked
    and nothing is installed. The security requirement, over the wire."""
    url, _digest = served_zip
    wrong = hashlib.sha256(b"not what was served").hexdigest()
    manifest = _manifest(
        url, wrong, "zip", binaries=[{"produced": "bin/prebuilt", "install_as": "prebuilt"}]
    )
    block = manifest.install[0].install
    assert isinstance(block, BinaryInstall)
    backend = _backend(tmp_path)
    plan = InstallPlan(
        target=TARGET,
        packages=(PlannedPackage(manifest=manifest, block=manifest.install[0], apt_packages=()),),
    )
    log = TransactionLog(tmp_path / "log.jsonl")

    report = execute(backend.steps(manifest, block), SubprocessRunner(), log=log, plan=plan)

    assert not report.ok
    assert "does not match the digest" in report.stderr
    assert not (tmp_path / "prefix" / "bin" / "prebuilt").exists()
    assert not (tmp_path / "build").exists(), "the archive was unpacked anyway"


def test_a_changed_artifact_unpacks_somewhere_new(tmp_path: Path) -> None:
    """Keyed by digest, so a vendor who republishes under the same URL does not
    get their new files layered over the old ones."""
    backend = _backend(tmp_path)
    first = _manifest(
        "https://example.invalid/x.zip",
        "a" * 64,
        "zip",
        binaries=[{"produced": "x", "install_as": "x"}],
    )
    second = _manifest(
        "https://example.invalid/x.zip",
        "b" * 64,
        "zip",
        binaries=[{"produced": "x", "install_as": "x"}],
    )
    a, b = first.install[0].install, second.install[0].install
    assert isinstance(a, BinaryInstall) and isinstance(b, BinaryInstall)
    assert backend.layout(first, a).root != backend.layout(second, b).root
