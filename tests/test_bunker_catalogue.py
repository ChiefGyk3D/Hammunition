# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

from pathlib import Path

# tests/test_bunker_catalogue.py
import pytest

from bunker_fixtures import artifact, document, encode, key
from hammunition.catalogue import CatalogueError, parse
from hammunition.keystrength import classify


@pytest.mark.parametrize(
    "algorithm,bits,rank,weak",
    [
        ("ed25519", None, 1, False),
        ("ecdsa", 384, 2, False),
        ("ecdsa", 256, 2, False),
        ("ecdsa", 521, 2, False),
        ("rsa", 2560, 4, False),
        ("rsa", 4096, 3, False),
        ("rsa", 2048, 5, True),
    ],
)
def test_real_key_strength(
    tmp_path: Path, algorithm: str, bits: int | None, rank: int, weak: bool
) -> None:
    private = key(tmp_path, algorithm, bits)
    got = classify(private.with_suffix(".pub").read_text().strip())
    assert (got.rank, got.weak) == (rank, weak)
    assert not got.hardware_by_type
    assert got.warning == (
        "RSA 2048-bit is weak: replace with Ed25519, ECDSA or RSA 3072+" if weak else None
    )


@pytest.mark.parametrize(
    "field,value",
    [
        ("version", 4),
        ("version", True),
        ("serial", 0),
        ("serial", True),
        ("generated", "2026-10-07T12:00:00+01:00"),
        ("bunker", {"name": "../x", "mode": "personal"}),
        ("signers", []),
    ],
)
def test_field_refusals(tmp_path: Path, field: str, value: object) -> None:
    public = key(tmp_path).with_suffix(".pub").read_text().strip()
    with pytest.raises(CatalogueError, match=field):
        parse(encode(document(public, **{field: value})))


def test_duplicate_artifact_and_signature_traversal(tmp_path: Path) -> None:
    public = key(tmp_path).with_suffix(".pub").read_text().strip()
    row = artifact("osm-regions", "europe/monaco", b"pbf")
    with pytest.raises(CatalogueError, match="artifacts"):
        parse(encode(document(public, artifacts=[row, row])))
    doc = document(public)
    signers = doc["signers"]
    assert isinstance(signers, list)
    signers[0]["signature"] = "catalogue.sig.d/../escape.sig"
    with pytest.raises(CatalogueError, match="signers"):
        parse(encode(doc))


def test_group_filter_is_not_a_parse_filter(tmp_path: Path) -> None:
    public = key(tmp_path).with_suffix(".pub").read_text().strip()
    row = artifact("acma-register", "spectra_rrl.zip", b"zip", share="owner:laptop-a")
    cat = parse(
        encode(document(public, bunker={"name": "bunker", "mode": "group"}, artifacts=[row]))
    )
    assert len(cat.artifacts) == 1
    assert cat.artifact("acma-register", "spectra_rrl.zip", "laptop-b") is None
    assert cat.artifact("acma-register", "spectra_rrl.zip", "laptop-a") is not None


def test_failed_v2_entry_is_preserved_but_not_usable(tmp_path: Path) -> None:
    public = key(tmp_path).with_suffix(".pub").read_text().strip()
    failed = artifact(
        "osm-regions",
        "europe/monaco",
        b"unused",
        path=None,
        sha256=None,
        size=None,
        fetched=None,
        verified=None,
        status="failed",
        reason="HTTP 503",
    )
    cat = parse(encode(document(public, artifacts=[failed])))
    assert cat.artifacts[0].path is None and cat.artifacts[0].status == "failed"


def test_fresh_bunker_has_empty_payload_lists(tmp_path: Path) -> None:
    private = key(tmp_path)
    public = private.with_suffix(".pub").read_text().strip()
    got = parse(encode(document(public, artifacts=[], inputs=[])))
    assert got.artifacts == () and got.inputs == ()
    assert len(got.signers) == 1
    with pytest.raises(CatalogueError, match="signers"):
        parse(encode(document(public, artifacts=[], inputs=[], signers=[])))


@pytest.fixture
def wire(tmp_path: Path) -> dict[str, object]:
    public = key(tmp_path).with_suffix(".pub").read_text().strip()
    return document(
        public,
        artifacts=[artifact("osm-regions", "europe/monaco", b"pbf")],
        inputs=[
            {
                "kind": "region-outline",
                "region": "europe/monaco",
                "name": "europe/monaco.poly",
                "path": "inputs/region-outline/europe/monaco.poly",
                "sha256": "a" * 64,
                "size": 1,
                "fetched": "2026-10-06T03:00:00Z",
            }
        ],
    )


