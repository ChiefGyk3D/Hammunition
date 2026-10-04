# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""Atheris target: the package, profile and hardware manifest loaders.

YAML text goes to a temp file the loader reads. The loaders' documented
rejections (schema validation, a non-mapping document, YAML syntax) are caught.
"""

import contextlib
import sys
import tempfile
from pathlib import Path

import atheris
import yaml
from _seeded import REPO, seed_text, text_from
from pydantic import ValidationError

with atheris.instrument_imports():
    from hammunition.manifest.load import load_manifest, load_profile
    from hammunition.manifest.schema import ManifestError

_PACKAGE = seed_text("catalog", "packages", "direwolf.yaml") or seed_text(
    "catalog", "packages", "a2d.yaml"
)
_PROFILE = seed_text("catalog", "profiles", "station.yaml")
_TMP = Path(tempfile.mkdtemp(prefix="fuzz-manifest-"))
_REJECTED = (ValidationError, ManifestError, yaml.YAMLError)


def TestOneInput(data: bytes) -> None:
    fdp = atheris.FuzzedDataProvider(data)
    profile = fdp.ConsumeBool()
    text = text_from(fdp, _PROFILE if profile else _PACKAGE)
    path = _TMP / "m.yaml"
    path.write_text(text, encoding="utf-8")
    with contextlib.suppress(*_REJECTED):
        (load_profile if profile else load_manifest)(path)


if __name__ == "__main__":
    assert REPO.is_dir()
    atheris.Setup(sys.argv, TestOneInput)
    atheris.Fuzz()
