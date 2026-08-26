# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""Consent gate tests.  D-021.

The decision says three things that only mean something if a test enforces
them: a convenience flag cannot satisfy a gate, silence is not consent, and the
disclosure may not read as legal advice.
"""

from __future__ import annotations

import dataclasses
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from hammunition.consent import (
    ConsentDeclined,
    ConsentRecord,
    ConsentUnavailable,
    Decision,
    render_disclosure,
    resolve_consent,
)
from hammunition.manifest.schema import ConsentGate, ManifestError, RiskCategory
from hammunition.state import TransactionLog

ENV_VAR = "HAMMUNITION_ACCEPT_RF_RESEARCH"


def make_gate(**overrides: object) -> ConsentGate:
    data: dict[str, object] = {
        "risk_categories": [
            RiskCategory.unlicensed_transmission,
            RiskCategory.spectrum_disruption,
        ],
        "env_var": ENV_VAR,
        "disclosure": (
            "This profile installs software that can drive connected radio hardware "
            "to transmit, and that can interfere with other users of the spectrum."
        ),
        "affirmation": (
            "Do you affirm that you have the authorization required for how you "
            "intend to use this software?"
        ),
    }
    data.update(overrides)
    return ConsentGate.model_validate(data)


FIXED = datetime(2026, 8, 26, 12, 0, tzinfo=UTC)


# ---------------------------------------------------------------------------
# The rule the whole decision rests on
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("assume_yes", [True, False])
def test_yes_flag_never_satisfies_a_gate(assume_yes: bool) -> None:
    """--yes means 'do not ask me to confirm routine steps'. This is not routine."""
    with pytest.raises(ConsentUnavailable):
        resolve_consent(make_gate(), "rf-research", environ={}, prompt=None, assume_yes=assume_yes)


def test_yes_flag_does_not_override_a_refusal() -> None:
    with pytest.raises(ConsentDeclined):
        resolve_consent(
            make_gate(),
            "rf-research",
            environ={},
            prompt=lambda _text: False,
            assume_yes=True,
        )


def test_generic_yes_environment_variables_do_not_satisfy_a_gate() -> None:
    """Only the gate's own declared variable counts."""
    for name in ("HAMMUNITION_YES", "HAMMUNITION_ASSUME_YES", "CI", "DEBIAN_FRONTEND"):
        with pytest.raises(ConsentUnavailable):
            resolve_consent(make_gate(), "rf-research", environ={name: "1"}, prompt=None)


def test_another_profiles_variable_does_not_satisfy_this_gate() -> None:
    with pytest.raises(ConsentUnavailable):
        resolve_consent(
            make_gate(),
            "rf-research",
            environ={"HAMMUNITION_ACCEPT_SOMETHING_ELSE": "1"},
            prompt=None,
        )


@pytest.mark.parametrize("value", ["0", "", "true", "yes", "no", "false"])
def test_env_var_must_be_exactly_one(value: str) -> None:
    """An affirmation is an explicit act, so exactly one value expresses it."""
    with pytest.raises(ConsentUnavailable):
        resolve_consent(make_gate(), "rf-research", environ={ENV_VAR: value}, prompt=None)


def test_no_tty_and_no_variable_is_refusal_not_assumption() -> None:
    """Silence is never consent."""
    with pytest.raises(ConsentUnavailable) as excinfo:
        resolve_consent(make_gate(), "rf-research", environ={}, prompt=None)
    message = str(excinfo.value)
    assert ENV_VAR in message, "the error must name the variable that would work"
    assert "--yes does not satisfy" in message


def test_declined_and_unavailable_are_different_exceptions() -> None:
    """'Nobody was asked' and 'somebody said no' are different facts."""
    assert not issubclass(ConsentDeclined, ConsentUnavailable)
    assert not issubclass(ConsentUnavailable, ConsentDeclined)


# ---------------------------------------------------------------------------
# What gets recorded
# ---------------------------------------------------------------------------


