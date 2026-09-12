# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""The data backend (D-049): offline datasets whose payload is the point.

* **Size and licence are in the plan.** The schema demands both, the fetch
  verifies the declared size against the bytes received, and the rendered
  plan prints them before anything is confirmed.
* **A wrong size is a refused manifest**, not a surprise: the digest still
  matches, so the declaration is the defect, and the transaction stops.
* **Nothing is executed.** A file is copied 0644; an archive is extracted
  through the same guarded extraction the source backend uses.
* **Uninstall can find it.** Every install lands an ``install-data`` action
  whose detail is the destination, which the attribution replay reads back.

The end-to-end test serves real bytes over loopback, for the same reason the
binary backend's does: a plan can be well-formed and install nothing.
"""

from __future__ import annotations

import hashlib
import http.server
import socketserver
import sys
import threading
import zipfile
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from hammunition.backends import Action, BackendError, DataBackend  # noqa: E402
from hammunition.backends.data import human_size  # noqa: E402
from hammunition.fetch import Fetcher  # noqa: E402
from hammunition.manifest.schema import DataInstall, PackageManifest  # noqa: E402
from hammunition.state.uninstall import files_installed_by_hammunition  # noqa: E402

CTY = b"Sov Mil Order of Malta:   15:  28:  EU:   41.90:   -12.43:    -1.0:  1A:\n    1A;\n"


def _manifest(artifacts: list[dict[str, Any]], **extra: Any) -> PackageManifest:
    return PackageManifest.model_validate(
        {
            "name": "country-files",
            "version": "20260906",
            "summary": "The DX-cluster country file",
            "categories": ["logging"],
            "install": [
                {
                    "install": {
                        "method": "data",
                        "artifacts": artifacts,
                        "licence": "AD1C, free with notice",
                        "licence_url": "https://www.country-files.com/",
                        **extra,
                    }
                }
            ],
            "update": {"probe": {"method": "none"}},
            "documentation": {
                "what_it_does": "Turns a callsign prefix into an entity, zone and place.",
                "why_you_want_it": "Every logger wants a current one.",
                "upstream_url": "https://www.country-files.com/",
            },
        }
    )


@pytest.fixture
def served(tmp_path: Path) -> Iterator[tuple[str, dict[str, tuple[str, int]]]]:
    """Serve cty.dat as a bare file and inside a zip. Yields (base_url, {name: (sha256, size)})."""
    root = tmp_path / "www"
    root.mkdir()
    (root / "cty.dat").write_bytes(CTY)
    archive = root / "bigcty.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("cty.dat", CTY)
        zf.writestr("copyright.txt", "AD1C\n")
    facts = {
        name: (hashlib.sha256((root / name).read_bytes()).hexdigest(), (root / name).stat().st_size)
        for name in ("cty.dat", "bigcty.zip")
    }

    class Handler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args: object, **kwargs: object) -> None:
            super().__init__(*args, directory=str(root), **kwargs)  # type: ignore[arg-type]

        def log_message(self, *args: object) -> None:
            """Quiet."""

    with socketserver.TCPServer(("127.0.0.1", 0), Handler) as httpd:
        port = httpd.server_address[1]
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        try:
            yield f"http://127.0.0.1:{port}", facts
        finally:
            httpd.shutdown()
            thread.join(timeout=5)


def _backend(tmp_path: Path) -> DataBackend:
    return DataBackend(fetcher=Fetcher(tmp_path / "cache"), prefix=tmp_path / "prefix")


def _run(steps: list[Any]) -> list[str]:
    outcomes = []
    for step in steps:
        assert isinstance(step, Action)
        outcomes.append(step.perform())
    return outcomes


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------


def test_a_data_file_needs_a_name_and_an_archive_refuses_one() -> None:
    with pytest.raises(ValidationError, match="install_as"):
        _manifest([{"url": "https://x/cty.dat", "sha256": "a" * 64, "size": 10}])
    with pytest.raises(ValidationError, match="archive's members"):
        _manifest(
            [
                {
                    "url": "https://x/c.zip",
                    "sha256": "a" * 64,
                    "size": 10,
                    "format": "zip",
                    "install_as": "c",
                }
            ]
        )


def test_size_licence_and_licence_url_are_mandatory() -> None:
    with pytest.raises(ValidationError):
        _manifest([{"url": "https://x/cty.dat", "sha256": "a" * 64, "install_as": "cty.dat"}])
    with pytest.raises(ValidationError, match="https"):
        _manifest(
            [{"url": "https://x/cty.dat", "sha256": "a" * 64, "size": 1, "install_as": "cty.dat"}],
            licence_url="http://insecure/",
        )


def test_the_shipped_manifest_is_a_data_unit() -> None:
    from hammunition.manifest.load import load_catalog

    m = load_catalog(REPO_ROOT / "catalog" / "packages")["country-files"]
    block = m.install[0].install
    assert isinstance(block, DataInstall)
    assert block.artifacts[0].format == "zip" and block.artifacts[0].size == 339004


def test_human_size_reads_like_a_publisher() -> None:
    assert human_size(353536) == "354 KB"
    assert human_size(690_000_000) == "0.69 GB"
    assert human_size(15_400_000) == "15.4 MB"


# ---------------------------------------------------------------------------
# Steps and the run
# ---------------------------------------------------------------------------


def test_a_file_is_fetched_verified_and_installed_0644(
    served: tuple[str, dict[str, tuple[str, int]]], tmp_path: Path
) -> None:
    base, facts = served
    sha, size = facts["cty.dat"]
    m = _manifest(
        [{"url": f"{base}/cty.dat", "sha256": sha, "size": size, "install_as": "cty.dat"}]
    )
    backend = _backend(tmp_path)
    steps = backend.steps(m, m.install[0].install)  # type: ignore[arg-type]
    assert [s.kind for s in steps] == ["fetch", "install-data"]
    assert f"{size} bytes" in steps[0].detail and "licence" not in steps[0].detail
    dest = tmp_path / "prefix" / "share" / "hammunition" / "data" / "country-files" / "cty.dat"
    assert steps[1].detail == str(dest)
    outcomes = _run(steps)
    assert "verified" in outcomes[0]
    assert dest.read_bytes() == CTY
    assert oct(dest.stat().st_mode & 0o777) == "0o644"


def test_an_archive_is_extracted_into_the_data_directory(
    served: tuple[str, dict[str, tuple[str, int]]], tmp_path: Path
) -> None:
    base, facts = served
    sha, size = facts["bigcty.zip"]
    m = _manifest([{"url": f"{base}/bigcty.zip", "sha256": sha, "size": size, "format": "zip"}])
    backend = _backend(tmp_path)
    steps = backend.steps(m, m.install[0].install)  # type: ignore[arg-type]
    _run(steps)
    data_dir = tmp_path / "prefix" / "share" / "hammunition" / "data" / "country-files"
    assert steps[1].detail == str(data_dir)
    assert (data_dir / "cty.dat").read_bytes() == CTY
    assert (data_dir / "copyright.txt").exists()
    assert oct((data_dir / "cty.dat").stat().st_mode & 0o777) == "0o644"


def test_a_wrong_declared_size_refuses_after_the_digest_matched(
    served: tuple[str, dict[str, tuple[str, int]]], tmp_path: Path
) -> None:
    base, facts = served
    sha, size = facts["cty.dat"]
    m = _manifest(
        [{"url": f"{base}/cty.dat", "sha256": sha, "size": size + 1, "install_as": "cty.dat"}]
    )
    steps = _backend(tmp_path).steps(m, m.install[0].install)  # type: ignore[arg-type]
    with pytest.raises(BackendError, match="declares"):
        steps[0].perform()


def test_a_wrong_digest_refuses_before_anything_is_installed(
    served: tuple[str, dict[str, tuple[str, int]]], tmp_path: Path
) -> None:
    base, facts = served
    _, size = facts["cty.dat"]
    m = _manifest(
        [{"url": f"{base}/cty.dat", "sha256": "b" * 64, "size": size, "install_as": "cty.dat"}]
    )
    steps = _backend(tmp_path).steps(m, m.install[0].install)  # type: ignore[arg-type]
    with pytest.raises(BackendError):
        steps[0].perform()
    assert not (tmp_path / "prefix").exists()


# ---------------------------------------------------------------------------
# The plan says it, and uninstall can find it
# ---------------------------------------------------------------------------


def test_the_plan_prints_size_and_licence_before_the_confirmation(tmp_path: Path) -> None:
    from hammunition.cli.main import render_plan
    from hammunition.distro import Target
    from hammunition.plan import InstallPlan, PlannedPackage

    m = _manifest(
        [
            {
                "url": "https://x/us.mbtiles",
                "sha256": "a" * 64,
                "size": 690_000_000,
                "install_as": "us.mbtiles",
            }
        ],
        licence="ODbL-1.0",
    )
    plan = InstallPlan(
        target=Target(distro="debian", version="13", arch="x86_64"),
        packages=(PlannedPackage(manifest=m, block=m.install[0], apt_packages=()),),
    )
    text = "\n".join(render_plan(plan, [], euid=0))
    assert "Offline data that will be downloaded and installed (D-049):" in text
    assert "0.69 GB" in text and "ODbL-1.0" in text and "https://www.country-files.com/" in text
    assert "share/hammunition/data/country-files/" in text


def test_uninstall_attribution_reads_install_data_details(tmp_path: Path) -> None:
    import json

    from hammunition.state import TransactionLog

    path = tmp_path / "transactions.jsonl"
    entries = [
        {
            "event": "action_end",
            "version": 1,
            "kind": "install-data",
            "detail": "/usr/local/share/hammunition/data/country-files",
            "outcome": "extracted",
        }
    ]
    path.write_text("".join(json.dumps(e) + "\n" for e in entries))
    log = TransactionLog(path=path)
    assert files_installed_by_hammunition(log) == {
        "/usr/local/share/hammunition/data/country-files"
    }