FIELDS = {
    "root": "kind version serial generated bunker signers engine_version artifacts inputs deferred declined last_run",
    "bunker": "name mode",
    "signers": "id public_key algorithm bits hardware no_touch_required signature",
    "artifacts": "unit name path sha256 size publisher_check publisher_digest publisher_url publisher_name publisher_size licence fetched verified status reason previous share",
    "inputs": "kind region name path sha256 size fetched",
}
NULLABLE = {
    "root": {"engine_version", "last_run"},
    "artifacts": {
        "path",
        "sha256",
        "size",
        "publisher_digest",
        "publisher_name",
        "publisher_size",
        "fetched",
        "verified",
        "reason",
        "previous",
    },
}


def section(wire: dict[str, object], group: str) -> dict[str, object]:
    if group == "root":
        return wire
    value = wire[group]
    if isinstance(value, list):
        value = value[0]
    assert isinstance(value, dict)
    return value


@pytest.mark.parametrize("group,field", [(g, f) for g, fs in FIELDS.items() for f in fs.split()])
@pytest.mark.parametrize("mutation", ["missing", "null", "wrong"])
def test_required_field_types(
    wire: dict[str, object], group: str, field: str, mutation: str
) -> None:
    row = section(wire, group)
    if mutation == "missing":
        del row[field]
    elif mutation == "null":
        if field in NULLABLE.get(group, set()):
            row[field] = None
            # Publisher measurement fields must be null together.
            if field in {"publisher_name", "publisher_size"}:
                row["publisher_name"] = row["publisher_size"] = None
            parse(encode(wire))
            return
        row[field] = None
    else:
        if field == "last_run":
            return  # Any JSON value is permitted.
        row[field] = (
            {}
            if group == "root"
            and field in {"deferred", "declined", "artifacts", "inputs", "signers"}
            else []
        )
    with pytest.raises(CatalogueError, match=field):
        parse(encode(wire))


@pytest.mark.parametrize(
    "group,field,value",
    [
        ("root", "kind", "other"),
        ("root", "generated", "2026-02-30T12:00:00Z"),
        ("bunker", "mode", "other"),
        ("signers", "algorithm", "ssh-rsa"),
        ("signers", "bits", 123),
        ("signers", "bits", True),
        ("signers", "id", "SHA256:wrong"),
        ("signers", "no_touch_required", True),
        ("signers", "hardware", "true"),
        ("signers", "signature", "elsewhere/1.sig"),
        ("inputs", "kind", "other"),
        ("inputs", "region", "../monaco"),
        ("inputs", "path", "wrong/path"),
        ("inputs", "size", -1),
        ("artifacts", "size", -1),
        ("artifacts", "size", "1"),
        ("artifacts", "size", True),
        ("artifacts", "sha256", "A" * 64),
        ("inputs", "sha256", "bad"),
        ("artifacts", "previous", "../escape"),
        ("artifacts", "path", "/escape"),
        ("artifacts", "name", "a//b"),
        ("artifacts", "unit", "a/b"),
        ("artifacts", "share", "owner:a\r\nb"),
        ("artifacts", "share", "owner:"),
        ("artifacts", "publisher_size", -1),
        ("artifacts", "publisher_size", 0),
        ("artifacts", "publisher_name", "../bad"),
        ("artifacts", "verified", "2026-13-01T00:00:00Z"),
        ("inputs", "fetched", "2026-10-07T00:00:00+00:00"),
    ],
)
def test_semantic_refusals(wire: dict[str, object], group: str, field: str, value: object) -> None:
    section(wire, group)[field] = value
    with pytest.raises(CatalogueError, match=field):
        parse(encode(wire))


@pytest.mark.parametrize("group", ["signers", "inputs"])
def test_duplicate_identities(wire: dict[str, object], group: str) -> None:
    rows = wire[group]
    assert isinstance(rows, list)
    rows.append(rows[0])
    with pytest.raises(CatalogueError, match=group):
        parse(encode(wire))


@pytest.mark.parametrize("raw", [b"\xff", b"{", b"[]", b'{"version":3,"version":3}'])
def test_invalid_json(raw: bytes) -> None:
    with pytest.raises(CatalogueError):
        parse(raw)


@pytest.mark.parametrize("value", ["", "ssh-dss AAAA", "ssh-ed25519 !!!!"])
def test_invalid_keys(value: str) -> None:
    with pytest.raises(ValueError, match="public_key"):
        classify(value)


