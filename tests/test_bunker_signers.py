# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

import json
import os
import pwd
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from bunker_fixtures import document, key, signed
from hammunition.catalogue import CatalogueError
from hammunition.keystrength import classify
from hammunition.signers import (
    EnrolledKey,
    MirrorState,
    SignerError,
    advance_mirror,
    allowed_signers,
    clear_mirror,
    load_mirror,
    mirror_path,
    save_mirror,
    validate_state,
    verify,
)


@pytest.mark.parametrize(
    "algorithm,bits", [("ed25519", None), ("ecdsa", 384), ("rsa", 4096), ("rsa", 2048)]
)
def test_real_signatures_and_policy(tmp_path: Path, algorithm: str, bits: int | None) -> None:
    private = key(tmp_path, algorithm, bits)
    public = private.with_suffix(".pub").read_text().strip()
    strength = classify(public)
    enrolled = EnrolledKey(strength.fingerprint, public, strength.algorithm, strength.bits, False)
    state = MirrorState("http://bunker.invalid/", "bunker", "personal", None, (enrolled,), 41)
    raw, sigs = signed(tmp_path, private, document(public))
    verified = verify(raw, sigs, state, now=datetime(2026, 10, 7, tzinfo=UTC))
    assert verified.key == enrolled
    assert bool(verified.strength.warning) == (bits == 2048)
    with pytest.raises(SignerError, match="hardware"):
        verify(raw, sigs, state, require_hardware=True, now=datetime(2026, 10, 7, tzinfo=UTC))
    with pytest.raises(SignerError, match="signature"):
        verify(raw + b" ", sigs, state, now=datetime(2026, 10, 7, tzinfo=UTC))
    with pytest.raises(SignerError, match="accept-older"):
        verify(raw, sigs, replace(state, accepted_serial=43), now=datetime(2026, 10, 7, tzinfo=UTC))
    stale = verify(raw, sigs, state, now=datetime(2026, 11, 8, tzinfo=UTC))
    assert any("30 days" in w for w in stale.warnings)
    stored = tmp_path / "config" / "mirror.json"
    save_mirror(state, stored)
    assert stored.stat().st_mode & 0o777 == 0o600
    assert load_mirror(stored) == state
    save_mirror(replace(state, accepted_serial=43), stored)
    with pytest.raises(SignerError, match="serial"):
        save_mirror(state, stored)
    current = load_mirror(stored)
    assert current is not None and current.accepted_serial == 43


