# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later
"""A git block can carry patches, applied after the pin is confirmed and
before the build, exactly as a source block's. First use: linbpq's makefile
runs `sudo setcap` inside the build (#96), and the only honest build is one
with that line removed by a diff the catalog shows."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from hammunition.backends import Command, GitBackend, RecordingRunner  # noqa: E402
from hammunition.manifest.load import load_catalog  # noqa: E402
from hammunition.manifest.schema import GitInstall, PackageManifest  # noqa: E402

DIFF = "--- a/makefile\n+++ b/makefile\n@@ -1,2 +1 @@\n cc -o thing thing.c\n-\tsudo setcap cap_net_raw=ep thing\n"


def _manifest(patches: list[dict[str, Any]]) -> PackageManifest:
    return PackageManifest.model_validate(
        {
            "name": "thing",
            "version": "1.0",
            "summary": "Fixture",
            "categories": ["packet"],
            "install": [
                {
                    "install": {
                        "method": "git",
                        "repo": "https://example.invalid/thing",
                        "ref": "v1.0",
                        "build_system": "make",
                        "provides_install_target": False,
                        "patches": patches,
                    }
                }
            ],
            "binaries": [{"produced": "thing", "install_as": "thing"}],
            "update": {"probe": {"method": "none"}},
            "documentation": {
                "what_it_does": "Stands in for a git build that needs a patch.",
                "why_you_want_it": "To prove the patch lands between checkout and build.",
                "upstream_url": "https://example.invalid/",
            },
        }
    )


def test_git_patches_are_staged_and_applied_after_the_pin_and_before_the_build(
    tmp_path: Path,
) -> None:
    m = _manifest([{"file": "makefile", "description": "drop the sudo", "unified_diff": DIFF}])
    backend = GitBackend(
        runner=RecordingRunner(), build_root=tmp_path, prefix=tmp_path / "prefix", jobs=1
    )
    steps = backend.steps(m, m.install[0])
    kinds = [getattr(s, "kind", None) or (s.argv[0] if hasattr(s, "argv") else "?") for s in steps]
    verify = kinds.index("verify-pin")
    patch_action = kinds.index("patch")
    apply = next(i for i, s in enumerate(steps) if getattr(s, "argv", ("",))[0] == "patch")
    make = next(i for i, s in enumerate(steps) if getattr(s, "argv", ("",))[0] == "make")
    assert verify < patch_action < apply < make
    applied = steps[apply]
    assert isinstance(applied, Command)
    assert applied.argv[:3] == ("patch", "-p1", "-i")


def test_a_git_block_without_patches_plans_none() -> None:
    m = _manifest([])
    backend = GitBackend(runner=RecordingRunner(), build_root=Path("/b"), prefix=Path("/p"), jobs=1)
    assert not any(getattr(s, "kind", None) == "patch" for s in backend.steps(m, m.install[0]))


def test_linbpq_removes_the_sudo_setcap_line_by_patch() -> None:
    catalog = load_catalog(REPO_ROOT / "catalog" / "packages")
    block = catalog["linbpq"].install[0].install
    assert isinstance(block, GitInstall)
    (patch,) = block.patches
    assert patch.file == "makefile"
    assert patch.unified_diff is not None
    assert '-\tsudo setcap "CAP_NET_ADMIN=ep' in patch.unified_diff
    assert "+\tsudo" not in patch.unified_diff
