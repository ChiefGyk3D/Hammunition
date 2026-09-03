# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""Resolving a consent gate into a recorded affirmation.  D-021.

Three properties this module exists to guarantee, each with a test:

1. ``--yes`` cannot satisfy a gate. The parameter is accepted so the signature
   documents the fact, and is never read.
2. Silence is never consent. No TTY and no environment variable is a refusal to
   proceed, not an assumption either way.
3. Whatever the operator was actually shown is recorded, not a reconstruction
   of it. The record carries the rendered text and its digest.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum

from hammunition.manifest.schema import AptRepo, ConsentGate, RiskCategory

__all__ = [
    "ConsentDeclined",
    "ConsentRecord",
    "ConsentUnavailable",
    "Decision",
    "render_disclosure",
    "render_repo_disclosure",
    "repo_env_var",
    "resolve_consent",
    "resolve_repo_consent",
]


class Decision(StrEnum):
    """How the affirmation was obtained. Recorded; never inferred later."""

    interactive = "interactive"
    environment = "environment"


class ConsentDeclined(Exception):
    """The operator was asked and said no."""


class ConsentUnavailable(Exception):
    """The gate could not be presented: no TTY, and no environment variable.

    Distinct from ConsentDeclined on purpose. "Nobody was asked" and "somebody
    said no" are different facts and the log should not conflate them.
    """


def render_disclosure(gate: ConsentGate, profile: str) -> str:
    """The exact text an operator sees. One function, so the interactive prompt
    and the recorded text cannot drift apart."""
    lines = [
        f"Profile {profile!r} is consent-gated.",
        "",
        gate.disclosure.strip(),
        "",
        "What this software can do:",
    ]
    lines += [f"  - {line}" for line in gate.risk_lines]
    lines += [
        "",
        "Hammunition cannot know your location, licence class, or the terms of any",
        "authorization you hold, and does not give legal advice. You are being asked",
        "to affirm your own authorization, not to be told what applies to you.",
        "",
        gate.affirmation.strip(),
    ]
    return "\n".join(lines)


@dataclass(frozen=True)
class ConsentRecord:
    """What goes in the transaction log. Enough to reconstruct what was shown."""

    profile: str
    decision: Decision
    risk_categories: tuple[RiskCategory, ...]
    disclosure_text: str
    disclosure_sha256: str
    env_var: str
    timestamp: datetime
    actor: str | None = None
    extra: Mapping[str, str] = field(default_factory=dict)

    def to_log_entry(self) -> dict[str, object]:
        """Transaction-log shape. JSON-serialisable, stable field names."""
        return {
            "event": "consent_affirmed",
            "version": 1,
            "timestamp": self.timestamp.astimezone(UTC).isoformat(),
            "profile": self.profile,
            "decision": self.decision.value,
            "risk_categories": [c.value for c in self.risk_categories],
            "env_var": self.env_var,
            "disclosure_sha256": self.disclosure_sha256,
            "disclosure_text": self.disclosure_text,
            "actor": self.actor,
            **({"extra": dict(self.extra)} if self.extra else {}),
        }


def resolve_consent(
    gate: ConsentGate,
    profile: str,
    *,
    environ: Mapping[str, str],
    prompt: Callable[[str], bool] | None,
    assume_yes: bool = False,
    actor: str | None = None,
    now: Callable[[], datetime] | None = None,
) -> ConsentRecord:
    """Obtain an affirmation, or raise.

    ``assume_yes`` carries the value of ``--yes``. It is deliberately never
    read: a gate a convenience flag walks through is not a gate (**D-021**).
    Keeping the parameter makes that explicit at every call site and lets a
    test assert it.

    ``prompt`` is None when there is no interactive terminal.
    """
    del assume_yes  # D-021: --yes must not satisfy a consent gate.

    stamp = (now or (lambda: datetime.now(UTC)))()
    text = render_disclosure(gate, profile)
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()

    def record(decision: Decision) -> ConsentRecord:
        return ConsentRecord(
            profile=profile,
            decision=decision,
            risk_categories=tuple(gate.risk_categories),
            disclosure_text=text,
            disclosure_sha256=digest,
            env_var=gate.env_var,
            timestamp=stamp,
            actor=actor,
        )

    if environ.get(gate.env_var) == "1":
        return record(Decision.environment)

    if prompt is None:
        raise ConsentUnavailable(
            f"profile {profile!r} requires affirmative consent and there is no "
            f"interactive terminal. Set {gate.env_var}=1 to affirm in a script. "
            f"--yes does not satisfy this gate.\n\n{text}"
        )

    if not prompt(text):
        raise ConsentDeclined(f"consent for profile {profile!r} was declined")
    return record(Decision.interactive)


