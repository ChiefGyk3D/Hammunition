# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""A source build that actually happens.

Every other test of this backend asserts the *shape* of what would run. That is
worth having and it is not the same as knowing the commands work: a plan can be
perfectly well-formed and still fail at the first `./configure`, and CLAUDE.md's
standing lesson is that three visual bugs in the sibling project passed every
test and were found by rendering the page. So this one runs the thing.

It compiles a real C program from a real tarball fetched over a real socket
through the real `UrllibTransport`, then executes the binary that was installed.
Nothing here is mocked except the *contents* of the archive.

Two constraints shaped it:

* **The prefix is a temporary directory, not `/usr/local`.** The test needs no
  root, which is why it can run in the ordinary suite rather than only in the
  container harness. `needs_root_for` returns False for a writable prefix, so
  the install step is genuinely unprivileged rather than pretending to be.
* **The archive is served over loopback HTTP.** A `file://` URL would have been
  simpler and the fetcher refuses one by design — the hardening in
  `UrllibTransport` blocks exactly that. Serving it on `127.0.0.1` respects the
  refusal and exercises more of the real path, and the suite's socket guard
  permits loopback for this reason.
"""

from __future__ import annotations

import hashlib
import http.server
import io
import shutil
import socketserver
import subprocess
import sys
import tarfile
import threading
from collections.abc import Iterator
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from hammunition.backends import SubprocessRunner  # noqa: E402
from hammunition.backends.source import SourceBackend, needs_root_for  # noqa: E402
from hammunition.distro import Target  # noqa: E402
from hammunition.execute import execute  # noqa: E402
from hammunition.fetch import Fetcher  # noqa: E402
from hammunition.manifest.schema import PackageManifest  # noqa: E402
from hammunition.plan import InstallPlan, PlannedPackage  # noqa: E402
from hammunition.state import TransactionLog  # noqa: E402

TARGET = Target(distro="debian", version="13", arch="x86_64")

needs_a_toolchain = pytest.mark.skipif(
    shutil.which("make") is None or shutil.which("cc") is None,
    reason="needs make and a C compiler; the container harness has both",
)

HELLO_C = """#include <stdio.h>
int main(void) { printf("hammunition built this\\n"); return 0; }
"""

# Deliberately plain: `install -D` creates the directory, and PREFIX is the one
# the backend passes. Nothing here needs autotools or cmake to be present.
MAKEFILE = """all: hello

hello: hello.c
\tcc -o hello hello.c

install: hello
\tinstall -D hello $(PREFIX)/bin/hello
"""


@pytest.fixture
def served(tmp_path: Path) -> Iterator[tuple[str, str]]:
    """Serve a source tarball over loopback. Yields (url, sha256)."""
    root = tmp_path / "www"
    root.mkdir()
    archive = root / "hello-1.0.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:
        for name, body in (("hello-1.0/hello.c", HELLO_C), ("hello-1.0/Makefile", MAKEFILE)):
            info = tarfile.TarInfo(name)
            data = body.encode()
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))

    digest = hashlib.sha256(archive.read_bytes()).hexdigest()

    class Handler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args: object, **kwargs: object) -> None:
            super().__init__(*args, directory=str(root), **kwargs)  # type: ignore[arg-type]

        def log_message(self, *args: object) -> None:
            """Quiet: the test's output is the assertion, not the access log."""

    with socketserver.TCPServer(("127.0.0.1", 0), Handler) as httpd:
        port = httpd.server_address[1]
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        try:
            yield f"http://127.0.0.1:{port}/hello-1.0.tar.gz", digest
        finally:
            httpd.shutdown()
            thread.join(timeout=5)


def _manifest(url: str, sha256: str) -> PackageManifest:
    return PackageManifest.model_validate(
        {
            "name": "hello",
            "version": "1.0",
            "summary": "A minimal C program built from source",
            "categories": ["digital-modes"],
            "install": [
                {
                    "install": {
                        "method": "source",
                        "source": {"url": url, "sha256": sha256},
                        "build_system": "make",
                    }
                }
            ],
            "update": {"probe": {"method": "none"}},
            "documentation": {
                "what_it_does": "Prints a line, so the build can be shown to have worked.",
                "why_you_want_it": "Because a plan that is never executed is not evidence.",
                "upstream_url": "https://example.invalid/",
            },
        }
    )


@needs_a_toolchain
def test_a_source_package_is_fetched_verified_built_and_installed(
    tmp_path: Path, served: tuple[str, str]
) -> None:
    url, digest = served
    prefix = tmp_path / "prefix"
    prefix.mkdir()
    assert not needs_root_for(prefix), "a writable prefix must not ask for root"

    manifest = _manifest(url, digest)
    block = manifest.install[0].install
    backend = SourceBackend(
        Fetcher(tmp_path / "cache"),
        build_root=tmp_path / "build",
        prefix=prefix,
        jobs=2,
    )
    plan = InstallPlan(
        target=TARGET,
        packages=(PlannedPackage(manifest=manifest, block=manifest.install[0], apt_packages=()),),
    )
    steps = backend.steps(manifest, block)  # type: ignore[arg-type]
    log = TransactionLog(tmp_path / "log.jsonl")

    report = execute(steps, SubprocessRunner(), log=log, plan=plan)

    assert report.ok, f"the build failed: {report.stderr}"

    # D-031: the run reporting success is not the evidence. The binary is.
    installed = prefix / "bin" / "hello"
    assert installed.is_file(), f"nothing was installed into {prefix}"
    output = subprocess.run([str(installed)], capture_output=True, text=True, check=True)
    assert "hammunition built this" in output.stdout

    events = [e["event"] for e in log.read()]
    assert events.count("action_end") == 2, "fetch and extract should both have completed"
    assert events[-1] == "transaction_end"


@needs_a_toolchain
def test_a_tampered_archive_stops_the_build_before_it_starts(
    tmp_path: Path, served: tuple[str, str]
) -> None:
    """The security requirement, end to end and over the wire: what is served is
    not what the manifest declared, so nothing is unpacked and nothing is built."""
    url, _digest = served
    wrong = hashlib.sha256(b"not what was served").hexdigest()
    prefix = tmp_path / "prefix"
    prefix.mkdir()

    manifest = _manifest(url, wrong)
    backend = SourceBackend(
        Fetcher(tmp_path / "cache"),
        build_root=tmp_path / "build",
        prefix=prefix,
        jobs=2,
    )
    plan = InstallPlan(
        target=TARGET,
        packages=(PlannedPackage(manifest=manifest, block=manifest.install[0], apt_packages=()),),
    )
    steps = backend.steps(manifest, manifest.install[0].install)  # type: ignore[arg-type]
    log = TransactionLog(tmp_path / "log.jsonl")

    report = execute(steps, SubprocessRunner(), log=log, plan=plan)

    assert not report.ok
    assert "does not match the digest" in report.stderr
    assert not (prefix / "bin" / "hello").exists(), "a tampered archive still got built"
    assert not (tmp_path / "build").exists(), "the source tree was unpacked anyway"
    events = [e["event"] for e in log.read()]
    assert "transaction_failed" in events
    assert "transaction_end" not in events
