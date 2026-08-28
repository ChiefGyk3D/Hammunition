# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""The git backend, and the pin check that is its reason for existing.

The archive backend asks *are these the right bytes* and a sha256 answers it.
This one asks *is this the right revision*, which a successful clone does not
answer: git can exit 0 having handed over a different commit than the catalog
was written against — a re-cut tag, a moved branch, a server that ignored what
was asked for. That is D-031 with teeth, because whatever landed is what gets
compiled and installed into `/usr/local`.

So most of what follows is about the check, not the clone.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from hammunition.backends import (  # noqa: E402
    Action,
    BackendError,
    Command,
    CommandResult,
    GitBackend,
    RecordingRunner,
)
from hammunition.manifest.schema import ManifestError, PackageManifest  # noqa: E402

SHA = "36ea9a143422f5b374371461667ff53fb9387300"
OTHER_SHA = "0" * 40


def _manifest(**install: Any) -> PackageManifest:
    block: dict[str, Any] = {
        "method": "git",
        "repo": "https://example.invalid/thing",
        "ref": "v1.0",
        "build_system": "cmake",
    }
    block.update(install)
    return PackageManifest.model_validate(
        {
            "name": "thing",
            "version": "1.0",
            "summary": "A thing built from a pinned revision",
            "categories": ["digital-modes"],
            "install": [{"install": block, "build_depends": ["cmake"]}],
            "update": {"probe": {"method": "github_tags"}},
            "documentation": {
                "what_it_does": "Does a thing for the purposes of testing the backend.",
                "why_you_want_it": "Because the git backend needs a manifest to act on.",
                "upstream_url": "https://example.invalid/",
            },
        }
    )


def _pin_review(**overrides: Any) -> dict[str, Any]:
    base = {
        "last_reviewed": "2026-08-26",
        "reviewed_by": "hammunition-maintainers",
        "basis": "distribution_pin",
        "distributions": ["kali", "parrot"],
        "rationale": (
            "Chosen to match the commit Kali and Parrot package, so a source build "
            "and an apt install are the same revision rather than two."
        ),
    }
    base.update(overrides)
    return base


class _HeadRunner(RecordingRunner):
    """Answers `git rev-parse HEAD` with a chosen revision."""

    def __init__(self, head: str) -> None:
        super().__init__()
        self.head = head

    def run(self, command: Command) -> CommandResult:
        super().run(command)
        if "rev-parse" in command.argv:
            return CommandResult(
                argv=command.argv, returncode=0, stdout=self.head + "\n", stderr=""
            )
        return CommandResult(argv=command.argv, returncode=0, stdout="", stderr="")


def _backend(runner: Any, tmp_path: Path) -> GitBackend:
    return GitBackend(
        runner=runner, build_root=tmp_path / "build", prefix=Path("/usr/local"), jobs=2
    )


# ---------------------------------------------------------------------------
# The pin check
# ---------------------------------------------------------------------------


def test_a_checkout_that_is_not_the_pinned_commit_is_refused(tmp_path: Path) -> None:
    """git exited 0, so nothing else in the run would have noticed. Building
    this would install a revision the catalog was not written against."""
    backend = _backend(_HeadRunner(OTHER_SHA), tmp_path)

    with pytest.raises(BackendError) as caught:
        backend.verify_pin(tmp_path / "src", SHA)

    message = str(caught.value)
    assert SHA in message and OTHER_SHA in message, "the error must show both revisions"


def test_a_checkout_at_the_pinned_commit_is_confirmed(tmp_path: Path) -> None:
    backend = _backend(_HeadRunner(SHA), tmp_path)
    assert SHA in backend.verify_pin(tmp_path / "src", SHA)


def test_a_tag_records_what_it_resolved_to(tmp_path: Path) -> None:
    """There is nothing to compare a tag against — the point of a tag is that
    upstream chose it — so the resolved commit is recorded instead. That record
    is the raw material of the pin database: the day a tag is re-cut, the log
    says what it used to be."""
    backend = _backend(_HeadRunner(SHA), tmp_path)
    outcome = backend.verify_pin(tmp_path / "src", "v1.0")
    assert "v1.0" in outcome
    assert SHA in outcome