def test_environment_path_records_how_consent_was_given() -> None:
    record = resolve_consent(
        make_gate(), "rf-research", environ={ENV_VAR: "1"}, prompt=None, now=lambda: FIXED
    )
    assert record.decision is Decision.environment
    assert record.timestamp == FIXED


def test_interactive_path_records_how_consent_was_given() -> None:
    record = resolve_consent(
        make_gate(), "rf-research", environ={}, prompt=lambda _t: True, now=lambda: FIXED
    )
    assert record.decision is Decision.interactive


def test_record_carries_the_text_actually_shown() -> None:
    """Not a reconstruction: the prompt and the record come from one function."""
    shown: list[str] = []

    def prompt(text: str) -> bool:
        shown.append(text)
        return True

    record = resolve_consent(make_gate(), "rf-research", environ={}, prompt=prompt)
    assert shown == [record.disclosure_text]


def test_record_digest_matches_its_text() -> None:
    import hashlib

    record = resolve_consent(make_gate(), "rf-research", environ={ENV_VAR: "1"}, prompt=None)
    assert (
        record.disclosure_sha256
        == hashlib.sha256(record.disclosure_text.encode("utf-8")).hexdigest()
    )


def test_log_entry_is_json_serialisable_and_complete() -> None:
    record = resolve_consent(
        make_gate(), "rf-research", environ={ENV_VAR: "1"}, prompt=None, now=lambda: FIXED
    )
    entry = record.to_log_entry()
    round_tripped = json.loads(json.dumps(entry))
    assert round_tripped["event"] == "consent_affirmed"
    assert round_tripped["profile"] == "rf-research"
    assert round_tripped["decision"] == "environment"
    assert round_tripped["env_var"] == ENV_VAR
    assert set(round_tripped["risk_categories"]) == {
        "unlicensed_transmission",
        "spectrum_disruption",
    }
    assert round_tripped["timestamp"] == "2026-08-26T12:00:00+00:00"


def test_affirmation_reaches_the_transaction_log(tmp_path: Path) -> None:
    log = TransactionLog(tmp_path / "transactions.jsonl")
    record = resolve_consent(make_gate(), "rf-research", environ={ENV_VAR: "1"}, prompt=None)
    log.append(record.to_log_entry())
    entries = list(log.read())
    assert len(entries) == 1
    assert entries[0]["event"] == "consent_affirmed"
    assert entries[0]["decision"] == "environment"


def test_record_is_immutable() -> None:
    record = resolve_consent(make_gate(), "rf-research", environ={ENV_VAR: "1"}, prompt=None)
    with pytest.raises(dataclasses.FrozenInstanceError):
        record.profile = "something-else"  # type: ignore[misc]
    assert isinstance(record, ConsentRecord)


# ---------------------------------------------------------------------------
# The disclosure may not read as legal advice
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "bad",
    [
        "Transmitting without a licence is illegal in most countries, and this can transmit.",
        "Under United States law you may not operate this equipment without authorization.",
        "This is prohibited unless you hold the appropriate authorization for the equipment.",
        "Operating this without authorization would be unlawful and this software can do it.",
        "FCC rules apply to this software and it can drive hardware to transmit.",
        "Using this against systems you do not own is a criminal offence in many places.",
    ],
)
def test_legal_advice_wording_is_rejected(bad: str) -> None:
    """D-021 calls such wording a defect. A defect that ships is not enforced."""
    with pytest.raises((ManifestError, ValidationError)):
        make_gate(disclosure=bad)


@pytest.mark.parametrize(
    "good",
    [
        "This software can cause connected hardware to emit radio frequency energy.",
        "This software can receive and decode communications that may be protected.",
        "Transmitting may require a licence or other authorization depending on where "
        "and how you operate.",
    ],
)
def test_capability_wording_is_accepted(good: str) -> None:
    """The taxonomy is about capability, so capability wording must pass."""
    gate = make_gate(disclosure=good + " " + "It is installed only on request.")
    assert gate.disclosure.startswith(good[:20])


def test_affirmation_must_ask_about_authorization() -> None:
    with pytest.raises((ManifestError, ValidationError)):
        make_gate(affirmation="Do you understand the risks described above?")


