# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later
"""Per-block `binaries`, and the one list every reader must agree on (issue #69).

`PackageManifest.binaries` is one list for the whole manifest. A prebuilt
archive whose blocks select by `arch` can emit a different path per block:
Rayhunter's release zip carries `installer` at the top level and one
`rayhunter-check` under a per-platform directory, so an aarch64 block reading
the manifest-level list would install the x64 executable and the post-run
effect check would confirm it. That is the D-031 shape — a run that reports
success having installed the wrong file — so the block's own list, when it
declares one, is what the backends install, what `verify_effects` reads back,
what `already_built` counts and what `uninstall` plans to remove.

Every test here was watched red before `InstallBlock.binaries` and
`effective_binaries` existed.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from hammunition.backends import BinaryBackend, Command, RecordingRunner  # noqa: E402
from hammunition.distro import Target  # noqa: E402
from hammunition.execute import verify_effects  # noqa: E402
from hammunition.fetch import Fetcher  # noqa: E402
from hammunition.manifest.load import load_catalog  # noqa: E402
from hammunition.manifest.schema import (  # noqa: E402
    BinaryInstall,
    ManifestError,
    PackageManifest,
    effective_binaries,
)
from hammunition.plan import InstallPlan, PlannedPackage  # noqa: E402

CATALOG = REPO_ROOT / "catalog" / "packages"
SHA = "b" * 64

DOCS = {
    "what_it_does": "Stands in for a prebuilt archive whose layout differs per arch.",
    "why_you_want_it": "To prove the block's own `binaries` is the list that is used.",
    "upstream_url": "https://example.invalid/",
}


def _two_arch_manifest(**overrides: Any) -> PackageManifest:
    """Rayhunter's shape: one zip per arch, the payload path carrying the arch."""
    data: dict[str, Any] = {
        "name": "perarch",
        "version": "1.0",
        "summary": "A prebuilt archive laid out differently on each architecture",
        "categories": ["rf-security"],
        "install": [
            {
                "when": {"arch": ["x86_64"]},
                "install": {
                    "method": "binary",
                    "artifact": {"url": "https://example.invalid/x64.zip", "sha256": SHA},
                    "format": "zip",
                },
                "binaries": [
                    {"produced": "installer", "install_as": "perarch-installer"},
                    {"produced": "check-linux-x64/check", "install_as": "perarch-check"},
                ],
            },
            {
                "when": {"arch": ["aarch64"]},
                "install": {
                    "method": "binary",
                    "artifact": {"url": "https://example.invalid/arm64.zip", "sha256": SHA},
                    "format": "zip",
                },
                "binaries": [
                    {"produced": "installer", "install_as": "perarch-installer"},
                    {"produced": "check-linux-aarch64/check", "install_as": "perarch-check"},
                ],
            },
        ],
        "update": {"probe": {"method": "none"}},
        "documentation": DOCS,
    }
    data.update(overrides)
    return PackageManifest.model_validate(data)


# ---------------------------------------------------------------------------
# Schema: what it accepts and what it refuses
# ---------------------------------------------------------------------------


def test_a_block_may_declare_its_own_binaries() -> None:
    manifest = _two_arch_manifest()
    assert manifest.binaries == []
    x64, arm = manifest.install
    assert x64.binaries is not None and arm.binaries is not None
    assert [b.produced for b in x64.binaries] == ["installer", "check-linux-x64/check"]
    assert [b.produced for b in arm.binaries] == ["installer", "check-linux-aarch64/check"]


def test_block_binaries_are_refused_on_a_method_that_installs_none() -> None:
    """apt places a package's files; naming build outputs there means nothing,
    and a list nothing reads is a claim the engine would never honour."""
    with pytest.raises((ValidationError, ManifestError)) as caught:
        PackageManifest.model_validate(
            {
                "name": "aptish",
                "version": "1.0",
                "summary": "An apt block that names binaries",
                "categories": ["rf-security"],
                "install": [
                    {
                        "when": {"arch": ["x86_64"]},
                        "install": {"method": "apt", "packages": ["aptish"]},
                        "binaries": [{"produced": "aptish", "install_as": "aptish"}],
                    }
                ],
                "update": {"probe": {"method": "none"}},
                "documentation": DOCS,
            }
        )
    message = str(caught.value)
    assert "apt" in message and "binaries" in message


def test_block_binaries_are_refused_on_a_deb() -> None:
    """apt places a .deb's contents; the engine copies nothing to name."""
    with pytest.raises((ValidationError, ManifestError)) as caught:
        PackageManifest.model_validate(
            {
                "name": "debbish",
                "version": "1.0",
                "summary": "A vendor .deb block that names binaries",
                "categories": ["rf-security"],
                "install": [
                    {
                        "install": {
                            "method": "binary",
                            "artifact": {"url": "https://example.invalid/x.deb", "sha256": SHA},
                            "format": "deb",
                            "deb_package": "debbish",
                        },
                        "binaries": [{"produced": "debbish", "install_as": "debbish"}],
                    }
                ],
                "update": {"probe": {"method": "none"}},
                "documentation": DOCS,
            }
        )
    assert "binaries" in str(caught.value)