def test_concurrent_verifications_preserve_highest_serial(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    private = key(tmp_path)
    public = private.with_suffix(".pub").read_text().strip()
    strength = classify(public)
    enrolled = EnrolledKey(strength.fingerprint, public, strength.algorithm, strength.bits, False)
    state = MirrorState("http://bunker.invalid", "bunker", "personal", None, (enrolled,), 42)
    save_mirror(state)

    def advance(serial: int) -> None:
        advance_mirror(state, serial, "2026-10-07T12:00:00Z")

    with ThreadPoolExecutor(max_workers=2) as executor:
        list(executor.map(advance, [44, 43]))
    current = load_mirror()
    assert current is not None and current.accepted_serial == 44


@pytest.fixture
def enrolled_state(tmp_path: Path) -> tuple[Path, MirrorState]:
    private = key(tmp_path)
    public = private.with_suffix(".pub").read_text().strip()
    measured = classify(public)
    enrolled = EnrolledKey(measured.fingerprint, public, measured.algorithm, measured.bits, False)
    return private, MirrorState(
        "http://bunker.invalid", "bunker", "personal", None, (enrolled,), 42
    )


def test_freshness_and_local_hardware(
    tmp_path: Path, enrolled_state: tuple[Path, MirrorState]
) -> None:
    private, state = enrolled_state
    doc = document(state.keys[0].public_key)
    rows = doc["signers"]
    assert isinstance(rows, list)
    rows[0]["hardware"] = True
    raw, sigs = signed(tmp_path, private, doc)
    boundary = datetime(2026, 11, 6, 12, tzinfo=UTC)
    assert verify(raw, sigs, state, now=boundary).warnings == ()
    assert verify(raw, sigs, state, now=boundary + timedelta(microseconds=1)).warnings
    with pytest.raises(SignerError, match="hardware"):
        verify(raw, sigs, state, now=boundary, require_hardware=True)
    affirmed = replace(state, keys=(replace(state.keys[0], hardware=True),))
    assert verify(raw, sigs, affirmed, now=boundary, require_hardware=True).key.hardware
    with pytest.raises(SignerError, match=r"bunker\.name"):
        verify(raw, sigs, replace(state, name="other"), now=boundary)
    with pytest.raises(SignerError, match="signature"):
        verify(raw, {}, state, now=boundary)


@pytest.mark.parametrize("first", [None, b"bad signature"])
def test_later_enrolled_signature_succeeds(
    tmp_path: Path, enrolled_state: tuple[Path, MirrorState], first: bytes | None
) -> None:
    _, state = enrolled_state
    other = key(tmp_path / "other")
    public = other.with_suffix(".pub").read_text().strip()
    measured = classify(public)
    enrolled = EnrolledKey(measured.fingerprint, public, measured.algorithm, measured.bits, False)
    doc = document(state.keys[0].public_key)
    rows = doc["signers"]
    assert isinstance(rows, list)
    extra = document(public)["signers"]
    assert isinstance(extra, list)
    extra[0]["signature"] = "catalogue.sig.d/2.sig"
    rows.extend(extra)
    raw, sigs = signed(tmp_path, other, doc)
    sigs["catalogue.sig.d/2.sig"] = sigs.pop("catalogue.sig.d/1.sig")
    if first is not None:
        sigs["catalogue.sig.d/1.sig"] = first
    now = datetime(2026, 10, 7, tzinfo=UTC)
    with pytest.raises(SignerError, match="signature"):
        verify(raw, sigs, state, now=now)
    assert verify(raw, sigs, replace(state, keys=(*state.keys, enrolled)), now=now).key == enrolled


@pytest.mark.parametrize("field", ["id", "public_key"])
def test_forged_signer_metadata(
    tmp_path: Path, enrolled_state: tuple[Path, MirrorState], field: str
) -> None:
    private, state = enrolled_state
    other = key(tmp_path / "other")
    doc = document(state.keys[0].public_key)
    rows = doc["signers"]
    assert isinstance(rows, list)
    rows[0][field] = (
        "SHA256:forged" if field == "id" else other.with_suffix(".pub").read_text().strip()
    )
    raw, sigs = signed(tmp_path, private, doc)
    with pytest.raises(CatalogueError, match="id"):
        verify(raw, sigs, state, now=datetime(2026, 10, 7, tzinfo=UTC))


@pytest.mark.parametrize("filename", ["mirror.json", "mirror.lock"])
def test_store_refuses_symlinks(
    tmp_path: Path, enrolled_state: tuple[Path, MirrorState], filename: str
) -> None:
    _, state = enrolled_state
    parent = tmp_path / "store"
    parent.mkdir()
    victim = tmp_path / "victim"
    victim.write_bytes(b"untouched")
    (parent / filename).symlink_to(victim)
    with pytest.raises(SignerError):
        save_mirror(state, parent / "mirror.json")
    assert victim.read_bytes() == b"untouched"


@pytest.mark.parametrize(
    "change",
    [
        {"accepted_serial": True},
        {"keys": []},
        {"name": "bad,name"},
        {"mode": "bad"},
        {"enrolment_id": "bad id"},
        {"generated": "bad"},
        {"extra": 1},
    ],
)
def test_corrupt_store_refused(
    tmp_path: Path, enrolled_state: tuple[Path, MirrorState], change: dict[str, object]
) -> None:
    _, state = enrolled_state
    path = tmp_path / "mirror.json"
    save_mirror(state, path)
    doc = json.loads(path.read_text())
    doc.update(change)
    path.write_text(json.dumps(doc))
    with pytest.raises(SignerError):
        load_mirror(path)


def test_no_touch_requires_sk(enrolled_state: tuple[Path, MirrorState]) -> None:
    _, state = enrolled_state
    with pytest.raises(SignerError, match="no_touch_required"):
        validate_state(replace(state, keys=(replace(state.keys[0], no_touch_required=True),)))
    assert "no-touch-required" not in allowed_signers(state)


def test_clear_and_advance_enrolment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, enrolled_state: tuple[Path, MirrorState]
) -> None:
    _, state = enrolled_state
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    assert load_mirror() is None
    clear_mirror()
    path = save_mirror(state)
    lock = path.with_name("mirror.lock")
    inode = lock.stat().st_ino
    with pytest.raises(SignerError, match="enrolment changed"):
        advance_mirror(replace(state, enrolment_id="other"), 43, "2026-10-07T12:00:00Z")
    advance_mirror(state, 42, "2026-10-07T12:00:00Z")
    current = load_mirror()
    assert current is not None and current.generated == "2026-10-07T12:00:00Z"
    save_mirror(replace(state, accepted_serial=0), allow_older=True)
    clear_mirror()
    clear_mirror()
    assert load_mirror() is None
    assert lock.stat().st_ino == inode