def test_key_prefix_and_multiline(wire: dict[str, object]) -> None:
    public = section(wire, "signers")["public_key"]
    assert isinstance(public, str)
    for value in [
        public + "\n" + public,
        public.replace("ssh-ed25519", "sk-ssh-ed25519@openssh.com", 1),
    ]:
        with pytest.raises(ValueError, match="public_key"):
            classify(value)


def test_lookup_and_forward_fields(wire: dict[str, object]) -> None:
    wire["future"] = {"value": 1}
    section(wire, "artifacts")["status"] = "upstream-status"
    cat = parse(encode(wire))
    assert cat.input("region-outline", "europe/monaco") is not None
    assert cat.input("tile-selection", "europe/monaco") is None
    assert cat.artifact("missing", "missing", None) is None
    assert cat.artifact("osm-regions", "europe/monaco", None) is not None
    section(wire, "artifacts")["path"] = None
    assert parse(encode(wire)).artifact("osm-regions", "europe/monaco", None) is None


@pytest.mark.parametrize(
    "value", ["", "/a", "a/", "a//b", ".", "..", "a/../b", "a\\b", "a\n", "a\r", "a\x00"]
)
def test_relative_path_rules(value: str) -> None:
    from hammunition.catalogue import safe_relative

    with pytest.raises(CatalogueError, match="path"):
        safe_relative(value, "path")


@pytest.mark.parametrize(
    "value,valid",
    [
        ("opaque/id", True),
        ("laptop-a", True),
        ("", False),
        ("a b", False),
        ("a\t", False),
        ("a\r\nb", False),
        ("é", False),
    ],
)
def test_enrolment_id(value: str, valid: bool) -> None:
    from hammunition.catalogue import valid_enrolment_id

    assert valid_enrolment_id(value) is valid


@pytest.mark.parametrize(
    "kind",
    [
        "region-outline",
        "tile-selection",
        "sheet-selection",
        "dem3dep-selection",
        "fstopo-selection",
    ],
)
def test_input_kinds(wire: dict[str, object], kind: str) -> None:
    row = section(wire, "inputs")
    row["kind"] = kind
    row["path"] = f"inputs/{kind}/{row['name']}"
    assert parse(encode(wire)).input(kind, "europe/monaco") is not None


def test_failed_and_current_entries(wire: dict[str, object]) -> None:
    rows = wire["artifacts"]
    assert isinstance(rows, list)
    rows.append(
        artifact(
            "other",
            "failed",
            b"",
            path=None,
            sha256=None,
            size=None,
            fetched=None,
            verified=None,
            status="failed",
            reason="HTTP 503",
        )
    )
    cat = parse(encode(wire))
    assert len(cat.artifacts) == 2
    assert cat.artifact("other", "failed", None) is None
    assert cat.artifact("osm-regions", "europe/monaco", None) is not None


def test_duplicate_signature_path(wire: dict[str, object], tmp_path: Path) -> None:
    second = document(key(tmp_path / "second").with_suffix(".pub").read_text().strip())
    rows = wire["signers"]
    other = second["signers"]
    assert isinstance(rows, list) and isinstance(other, list)
    rows.extend(other)
    with pytest.raises(CatalogueError, match=r"signers\.signature"):
        parse(encode(wire))


def test_security_key_type_without_token(wire: dict[str, object]) -> None:
    # Wrap a freshly generated Ed25519 public blob in the OpenSSH sk public
    # format. Classification needs no private key or attached signing token.
    import base64
    import struct

    row = section(wire, "signers")
    public = row["public_key"]
    assert isinstance(public, str)
    blob = base64.b64decode(public.split()[1])
    length = struct.unpack(">I", blob[:4])[0]
    algorithm = "sk-ssh-ed25519@openssh.com"
    application = b"ssh:test"
    wrapped = (
        struct.pack(">I", len(algorithm))
        + algorithm.encode()
        + blob[4 + length :]
        + struct.pack(">I", len(application))
        + application
    )
    sk = algorithm + " " + base64.b64encode(wrapped).decode()
    strength = classify(sk)
    assert strength.hardware_by_type and strength.rank == 1
    row.update(
        public_key=sk,
        algorithm=algorithm,
        bits=strength.bits,
        id=strength.fingerprint,
        hardware=True,
        no_touch_required=True,
    )
    assert parse(encode(wire)).signers[0].no_touch_required
    row["hardware"] = False
    with pytest.raises(CatalogueError, match="hardware"):
        parse(encode(wire))