def test_an_empty_block_binaries_list_is_refused() -> None:
    """`binaries: []` reads as an override to nothing, which would silently
    install nothing where the manifest's list installs something. Omit the key."""
    with pytest.raises((ValidationError, ManifestError)) as caught:
        _two_arch_manifest(
            install=[
                {
                    "when": {"arch": ["x86_64"]},
                    "install": {
                        "method": "binary",
                        "artifact": {"url": "https://example.invalid/x64.zip", "sha256": SHA},
                        "format": "zip",
                    },
                    "binaries": [],
                }
            ],
            binaries=[{"produced": "installer", "install_as": "perarch-installer"}],
        )
    assert "empty" in str(caught.value)


# ---------------------------------------------------------------------------
# The helper every reader goes through
# ---------------------------------------------------------------------------


def test_effective_binaries_prefers_the_block() -> None:
    manifest = _two_arch_manifest(
        binaries=[{"produced": "installer", "install_as": "manifest-level"}]
    )
    arm = manifest.install[1]
    assert [b.install_as for b in effective_binaries(manifest, arm)] == [
        "perarch-installer",
        "perarch-check",
    ]
    assert [b.produced for b in effective_binaries(manifest, arm)] == [
        "installer",
        "check-linux-aarch64/check",
    ]


def test_effective_binaries_falls_back_to_the_manifest() -> None:
    manifest = PackageManifest.model_validate(
        {
            "name": "shared",
            "version": "1.0",
            "summary": "One layout on every architecture",
            "categories": ["rf-security"],
            "install": [
                {
                    "install": {
                        "method": "binary",
                        "artifact": {"url": "https://example.invalid/any.zip", "sha256": SHA},
                        "format": "zip",
                    }
                }
            ],
            "binaries": [{"produced": "shared", "install_as": "shared"}],
            "update": {"probe": {"method": "none"}},
            "documentation": DOCS,
        }
    )
    assert [b.install_as for b in effective_binaries(manifest, manifest.install[0])] == ["shared"]


# ---------------------------------------------------------------------------
# The block's list is what gets installed, and what gets checked
# ---------------------------------------------------------------------------


def test_the_binary_backend_installs_the_blocks_own_binaries(tmp_path: Path) -> None:
    """The aarch64 block's `produced` path is what the install command copies.
    Reading the manifest-level list here is how the x64 executable would land
    on an aarch64 machine with the run reporting success."""
    manifest = _two_arch_manifest(
        binaries=[{"produced": "check-linux-x64/check", "install_as": "perarch-check"}]
    )
    backend = BinaryBackend(
        fetcher=Fetcher(tmp_path / "cache"),
        runner=RecordingRunner(),
        build_root=tmp_path / "build",
        prefix=tmp_path / "prefix",
    )
    rendered = " ".join(
        " ".join(step.argv)
        for step in backend.steps(manifest, manifest.install[1])
        if isinstance(step, Command)
    )
    assert "check-linux-aarch64/check" in rendered
    assert "check-linux-x64/check" not in rendered


def test_verify_effects_reads_back_the_blocks_own_binaries(tmp_path: Path) -> None:
    """The post-run check must ask about the file the block installed. Asking
    about the manifest-level name is D-031 exactly: a check that passes on the
    wrong artefact is worse than no check."""
    manifest = _two_arch_manifest(binaries=[{"produced": "installer", "install_as": "wrong-name"}])
    prefix = tmp_path / "prefix"
    (prefix / "bin").mkdir(parents=True)
    for name in ("perarch-installer", "perarch-check"):
        path = prefix / "bin" / name
        path.write_text("#!/bin/sh\n")
        path.chmod(0o755)
    # The manifest-level name is deliberately absent from the prefix.
    plan = InstallPlan(
        target=Target(distro="debian", version="13", arch="aarch64"),
        packages=(PlannedPackage(manifest=manifest, block=manifest.install[1], apt_packages=()),),
    )
    report = verify_effects(plan, None, prefix=prefix)
    subjects = {check.subject: check.confirmed for check in report.checks}
    assert subjects["perarch:perarch-installer"] is True
    assert subjects["perarch:perarch-check"] is True
    assert "perarch:wrong-name" not in subjects


# ---------------------------------------------------------------------------
# The catalog entry this was written for
# ---------------------------------------------------------------------------


def test_rayhunter_resolves_per_arch_with_its_own_binaries() -> None:
    """The maintainer's uConsole is aarch64 (docs/reference/hardware-gaps.md),
    and until issue #69 the manifest had no block for it at all."""
    rayhunter = load_catalog(CATALOG)["rayhunter"]
    wanted = {
        "x86_64": "rayhunter-check-linux-x64/rayhunter-check",
        "aarch64": "rayhunter-check-linux-aarch64/rayhunter-check",
        "armv7l": "rayhunter-check-linux-armv7/rayhunter-check",
    }
    for arch, produced in wanted.items():
        block = rayhunter.resolve("debian", "13", arch)
        assert block is not None, f"rayhunter does not resolve on {arch}"
        install = block.install
        assert isinstance(install, BinaryInstall)
        assert f"linux-{'x64' if arch == 'x86_64' else arch.rstrip('l')}" in install.artifact.url
        names = effective_binaries(rayhunter, block)
        assert [b.produced for b in names] == ["installer", produced]
        assert [b.install_as for b in names] == ["rayhunter-installer", "rayhunter-check"]
