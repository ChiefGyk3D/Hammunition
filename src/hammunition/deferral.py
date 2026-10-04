# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""The deferral record, in a module of its own so that plan and
userservice can both use it without importing each other."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Deferral:
    """Something the transaction will NOT do, without refusing to proceed.

    The distinction from :class:`Blocker` is the whole of D-035. A blocker means
    the machine must not be touched. A deferral means most of what was asked for
    happens and one part does not, named precisely, with what would let it.

    Templated configuration missing a station value is the case this exists for:
    a `packet` profile of nineteen packages used to refuse entirely because
    `linbpq` did not know a callsign. Nineteen packages installed and one file
    not written is a better outcome than nothing installed, and it is only
    honest if the unwritten file is reported rather than skipped.

    Q-017 extended it to a *profile member the target does not offer*: on
    Ubuntu 24.04 `listening` withheld nineteen installable units over four the
    archive does not carry. Same shape, same rule -- most of what was asked
    for happens, the part that does not is named, and `status` keeps naming it.
    """

    subject: str
    what: str
    """What will not happen."""
    why: str
    """What is missing."""
    remedy: str
    """What the operator can do about it."""
    kind: str = "config"
    """``config`` (D-035: a file not written) or ``package`` (Q-017: a profile
    member not installed). Recorded in the transaction log so `status` can
    tell them apart."""

    def render(self) -> str:
        return f"{self.subject}: {self.what}\n    why: {self.why}\n    → {self.remedy}"

    def to_log_entry(self) -> dict[str, str]:
        return {"kind": self.kind, "subject": self.subject, "what": self.what, "why": self.why}
