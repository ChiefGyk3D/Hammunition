# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""Building from a pinned git revision.  DESIGN.md §6, D-024.

The archive backend's problem is *are these the right bytes*, and a sha256
answers it. This backend's problem is *is this the right revision*, and it is
not the same question: a clone can succeed, and succeed completely, while
handing you a different commit than the one the catalog was written against —
a re-cut tag, a moved branch, a server that quietly ignored what was asked for.

So the pin is checked after the checkout rather than assumed from it. ``git``
exiting 0 is not evidence you got the revision you named (**D-031**), and this
is the backend where that distinction has teeth: what gets compiled and
installed into ``/usr/local`` is decided entirely by which commit landed.

**A moving ref is unrepresentable.** The schema refuses ``master``, ``main``,
``HEAD``, ``trunk`` and ``develop`` outright, and requires a
:class:`~hammunition.manifest.schema.PinReview` — who looked, when, and why this
commit — whenever the ref is a bare SHA. A tag carries an upstream signal that
somebody thought a revision worth naming; a SHA carries none, so pinning one
moves a judgement upstream stopped making onto us and that judgement is recorded
beside the pin rather than implied by it.

**The fetch is shallow and by ref**, so a pinned commit costs one object walk
rather than a project's whole history. ``git fetch --depth 1 origin <ref>``
works for both a tag and a SHA against every forge the catalog names.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from hammunition.manifest.schema import COMMIT_SHA, GitInstall, PackageManifest

from .base import Action, BackendError, Command, CommandRunner
import re

from .source import SourceLayout, build_commands, prepare_tree, tree_install_commands

COMMIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$")

__all__ = ["GitBackend"]


@dataclass(frozen=True)
class GitBackend:
    """Turns a ``git`` install block into the steps that build it."""

    runner: CommandRunner
    """Used by the pin check, which has to ask git what actually landed. Going
    through the runner rather than :mod:`subprocess` keeps the one seam every
    other command uses, so the check is testable without a network or a clone."""

    build_root: Path
    prefix: Path
    jobs: int

    method = "git"

    def layout(self, manifest: PackageManifest, block: GitInstall) -> SourceLayout:
        """Where this package builds. Pure — touches no disk.

        Keyed by the ref rather than a digest, so switching a pin builds in a
        new directory instead of on top of the previous revision's objects.
        """
        return SourceLayout(self.build_root / f"{manifest.name}-{block.ref[:12]}")

    def steps(self, manifest: PackageManifest, block: GitInstall) -> list[Action | Command]:
        layout = self.layout(manifest, block)
        src = layout.src
        steps: list[Action | Command] = [
            Action(
                kind="prepare",
                description=f"Clear any previous {manifest.name} checkout",
                detail=f"{src} (removed if present, then recreated)",
                perform=lambda: prepare_tree(src),
            ),
            Command(
                argv=("git", "init", "--quiet", str(src)),
                description=f"Start an empty repository for {manifest.name}",
            ),
            Command(
                argv=("git", "-C", str(src), "remote", "add", "origin", block.repo),
                description=f"Point it at {block.repo}",
            ),
            Command(
                # Shallow and by ref: a pinned commit costs one object walk, not
                # the project's whole history.
                argv=("git", "-C", str(src), "fetch", "--depth", "1", "origin", block.ref),
                description=f"Fetch {manifest.name} at {block.ref}",
            ),
            Command(
                argv=("git", "-C", str(src), "checkout", "--quiet", "FETCH_HEAD"),
                description=f"Check out {block.ref}",
            ),
            *(
                [
                    Command(
                        # A shallow tag fetch leaves only FETCH_HEAD; builds
                        # that version themselves with `git describe` then see
                        # no tag at all. Recreating the ref locally costs
                        # nothing and makes describe answer with the pin.
                        argv=("git", "-C", str(src), "tag", "-f", block.ref, "FETCH_HEAD"),
                        description=f"Recreate the {block.ref} tag for describe-based versioning",
                    )
                ]
                if not COMMIT_SHA_RE.match(block.ref)
                else []
            ),
            Action(
                kind="verify-pin",
                description=f"Confirm {manifest.name} is at the pinned revision",
                detail=f"git rev-parse HEAD in {src} must be {block.ref}",
                perform=lambda: self.verify_pin(src, block.ref),
            ),
        ]
        steps.extend(
            build_commands(
                name=manifest.name,
                build_system=block.build_system,
                layout=layout,
                prefix=self.prefix,
                jobs=self.jobs,
                configure_args=block.configure_args,
                compiler_flags=block.compiler_flags,
                project_file=block.project_file,
                build_args=block.build_args,
                provides_install_target=block.provides_install_target,
                binaries=manifest.binaries,
                autoreconf=block.autoreconf,
            )
        )
        if block.install_tree:
            steps.extend(
                tree_install_commands(
                    name=manifest.name, source_tree=layout.src, prefix=self.prefix
                )
            )
        return steps

    def verify_pin(self, src: Path, ref: str) -> str:
        """Ask git what actually landed, and refuse anything else.

        For a SHA the comparison is exact. For a tag there is nothing to compare
        against — the point of a tag is that upstream chose it — so the resolved
        commit is *recorded* instead, which is the raw material the pin database
        is made of: the day a tag is re-cut, the log says what it used to be.
        """
        result = self.runner.run(
            Command(
                argv=("git", "-C", str(src), "rev-parse", "HEAD"),
                description="Read the checked-out revision",
            )
        )
        if not result.ok:
            raise BackendError(
                f"could not read the checked-out revision in {src}: {result.stderr.strip()}"
            )
        head = result.stdout.strip()
        if COMMIT_SHA.match(ref):
            if head != ref:
                raise BackendError(
                    f"the checkout is not the pinned revision.\n"
                    f"  pinned:  {ref}\n"
                    f"  checked out: {head}\n"
                    f"git exited 0, so nothing else in this run would have noticed. "
                    f"Building this would install a revision the catalog was not "
                    f"written against (D-024, D-031)."
                )
            return f"HEAD is {head}, matching the pin"
        return f"tag {ref} resolved to {head}"