# ---------------------------------------------------------------------------
# Third-party apt repositories.  D-040.
# ---------------------------------------------------------------------------
#
# Same three properties as a profile gate, and one more: the scripted
# affirmation names the key. ``HAMMUNITION_ACCEPT_APT_REPO_<NAME>=1`` would
# let an automation written against one key keep affirming after the
# catalog re-pins another; setting it to the fingerprint the operator was
# shown binds the affirmation to that key, and a re-pin stops the script
# with the gate rather than walking through it.


def repo_env_var(repo: AptRepo) -> str:
    """``HAMMUNITION_ACCEPT_APT_REPO_<NAME>``, the name upper-cased and
    anything that is not a letter or digit folded to an underscore."""
    folded = "".join(c if c.isalnum() else "_" for c in repo.name.upper())
    return f"HAMMUNITION_ACCEPT_APT_REPO_{folded}"


def render_repo_disclosure(repo: AptRepo, unit: str, *, sources: str, keyring: str) -> str:
    """Exactly what the operator sees before a repository is added.

    ``sources`` and ``keyring`` are the two paths the engine will write,
    passed in rather than computed here so the disclosure and the plan
    cannot name different files.
    """
    fingerprint = "".join(repo.key_fingerprint.split()).upper()
    lines = [
        f"Package {unit!r} needs a third-party apt repository: {repo.name}.",
        "",
        repo.rationale.strip(),
        "",
        "What will be added:",
        f"  repository:  {repo.uri}",
        f"  suites:      {' '.join(repo.suites)}",
        f"  components:  {' '.join(repo.components)}",
        f"  signing key: {repo.key_url}",
        f"  fingerprint: {fingerprint}",
        f"  written to:  {sources}",
        f"               {keyring}",
        "",
        "The key is fetched, its fingerprint checked against the one above, and",
        "only then installed. It is trusted for this repository alone (Signed-By),",
        "never archive-wide. Whoever holds this key can ship updates to any package",
        "name this repository publishes, for as long as it stays configured.",
        f"`hammunition uninstall {unit}` removes both files.",
        "",
        f"Add the {repo.name} repository and trust this key for it?",
    ]
    return "\n".join(lines)


def resolve_repo_consent(
    repo: AptRepo,
    unit: str,
    *,
    sources: str,
    keyring: str,
    environ: Mapping[str, str],
    prompt: Callable[[str], bool] | None,
    assume_yes: bool = False,
    actor: str | None = None,
    now: Callable[[], datetime] | None = None,
) -> ConsentRecord:
    """Obtain an affirmation for one repository, or raise.

    ``assume_yes`` is accepted and never read, exactly as in
    :func:`resolve_consent`: a repository that ``--yes`` could add is a
    repository added without anyone reading what it grants (D-021, D-040).
    The environment route requires the variable to hold the pinned
    fingerprint; ``1`` is refused with the value it should have held.
    """
    del assume_yes  # D-021/D-040: --yes must not add a repository.

    stamp = (now or (lambda: datetime.now(UTC)))()
    text = render_repo_disclosure(repo, unit, sources=sources, keyring=keyring)
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    env_var = repo_env_var(repo)
    fingerprint = "".join(repo.key_fingerprint.split()).upper()

    def record(decision: Decision) -> ConsentRecord:
        return ConsentRecord(
            profile=f"apt-repo:{repo.name}",
            decision=decision,
            risk_categories=(),
            disclosure_text=text,
            disclosure_sha256=digest,
            env_var=env_var,
            timestamp=stamp,
            actor=actor,
            extra={
                "kind": "apt_repo",
                "unit": unit,
                "repository": repo.name,
                "uri": repo.uri,
                "key_fingerprint": fingerprint,
            },
        )

    given = environ.get(env_var)
    if given is not None:
        if "".join(given.split()).upper() == fingerprint:
            return record(Decision.environment)
        raise ConsentUnavailable(
            f"{env_var} is set but does not name the pinned key. To affirm the "
            f"{repo.name} repository in a script, set it to the fingerprint you were "
            f"shown: {env_var}={fingerprint}. A bare '1' is refused so that a "
            f"re-pinned key stops the script instead of being trusted unread.\n\n{text}"
        )

    if prompt is None:
        raise ConsentUnavailable(
            f"adding the {repo.name} repository for {unit!r} requires affirmative "
            f"consent and there is no interactive terminal. Set "
            f"{env_var}={fingerprint} to affirm in a script. --yes does not satisfy "
            f"this gate.\n\n{text}"
        )

    if not prompt(text):
        raise ConsentDeclined(f"adding the {repo.name} repository for {unit!r} was declined")
    return record(Decision.interactive)
