# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""The source backend: unpacking, and the steps a build turns into.

Extraction is where this backend can do real damage, so most of what follows is
written to the attack rather than to the happy path. An archive member named
``../../etc/cron.d/x``, one with an absolute path, or a symlink pointing out of
the tree are all ways to turn "unpack this" into "write anywhere", and whether
they work is decided by the extractor's defaults — which is exactly the kind of
thing that is easy to assume and cheap to assert.

The build-step tests assert the *shape* the plan will print: order, which single
step is privileged, and that declared flags actually reach the compiler. They
run no compiler; that is the container harness's job.
"""

from __future__ import annotations

import contextlib
import io
import sys
import tarfile
import zipfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from hammunition.backends import Action, BackendError, Command  # noqa: E402
from hammunition.backends.source import (  # noqa: E402
    DEFAULT_PREFIX,
    SourceBackend,
    extract,
)
from hammunition.fetch import Fetcher  # noqa: E402
from hammunition.manifest.schema import PackageManifest  # noqa: E402

PAYLOAD_SHA = "a" * 64


def _manifest(build_system: str = "autotools", **install: object) -> PackageManifest:
    block: dict[str, object] = {
        "method": "source",
        "source": {"url": "https://example.invalid/thing-1.0.tar.gz", "sha256": PAYLOAD_SHA},
        "build_system": build_system,
    }
    block.update(install)
    return PackageManifest.model_validate(
        {
            "name": "thing",
            "version": "1.0",
            "summary": "A thing that is built from source",
            "categories": ["digital-modes"],
            "install": [{"install": block}],
            "update": {"probe": {"method": "none"}},
            "documentation": {
                "what_it_does": "Does a thing for the purposes of testing the backend.",
                "why_you_want_it": "Because the source backend needs a manifest to act on.",
                "upstream_url": "https://example.invalid/",
            },
        }
    )


def _backend(tmp_path: Path, **kwargs: object) -> SourceBackend:
    return SourceBackend(
        Fetcher(tmp_path / "cache"),
        build_root=tmp_path / "build",
        jobs=4,
        **kwargs,  # type: ignore[arg-type]
    )


def _tar(path: Path, members: dict[str, bytes]) -> Path:
    with tarfile.open(path, "w:gz") as tar:
        for name, body in members.items():
            info = tarfile.TarInfo(name)
            info.size = len(body)
            tar.addfile(info, io.BytesIO(body))
    return path


def _zip(path: Path, members: dict[str, bytes]) -> Path:
    with zipfile.ZipFile(path, "w") as archive:
        for name, body in members.items():
            archive.writestr(name, body)
    return path


# ---------------------------------------------------------------------------
# Extraction: the refusals
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "member",
    [
        "../../escaped",
        "../escaped",
        "subdir/../../../escaped",
        "/escaped",
    ],
)
def test_no_tar_member_can_write_outside_the_destination(tmp_path: Path, member: str) -> None:
    """The property is *nothing lands outside*, not *an exception is raised*.

    The two mechanisms differ and both are acceptable: tarfile's ``data``
    filter refuses a ``..`` component outright, but an absolute name it
    *neutralises* — the leading ``/`` is stripped and the member lands harmlessly
    inside the destination. Asserting on the exception would have called that
    second case a failure while the machine was perfectly safe, and would have
    said nothing about where the bytes actually went. So this asserts where the
    bytes went.
    """
    victim = tmp_path / "escaped"
    destination = tmp_path / "dest" / "src"
    archive = _tar(tmp_path / "evil.tar.gz", {member: b"pwned", "keep/ok": b"fine"})

    # Refusal is one of two valid outcomes; containment is the other, and the
    # assertions below are what distinguish safe from unsafe either way.
    with contextlib.suppress(Exception):
        extract(archive, destination)

    assert not victim.exists(), f"member {member!r} escaped to {victim}"
    for landed in destination.rglob("*") if destination.exists() else []:
        resolved = landed.resolve()
        assert destination.resolve() in resolved.parents or resolved == destination.resolve(), (
            f"{landed} landed outside {destination}"
        )


def test_an_absolute_tar_member_lands_inside_rather_than_at_its_absolute_path(
    tmp_path: Path,
) -> None:
    """Named separately because the mechanism is worth pinning down: an absolute
    member is made relative, so it is *contained*, not rejected."""
    outside = tmp_path / "absolute-target"
    archive = _tar(tmp_path / "abs.tar.gz", {str(outside): b"pwned", "keep/ok": b"fine"})
    destination = tmp_path / "dest" / "src"

    extract(archive, destination)

    assert not outside.exists(), "an absolute member was written outside the tree"
    assert list(destination.rglob("absolute-target")), (
        "the absolute member vanished entirely; it should be contained, not dropped"
    )


def test_a_zip_member_escaping_the_tree_is_refused(tmp_path: Path) -> None:
    """zip has no equivalent of tar's `data` filter, so the members are screened
    here. mshv ships a zip, so this path is not hypothetical."""
    archive = _zip(tmp_path / "evil.zip", {"../../escaped": b"pwned"})
    with pytest.raises(BackendError, match="outside the build directory"):
        extract(archive, tmp_path / "dest" / "src")
    assert not (tmp_path / "escaped").exists()


def test_a_zip_member_with_an_absolute_path_is_refused(tmp_path: Path) -> None:
    archive = _zip(tmp_path / "abs.zip", {"/etc/cron.d/x": b"pwned"})
    with pytest.raises(BackendError, match="absolute path"):
        extract(archive, tmp_path / "dest" / "src")


def test_an_unknown_archive_format_is_refused(tmp_path: Path) -> None:
    blob = tmp_path / "thing.rar"
    blob.write_bytes(b"not an archive we unpack")
    with pytest.raises(BackendError, match="not an archive"):
        extract(blob, tmp_path / "dest" / "src")


def test_an_empty_archive_is_refused(tmp_path: Path) -> None:
    """D-031: the extractor returning is not evidence anything landed."""
    archive = _tar(tmp_path / "empty.tar.gz", {})
    with pytest.raises(BackendError, match="unpacked to nothing"):
        extract(archive, tmp_path / "dest" / "src")


# ---------------------------------------------------------------------------
# Extraction: what it does when the archive is honest
# ---------------------------------------------------------------------------


def test_a_single_top_level_directory_is_stripped(tmp_path: Path) -> None:
    """The strip is what makes the source root predictable, which is what lets
    the plan print `./configure`'s real path before the download happens."""
    archive = _tar(
        tmp_path / "thing.tar.gz",
        {"thing-1.0/configure": b"#!/bin/sh\n", "thing-1.0/src/main.c": b"int main(){}\n"},
    )
    destination = tmp_path / "dest" / "src"
    outcome = extract(archive, destination)

    assert (destination / "configure").is_file(), "the top-level directory was not stripped"
    assert (destination / "src" / "main.c").is_file()
    assert "thing-1.0" in outcome