def test_env_var_must_be_namespaced() -> None:
    for bad in ("YES", "HAMMUNITION_YES", "ACCEPT_RF", "hammunition_accept_rf"):
        with pytest.raises((ManifestError, ValidationError)):
            make_gate(env_var=bad)


def test_at_least_one_risk_category_is_required() -> None:
    with pytest.raises((ManifestError, ValidationError)):
        make_gate(risk_categories=[])


def test_duplicate_risk_categories_are_rejected() -> None:
    with pytest.raises((ManifestError, ValidationError)):
        make_gate(
            risk_categories=[
                RiskCategory.unlicensed_transmission,
                RiskCategory.unlicensed_transmission,
            ]
        )


# ---------------------------------------------------------------------------
# What the operator sees
# ---------------------------------------------------------------------------


def test_disclosure_names_every_declared_category() -> None:
    text = render_disclosure(make_gate(), "rf-research")
    assert "unlicensed_transmission" in text
    assert "spectrum_disruption" in text
    assert "identifier_collection" not in text


def test_disclosure_disclaims_legal_advice() -> None:
    text = render_disclosure(make_gate(), "rf-research")
    assert "does not give legal advice" in text
    assert "cannot know your location" in text


def test_disclosure_names_the_profile() -> None:
    assert "'rf-research'" in render_disclosure(make_gate(), "rf-research")


# ---------------------------------------------------------------------------
# The real catalog profiles
# ---------------------------------------------------------------------------

from hammunition.manifest.load import CatalogError, load_profiles  # noqa: E402

PROFILES = Path(__file__).resolve().parent.parent / "catalog" / "profiles"


def test_catalog_profiles_load() -> None:
    profiles = load_profiles(PROFILES)
    assert {"rf-research", "rf-security"} <= set(profiles)


def test_gating_is_selective() -> None:
    """D-021: a gate on everything trains people to click through.

    rf-security is the control. If it ever acquires a gate, the rf-research gate
    stops meaning anything, so this asserts the contrast rather than the gate.
    """
    profiles = load_profiles(PROFILES)
    assert profiles["rf-research"].consent is not None
    assert profiles["rf-security"].consent is None


def test_gated_profile_declares_the_transmit_risk() -> None:
    gate = load_profiles(PROFILES)["rf-research"].consent
    assert gate is not None
    assert RiskCategory.unlicensed_transmission in gate.risk_categories


def test_gated_profile_excludes_transmit_capable_cellular() -> None:
    """Q-008's recommendation, asserted so it cannot drift in silently."""
    profile = load_profiles(PROFILES)["rf-research"]
    forbidden = {"srsran-4g", "osmo-trx", "osmo-bsc", "intrusive-lte-mme", "srsran"}
    assert not (forbidden & set(profile.packages)), (
        "transmit-capable cellular stacks are excluded pending Q-008; adding one "
        "here is a scope decision, not a catalog edit"
    )


def test_profile_package_cross_check_fails_loudly(tmp_path: Path) -> None:
    """D-016: a profile that half-resolves is silent degradation."""
    (tmp_path / "demo.yaml").write_text(
        "name: demo\n"
        "summary: demo\n"
        "packages: [fldigi, does-not-exist]\n"
        "documentation:\n"
        "  what_it_installs: A demonstration profile for the cross-check test.\n"
        "  why_together: They are grouped only to exercise validation here.\n"
        "  deliberately_excludes: Everything else.\n"
        "  manual_configuration: None required.\n"
    )
    with pytest.raises(CatalogError) as excinfo:
        load_profiles(tmp_path, packages={"fldigi": None})  # type: ignore[dict-item]
    assert "does-not-exist" in str(excinfo.value)


def test_profile_docs_are_mandatory(tmp_path: Path) -> None:
    (tmp_path / "bare.yaml").write_text("name: bare\nsummary: no docs\npackages: [fldigi]\n")
    with pytest.raises(CatalogError):
        load_profiles(tmp_path)
