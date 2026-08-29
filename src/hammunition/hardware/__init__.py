# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""Hardware support: turning the device catalog into things a machine does.

**D-029.** The hardware role is permissions, composite-device mapping,
firmware-mode identification, and honest documentation of what nothing solves.
Persistent udev symlinks are one tactic used where the evidence supports one,
not the headline.
"""

from .udev import RULES_PATH, Omission, RuleSet, rules_file, rules_for

__all__ = ["RULES_PATH", "Omission", "RuleSet", "rules_file", "rules_for"]
