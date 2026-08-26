# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

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
    ambiguous: dict[tuple[str, str], str] = {}
    failures: dict[Path, str] = {}

    for path in sorted(directory.rglob("*.yaml")):
        try:
            data = yaml.safe_load(path.read_text())
            if not isinstance(data, dict):
                raise ManifestError("hardware entry must be a YAML mapping")
            if data.get("kind") == "ambiguity-list":
                for entry in data.get("identifiers") or []:
                    vendor, _, product = str(entry["id"]).partition(":")
                    ambiguous[(vendor, product)] = str(entry["basis"])
            elif data.get("kind") == "class":
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

    # D-028. The generated ambiguity list is only load-bearing if something
    # checks against it. An identifier the kernel classifies as a bridge chip,
    # carried in a manifest without saying so, is exactly the state that lets a
    # symlink rule reach hardware it was never meant to name -- and the symlink
    # check downstream keys off the `ambiguity` block, so an unmarked identifier
    # silently passes it.
    if ambiguous:
        for entry in (*classes.values(), *devices.values()):
            source = (
                f"classes/{entry.name}.yaml"
                if isinstance(entry, DeviceClass)
                else f"devices/{entry.name}.yaml"
            )
            for usb in entry.usb_ids:
                if usb.product is None or usb.ambiguity is not None:
                    continue
                basis = ambiguous.get((usb.vendor.lower(), usb.product.lower()))
                if basis is not None:
                    failures[directory / source] = (
                        f"{entry.name!r} carries {usb.vendor}:{usb.product} with no "
                        f"`ambiguity` block, but the generated list marks it "
                        f"{basis} — it names a chip, not a device. Add the block, or "
                        f"regenerate the list if the evidence has changed (D-028)."
                    )

    if failures:
        raise CatalogError(failures)
    return classes, devices
