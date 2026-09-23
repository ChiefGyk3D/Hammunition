# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""Hardware support: turning the device catalog into things a machine does.

**D-029.** The hardware role is permissions, composite-device mapping,
firmware-mode identification, and honest documentation of what nothing solves.
Persistent udev symlinks are one tactic used where the evidence supports one,
not the headline.
"""

from .apply import HardwarePlan, plan_hardware
from .detect import AttachedDevice, Match, match_catalog, read_usb_bus
from .power import (
    Parkable,
    PowerError,
    PowerPlan,
    Write,
    execute,
    guard,
    parkable,
    plan_park,
    plan_wake,
)
from .udev import RULES_PATH, Omission, RuleSet, rules_file, rules_for

__all__ = [
    "RULES_PATH",
    "AttachedDevice",
    "HardwarePlan",
    "Match",
    "Omission",
    "Parkable",
    "PowerError",
    "PowerPlan",
    "RuleSet",
    "Write",
    "execute",
    "guard",
    "match_catalog",
    "parkable",
    "plan_hardware",
    "plan_park",
    "plan_wake",
    "read_usb_bus",
    "rules_file",
    "rules_for",
]
