# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""What the running kernel carries, read from ``/lib/modules/<release>``.

Linux 7.1 removed the amateur-radio networking subsystem -- ``net/ax25``,
``net/netrom``, ``net/rose`` and every driver in ``drivers/net/hamradio``
(mkiss, 6pack, bpqether, baycom, scc, yam) -- in merge 64edfa65 of
2026-04-24, and Debian dropped ``ax25-tools`` from testing on 2026-09-01
when it stopped building against the headers that went with it (#1143282).
A kernel is a fact about the machine, not the distribution: one Pop!_OS
24.04 VM carries ``ax25.ko.zst`` in its 7.0.11 module tree and nothing in
its 7.1.5 one (both measured 2026-09-04), so this is read at plan time and
never written into the capability matrix.

The check reads the module tree rather than ``lsmod`` or ``/proc/net/ax25``,
which only say whether the module is *loaded*: on every kernel that carries
it, ``ax25`` is a module that a root ``kissattach`` autoloads, and an
unloaded module is not a missing one.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Final

# feature name (the manifest's `requires_kernel` vocabulary) -> the module's
# path under /lib/modules/<release>/kernel/, without the compression suffix.
# Only what has been measured is here; `KernelProbe.available` raises on
# anything else, so a manifest cannot name a feature the probe cannot see.
FEATURES: Final = MappingProxyType({"ax25": "kernel/net/ax25/ax25.ko"})

# How the plan names each feature to the operator.
DESCRIBE: Final = MappingProxyType({"ax25": "the kernel's AX.25 stack (module ax25)"})

KERNEL_REMOVAL: Final = (
    "Linux 7.1 removed net/ax25 and the hamradio drivers (merge 64edfa65, 2026-04-24)"
)

# What still works without the subsystem, and what does not. Direwolf speaks
# KISS and AGW over TCP to pat (`ax25+agwpe`), linbpq, yaac and xastir with no
# kernel AX.25 at all; only the kernel-interface tools (kissattach, axparms,
# axlisten, the ax25-* daemons) have nothing to attach to.
USERSPACE_PATH: Final = (
    "the userspace packet path is unaffected -- Direwolf's KISS and AGW ports serve "
    "pat (transport `ax25+agwpe`), linbpq, yaac and xastir without kernel AX.25"
)

# No distribution packages the out-of-tree module that was proposed when the
# subsystem was removed, and Hammunition never builds a kernel module of its
# own (a custom kernel is on the rejected list; D-024 carries only what a
# distribution packages).
NO_MODULE_BUILD: Final = (
    "no distribution packages the out-of-tree module yet, and Hammunition never "
    "builds a kernel module (D-024)"
)


@dataclass(frozen=True)
class KernelProbe:
    release: str
    """``uname -r``; the directory under ``modules_root`` that is read."""

    modules_root: Path = Path("/lib/modules")

    @classmethod
    def detect(cls) -> KernelProbe:
        import os

        return cls(release=os.uname().release)

    def available(self, feature: str) -> bool | None:
        """``True`` when the module is shipped or built in, ``False`` when the
        kernel's module tree exists and lacks it, ``None`` when there is no
        module tree for this release to read -- a container on the host's
        kernel, typically -- which is not evidence either way."""
        module = FEATURES[feature]
        tree = self.modules_root / self.release
        if not tree.is_dir():
            return None
        target = tree / module
        if any(target.parent.glob(f"{target.name}*")):
            return True
        builtin = tree / "modules.builtin"
        return builtin.is_file() and module in builtin.read_text().split()