def test_an_unreadable_revision_is_an_error_not_a_pass(tmp_path: Path) -> None:
    class Failing(RecordingRunner):
        def run(self, command: Command) -> CommandResult:
            super().run(command)
            return CommandResult(
                argv=command.argv, returncode=128, stdout="", stderr="not a repository"
            )

    backend = _backend(Failing(), tmp_path)
    with pytest.raises(BackendError, match="could not read"):
        backend.verify_pin(tmp_path / "src", SHA)


# ---------------------------------------------------------------------------
# The steps
# ---------------------------------------------------------------------------


def test_the_pin_is_checked_after_the_checkout_and_before_the_build(tmp_path: Path) -> None:
    """Order is the whole point: a check after the build would confirm a
    revision that had already been installed."""
    manifest = _manifest()
    backend = _backend(_HeadRunner(SHA), tmp_path)
    steps = backend.steps(manifest, manifest.install[0].install)  # type: ignore[arg-type]

    labels = [s.kind if isinstance(s, Action) else " ".join(s.argv[:2]) for s in steps]
    assert labels.index("verify-pin") > labels.index("git -C"), "the pin was checked too early"
    assert labels.index("verify-pin") < labels.index("cmake -S"), "the build ran before the check"


def test_the_fetch_is_shallow_and_by_ref(tmp_path: Path) -> None:
    """A pinned commit should cost one object walk, not a project's history."""
    manifest = _manifest()
    backend = _backend(_HeadRunner(SHA), tmp_path)
    steps = backend.steps(manifest, manifest.install[0].install)  # type: ignore[arg-type]

    fetch = next(s for s in steps if isinstance(s, Command) and "fetch" in s.argv)
    assert "--depth" in fetch.argv and "1" in fetch.argv
    assert fetch.argv[-1] == "v1.0"


def test_only_the_install_step_is_privileged(tmp_path: Path) -> None:
    manifest = _manifest()
    backend = _backend(_HeadRunner(SHA), tmp_path)
    steps = backend.steps(manifest, manifest.install[0].install)  # type: ignore[arg-type]

    privileged = [s for s in steps if s.requires_root]
    assert len(privileged) == 1
    assert isinstance(privileged[0], Command)
    assert privileged[0].argv[:2] == ("cmake", "--install")


def test_a_different_pin_builds_in_a_different_directory(tmp_path: Path) -> None:
    """Switching a pin must not build on top of the previous revision's objects."""
    backend = _backend(_HeadRunner(SHA), tmp_path)
    first = _manifest()
    second = _manifest(ref=SHA, pin_review=_pin_review())

    a = backend.layout(first, first.install[0].install)  # type: ignore[arg-type]
    b = backend.layout(second, second.install[0].install)  # type: ignore[arg-type]
    assert a.root != b.root


# ---------------------------------------------------------------------------
# What the schema makes unrepresentable — asserted here because the backend
# relies on it rather than re-checking it
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("ref", ["master", "main", "HEAD", "trunk", "develop"])
def test_a_moving_ref_cannot_be_expressed(ref: str) -> None:
    with pytest.raises((ValidationError, ManifestError), match="moving branch"):
        _manifest(ref=ref)


def test_a_bare_sha_needs_a_pin_review() -> None:
    """A tag carries an upstream signal that a revision was worth naming; a SHA
    carries none, so pinning one moves a judgement onto us and it is recorded
    beside the pin rather than implied (D-024)."""
    with pytest.raises((ValidationError, ManifestError), match="pin_review"):
        _manifest(ref=SHA)


def test_a_sha_with_a_pin_review_is_accepted() -> None:
    manifest = _manifest(ref=SHA, pin_review=_pin_review())
    block = manifest.install[0].install
    assert block.pin_review is not None  # type: ignore[union-attr]
    assert block.pin_review.basis == "distribution_pin"  # type: ignore[union-attr]
