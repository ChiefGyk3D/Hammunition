"""Load and validate catalog manifests."""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import ValidationError

from .hardware import DeviceClass, DeviceManifest
from .schema import ManifestError, PackageManifest, ProfileManifest

__all__ = [
    "CatalogError",
    "load_catalog",
    "load_hardware",
    "load_manifest",
    "load_profile",
    "load_profiles",
]


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


def load_profile(path: Path) -> ProfileManifest:
    data = yaml.safe_load(path.read_text())
    if not isinstance(data, dict):
        raise ManifestError(f"{path}: profile must be a YAML mapping")
    return ProfileManifest.model_validate(data)


def load_profiles(
    directory: Path, packages: dict[str, PackageManifest] | None = None
) -> dict[str, ProfileManifest]:
    """Load every profile, reporting *all* failures together — D-016.

    When ``packages`` is supplied, a profile naming a package that is not in the
    catalog is a failure rather than a warning. A profile that half-resolves is
    the silent degradation D-016 forbids: the operator asked for a named set and
    would get some of it without being told which part is missing.
    """
    profiles: dict[str, ProfileManifest] = {}
    failures: dict[Path, str] = {}

    for path in sorted(directory.glob("*.yaml")):
        try:
            profile = load_profile(path)
        except (ValidationError, ManifestError, yaml.YAMLError) as exc:
            failures[path] = str(exc).split("\n")[0]
            continue
        if profile.name in profiles:
            failures[path] = f"duplicate profile name {profile.name!r}"
            continue
        if packages is not None:
            missing = [p for p in profile.packages if p not in packages]
            if missing:
                failures[path] = (
                    f"profile {profile.name!r} names packages with no manifest: "
                    f"{', '.join(sorted(missing))}"
                )
                continue
        profiles[profile.name] = profile

    if failures:
        raise CatalogError(failures)
    return profiles


def load_hardware(
    directory: Path,
) -> tuple[dict[str, DeviceClass], dict[str, DeviceManifest]]:
    """Load `catalog/hardware/`, reporting all failures together — D-016.

    A device naming a `device_class` that does not exist is a failure: the class
    is where its udev rules and tooling come from, so a dangling reference means
    the device silently gets none of them.
    """
    classes: dict[str, DeviceClass] = {}
    devices: dict[str, DeviceManifest] = {}
    failures: dict[Path, str] = {}

    for path in sorted(directory.rglob("*.yaml")):
        try:
            data = yaml.safe_load(path.read_text())
            if not isinstance(data, dict):
                raise ManifestError("hardware entry must be a YAML mapping")
            if data.get("kind") == "class":
                entry_class = DeviceClass.model_validate(data)
                if entry_class.name in classes:
                    raise ManifestError(f"duplicate device class {entry_class.name!r}")
                classes[entry_class.name] = entry_class
            else:
                device = DeviceManifest.model_validate(data)
                if device.name in devices:
                    raise ManifestError(f"duplicate device {device.name!r}")
                devices[device.name] = device
        except (ValidationError, ManifestError, yaml.YAMLError) as exc:
            failures[path] = str(exc).split("\n")[0]

    for name, device in devices.items():
        if device.device_class and device.device_class not in classes:
            failures[directory / f"{name}.yaml"] = (
                f"device {name!r} references unknown device_class {device.device_class!r}"
            )

    if failures:
        raise CatalogError(failures)
    return classes, devices
