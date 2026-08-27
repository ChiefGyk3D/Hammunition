# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""Distribution detection.  DESIGN.md §8 — /etc/os-release, no heuristics."""

from .detect import (
    DEBIAN_FAMILY,
    OS_RELEASE_PATHS,
    DetectionError,
    Target,
    parse_os_release,
    read_os_release,
)

__all__ = [
    "DEBIAN_FAMILY",
    "OS_RELEASE_PATHS",
    "DetectionError",
    "Target",
    "parse_os_release",
    "read_os_release",
]