def test_a_multi_entry_archive_is_not_stripped(tmp_path: Path) -> None:
    archive = _tar(tmp_path / "flat.tar.gz", {"Makefile": b"all:\n", "main.c": b"int main(){}\n"})
    destination = tmp_path / "dest" / "src"
    extract(archive, destination)
    assert (destination / "Makefile").is_file()
    assert (destination / "main.c").is_file()


def test_re_extraction_starts_from_a_clean_tree(tmp_path: Path) -> None:
    """Idempotent (CLAUDE.md). Layering a new archive over a half-built tree
    leaves stale objects outliving the source they came from."""
    archive = _tar(tmp_path / "thing.tar.gz", {"thing-1.0/configure": b"#!/bin/sh\n"})
    destination = tmp_path / "dest" / "src"
    extract(archive, destination)
    stale = destination / "stale.o"
    stale.write_bytes(b"from a previous build")

    extract(archive, destination)
    assert not stale.exists(), "a stale artefact survived re-extraction"
    assert (destination / "configure").is_file()


def test_extraction_leaves_no_staging_directory(tmp_path: Path) -> None:
    archive = _tar(tmp_path / "thing.tar.gz", {"thing-1.0/configure": b"#!/bin/sh\n"})
    destination = tmp_path / "dest" / "src"
    extract(archive, destination)
    assert [p.name for p in destination.parent.iterdir()] == ["src"]


# ---------------------------------------------------------------------------
# The steps a build turns into
# ---------------------------------------------------------------------------


def test_the_steps_run_in_the_order_a_build_needs(tmp_path: Path) -> None:
    backend = _backend(tmp_path)
    manifest = _manifest("autotools")
    steps = backend.steps(manifest, manifest.install[0].install)  # type: ignore[arg-type]

    kinds = [s.kind if isinstance(s, Action) else s.argv[0] for s in steps]
    assert kinds == ["fetch", "extract", "./configure", "make", "make"]