def test_owner_handoff(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, enrolled_state: tuple[Path, MirrorState]
) -> None:
    _, state = enrolled_state
    uid, gid = os.geteuid(), os.getegid()
    entry = pwd.struct_passwd(("operator", "x", uid, gid, "", str(tmp_path), "/bin/sh"))
    monkeypatch.setattr(os, "geteuid", lambda: 0)
    monkeypatch.setattr(pwd, "getpwnam", lambda name: entry)
    real_replace = os.replace
    observed: list[int] = []

    def check_replace(src: str, dst: str, *, src_dir_fd: int, dst_dir_fd: int) -> None:
        observed.append(os.stat(src, dir_fd=src_dir_fd).st_uid)
        real_replace(src, dst, src_dir_fd=src_dir_fd, dst_dir_fd=dst_dir_fd)

    monkeypatch.setattr(os, "replace", check_replace)
    path = save_mirror(state, tmp_path / "store" / "mirror.json", owner="operator")
    assert observed == [uid]
    assert path.stat().st_uid == uid
    assert load_mirror(path, owner="operator") == state
    assert mirror_path("operator").is_relative_to(tmp_path)


def test_existing_lock_wrong_owner(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, enrolled_state: tuple[Path, MirrorState]
) -> None:
    _, state = enrolled_state
    path = tmp_path / "mirror.json"
    save_mirror(state, path)
    entry = pwd.struct_passwd(
        ("operator", "x", os.geteuid() + 1, os.getegid(), "", str(tmp_path), "/bin/sh")
    )
    monkeypatch.setattr(os, "geteuid", lambda: 0)
    monkeypatch.setattr(pwd, "getpwnam", lambda name: entry)
    with pytest.raises(SignerError, match="another account"):
        load_mirror(path, owner="operator")


@pytest.mark.parametrize(
    "field,value", [("accepted_serial", True), ("hardware", 1), ("no_touch_required", 0)]
)
def test_direct_state_types_refused(
    enrolled_state: tuple[Path, MirrorState], field: str, value: object
) -> None:
    _, state = enrolled_state
    changes = {field: value}
    invalid = (
        replace(state, **changes)
        if field == "accepted_serial"
        else replace(state, keys=(replace(state.keys[0], **changes),))
    )
    with pytest.raises(SignerError, match=field):
        validate_state(invalid)


@pytest.mark.parametrize("filename", ["mirror.json", "mirror.lock"])
def test_store_permissions_refused(
    tmp_path: Path, enrolled_state: tuple[Path, MirrorState], filename: str
) -> None:
    _, state = enrolled_state
    path = save_mirror(state, tmp_path / "store" / "mirror.json")
    path.with_name(filename).chmod(0o644)
    with pytest.raises(SignerError, match="0600"):
        load_mirror(path)


def test_store_key_metadata_refused(
    tmp_path: Path, enrolled_state: tuple[Path, MirrorState]
) -> None:
    _, state = enrolled_state
    path = save_mirror(state, tmp_path / "mirror.json")
    doc = json.loads(path.read_text())
    doc["keys"][0]["bits"] = 4096
    path.write_text(json.dumps(doc))
    with pytest.raises(SignerError, match="metadata"):
        load_mirror(path)


def test_sk_touch_metadata_roundtrip(
    tmp_path: Path, enrolled_state: tuple[Path, MirrorState]
) -> None:
    import base64
    import struct

    _, state = enrolled_state
    blob = base64.b64decode(state.keys[0].public_key.split()[1])
    length = struct.unpack(">I", blob[:4])[0]
    algorithm = "sk-ssh-ed25519@openssh.com"
    application = b"ssh:"
    wrapped = (
        struct.pack(">I", len(algorithm))
        + algorithm.encode()
        + blob[4 + length :]
        + struct.pack(">I", len(application))
        + application
    )
    public = algorithm + " " + base64.b64encode(wrapped).decode()
    measured = classify(public)
    enrolled = EnrolledKey(measured.fingerprint, public, algorithm, 256, True, True)
    state = replace(state, keys=(enrolled,))
    path = save_mirror(state, tmp_path / "mirror.json")
    assert load_mirror(path) == state
    assert (
        allowed_signers(state)
        == f'bunker:bunker namespaces="hammunition-bunker-catalogue" {public}\n'
    )
    with pytest.raises(SignerError, match="hardware"):
        validate_state(replace(state, keys=(replace(enrolled, hardware=False),)))
