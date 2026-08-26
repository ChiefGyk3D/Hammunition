"""Load and validate catalog manifests."""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import ValidationError

from .schema import ManifestError, PackageManifest

__all__ = ["load_manifest", "load_catalog", "CatalogError"]


class CatalogError(Exception):
    """One or more manifests failed validation. Carries every failure, not the first."""

    def __init__(self, failures: dict[Path, str]) -> None:
        self.failures = failures
        detail = "\n".join(f"  {p.name}: {e}" for p, e in failures.items())
        super().__init__(f"{len(failures)} manifest(s) failed validation:\n{detail}")


def load_manifest(path: Path) -> PackageManifest:
    data = yaml.safe_load(path.read_text())
    if not isinstance(data, dict):
        raise ManifestError(f"{path}: manifest must be a YAML mapping")
    return PackageManifest.model_validate(data)


def load_catalog(directory: Path) -> dict[str, PackageManifest]:
    """Load every manifest, reporting *all* failures rather than aborting on the
    first — D-016: resolve everything, then report together."""
    manifests: dict[str, PackageManifest] = {}
    failures: dict[Path, str] = {}

    for path in sorted(directory.glob("*.yaml")):
        try:
            manifest = load_manifest(path)
        except (ValidationError, ManifestError, yaml.YAMLError) as exc:
            failures[path] = str(exc).split("\n")[0]
            continue
        if manifest.name in manifests:
            failures[path] = f"duplicate package name {manifest.name!r}"
            continue
        manifests[manifest.name] = manifest

    if failures:
        raise CatalogError(failures)
    return manifests
