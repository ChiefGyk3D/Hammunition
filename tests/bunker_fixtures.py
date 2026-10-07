# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

# tests/bunker_fixtures.py
import hashlib
import json
import subprocess
from pathlib import Path

from hammunition.keystrength import classify


def key(tmp_path: Path, algorithm: str = "ed25519", bits: int | None = None) -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    path = tmp_path / f"key-{algorithm}-{bits or 0}"
    if path.exists() or path.with_suffix(".pub").exists():
        raise FileExistsError(f"test key already exists: {path}")
    argv = ["ssh-keygen", "-q", "-t", algorithm, "-N", "", "-f", str(path)]
    if bits is not None:
        argv += ["-b", str(bits)]
    subprocess.run(argv, check=True, capture_output=True)
    return path


def document(public_key: str, **changes: object) -> dict[str, object]:
    strength = classify(public_key)
    value: dict[str, object] = {
        "kind": "bunker-index",
        "version": 3,
        "serial": 42,
        "generated": "2026-10-07T12:00:00Z",
        "bunker": {"name": "bunker", "mode": "personal"},
        "signers": [
            {
                "id": strength.fingerprint,
                "public_key": public_key,
                "algorithm": strength.algorithm,
                "bits": strength.bits,
                "hardware": False,
                "no_touch_required": False,
                "signature": "catalogue.sig.d/1.sig",
            }
        ],
        "engine_version": "0.22.0",
        "artifacts": [],
        "inputs": [],
        "deferred": [],
        "declined": [],
        "last_run": None,
    }
    value.update(changes)
    return value


def encode(doc: dict[str, object]) -> bytes:
    return json.dumps(doc, ensure_ascii=False).encode("utf-8")


def artifact(unit: str, name: str, body: bytes, **changes: object) -> dict[str, object]:
    value: dict[str, object] = {
        "unit": unit,
        "name": name,
        "path": f"{unit}/{name}",
        "sha256": hashlib.sha256(body).hexdigest(),
        "size": len(body),
        "publisher_check": "sha256",
        "publisher_digest": None,
        "publisher_url": "https://example.invalid/payload",
        "publisher_name": None,
        "publisher_size": None,
        "licence": "CC0-1.0",
        "fetched": "2026-10-06T03:00:00Z",
        "verified": "2026-10-07T03:00:00Z",
        "status": "current",
        "reason": None,
        "previous": None,
        "share": "all",
    }
    value.update(changes)
    return value
