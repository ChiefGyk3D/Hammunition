# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later
"""The console's tests run under the engine's conftest (pinned HOME and XDG, the
network and package-manager guards); this file adds only what they need on top."""

import urwid

urwid.set_encoding("utf-8")
