# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""GPS time: the clock follows the GPS receiver when the network is gone.  D-058.

`mode` is the operator's preference and the ntp.d file it becomes; `ntpconf`
the marked edits to ntpsec's own conffile; `state` what the clock follows,
read without privilege; `apply` the root half, run only inside
``hammunition-devctl``; `grants` what ``hardware apply`` installs so ntpd can
read gpsd's time at all.
"""
