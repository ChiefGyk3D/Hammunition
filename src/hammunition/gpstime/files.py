# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""Every path GPS time reads or writes.  D-058.

Read as ``files.NAME`` at call time, never imported by value, so one test
fixture can point all of them at a temporary tree.
"""

from __future__ import annotations

__all__ = [
    "APPARMOR_LOCAL",
    "APPARMOR_PROFILE",
    "DHCP_CONF",
    "DROPIN",
    "NTPSEC_DEFAULT",
    "NTP_CONF",
    "NTP_D_DIR",
    "NTP_D_FILE",
    "NTPD",
    "PATHS",
    "RTC_CLASS",
    "TIME_CONFIG",
]

TIME_CONFIG = "/etc/hammunition/time.yaml"
"""The mode. Machine-wide like the time itself; root-owned 0644, written only by the helper."""

NTP_CONF = "/etc/ntpsec/ntp.conf"
"""ntpsec's own configuration, a dpkg conffile. Edited only on marked lines."""

NTPD = "/usr/sbin/ntpd"
"""ntpsec's daemon. The conffile alone is no evidence: `apt remove ntpsec` leaves
/etc/ntpsec/ntp.conf behind (a dpkg conffile) and takes this binary away."""

NTP_D_DIR = "/etc/ntpsec/ntp.d"
"""ntpd reads ``*.conf`` here after ntp.conf (``ntpd(8)``). The package does not ship it."""

NTP_D_FILE = "/etc/ntpsec/ntp.d/hammunition-gps.conf"
"""Hammunition's refclock and selection lines, rewritten whole per mode."""

DROPIN = "/etc/systemd/system/ntpsec.service.d/hammunition-gps.conf"
"""Grants ntpd CAP_IPC_OWNER so it can attach gpsd's root-only SHM segment."""

APPARMOR_LOCAL = "/etc/apparmor.d/local/usr.sbin.ntpd"
"""The file Debian reserves for local additions to ntpd's profile. Created empty by
the package's maintainer script and not owned by dpkg, so it is edited, never removed."""

APPARMOR_PROFILE = "/etc/apparmor.d/usr.sbin.ntpd"
"""ntpd's AppArmor profile; its absence means there is nothing to reload."""

NTPSEC_DEFAULT = "/etc/default/ntpsec"
"""Where IGNORE_DHCP is set."""

DHCP_CONF = "/run/ntpsec/ntp.conf.dhcp"
"""When present and IGNORE_DHCP is not yes, ntpsec's wrapper starts ntpd on this
instead of NTP_CONF."""

RTC_CLASS = "/sys/class/rtc"
"""Empty on a machine with no hardware clock (a Raspberry Pi without an RTC module)."""

PATHS: dict[str, str] = {
    "TIME_CONFIG": TIME_CONFIG,
    "NTP_CONF": NTP_CONF,
    "NTPD": NTPD,
    "NTP_D_DIR": NTP_D_DIR,
    "NTP_D_FILE": NTP_D_FILE,
    "DROPIN": DROPIN,
    "APPARMOR_LOCAL": APPARMOR_LOCAL,
    "APPARMOR_PROFILE": APPARMOR_PROFILE,
    "NTPSEC_DEFAULT": NTPSEC_DEFAULT,
    "DHCP_CONF": DHCP_CONF,
    "RTC_CLASS": RTC_CLASS,
}
"""Each attribute and its real default, for the fixtures that repoint them."""