def test_only_the_install_step_is_privileged(tmp_path: Path) -> None:
    """CLAUDE.md drops to the operator wherever possible. A build run wholly as
    root leaves a tree of root-owned objects in the operator's cache."""
    backend = _backend(tmp_path)
    manifest = _manifest("cmake")
    steps = backend.steps(manifest, manifest.install[0].install)  # type: ignore[arg-type]

    privileged = [s for s in steps if s.requires_root]
    assert len(privileged) == 1
    assert isinstance(privileged[0], Command)
    assert privileged[0].argv[:2] == ("cmake", "--install")


def test_the_plan_can_print_every_path_before_anything_is_fetched(tmp_path: Path) -> None:
    """Nothing in `steps()` touches the disk or the network, so `--dry-run`
    renders real paths rather than describing them."""
    backend = _backend(tmp_path)
    manifest = _manifest("cmake")
    steps = backend.steps(manifest, manifest.install[0].install)  # type: ignore[arg-type]

    assert not (tmp_path / "build").exists()
    assert not (tmp_path / "cache").exists()
    rendered = "\n".join(s.display(euid=1000) for s in steps)
    layout = backend.layout(manifest, manifest.install[0].install)  # type: ignore[arg-type]
    assert str(layout.src) in rendered
    assert "sha256 verified" in rendered


def test_compiler_flags_reach_the_compiler(tmp_path: Path) -> None:
    """Six AHRL units need -Wno-* to build at all. AHRL carries them as shell
    string-mangling; declaring them makes them reviewable catalog data."""
    manifest = _manifest("autotools", compiler_flags=["-Wno-incompatible-pointer-types"])
    backend = _backend(tmp_path)
    steps = backend.steps(manifest, manifest.install[0].install)  # type: ignore[arg-type]

    configure = next(s for s in steps if isinstance(s, Command) and s.argv[0] == "./configure")
    assert configure.env["CFLAGS"] == "-Wno-incompatible-pointer-types"
    assert configure.env["CXXFLAGS"] == "-Wno-incompatible-pointer-types"


def test_the_qmake_project_file_is_passed_when_declared(tmp_path: Path) -> None:
    """MSHV needs a different .pro per architecture, which is why the field
    exists at all."""
    manifest = _manifest("qmake", project_file="MSHV_64.pro")
    backend = _backend(tmp_path)
    steps = backend.steps(manifest, manifest.install[0].install)  # type: ignore[arg-type]

    qmake = next(s for s in steps if isinstance(s, Command) and s.argv[0] == "qmake")
    assert "MSHV_64.pro" in qmake.argv


def test_the_install_prefix_is_usr_local(tmp_path: Path) -> None:
    manifest = _manifest("autotools")
    backend = _backend(tmp_path)
    steps = backend.steps(manifest, manifest.install[0].install)  # type: ignore[arg-type]
    configure = next(s for s in steps if isinstance(s, Command) and s.argv[0] == "./configure")
    assert f"--prefix={DEFAULT_PREFIX}" in configure.argv


def test_build_commands_carry_a_working_directory(tmp_path: Path) -> None:
    """`./configure` has no meaning without one, and the plan must show it."""
    manifest = _manifest("autotools")
    backend = _backend(tmp_path)
    layout = backend.layout(manifest, manifest.install[0].install)  # type: ignore[arg-type]
    steps = backend.steps(manifest, manifest.install[0].install)  # type: ignore[arg-type]

    configure = next(s for s in steps if isinstance(s, Command) and s.argv[0] == "./configure")
    assert configure.cwd == layout.src
    assert configure.display(euid=1000).startswith(f"cd {layout.src} &&")


# ---------------------------------------------------------------------------
# The measured zeros, refused by name rather than silently skipped
# ---------------------------------------------------------------------------


def test_a_custom_build_system_is_refused_by_name(tmp_path: Path) -> None:
    manifest = _manifest("custom")
    backend = _backend(tmp_path)
    with pytest.raises(BackendError, match="custom"):
        backend.steps(manifest, manifest.install[0].install)  # type: ignore[arg-type]


def test_patches_are_refused_by_name(tmp_path: Path) -> None:
    """Building unpatched source would produce a binary the manifest did not
    describe, which is worse than refusing."""
    manifest = _manifest(
        "autotools",
        patches=[{"file": "src/main.c", "description": "fix a thing that needs fixing"}],
    )
    backend = _backend(tmp_path)
    with pytest.raises(BackendError, match="patch"):
        backend.steps(manifest, manifest.install[0].install)  # type: ignore[arg-type]
