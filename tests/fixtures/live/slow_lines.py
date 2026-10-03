# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later
"""A fake long command: one numbered line every 0.2 s for 2 s, some on stderr."""

import sys
import time

for i in range(10):
    stream = sys.stderr if i % 3 == 2 else sys.stdout
    print(f"step {i} \x1b[32mgreen\x1b[0m", file=stream, flush=True)
    time.sleep(0.2)
print("finished", flush=True)
