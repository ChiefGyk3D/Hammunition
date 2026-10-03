# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later
"""A fake sudo: prompts on the terminal (not stdout or stderr), waits 3 s for
"the password", then runs the command."""

import os
import sys
import time

with open(os.environ["FAKE_SUDO_TTY"], "w") as tty:
    tty.write("[sudo] password for operator: ")
    tty.flush()
    time.sleep(3)
os.execvp(sys.argv[1], sys.argv[1:])
