# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later

"""The GUI smoke lane's verdicts, against stderr recorded from a real failure.

yaac with only default-jre-headless: the launcher raised
java.awt.HeadlessException on the splash screen and then exited **0**
(Debian 13 under Xvfb, 2026-09-05, issue #31). The lane's three verdicts
filed that as `exited-clean`, the same bucket as a program that printed
`--help` and left, and the four-line stderr tail it kept was stack frames
-- the line that named the fault was thirty lines up. A verdict that reads
the exit status and not the effect is the D-031 mistake again.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent

# Verbatim shape of the recorded stderr, cut to the lines that matter: the
# fault is a `Caused by:` line buried between two stack traces, and the last
# four lines are frames from the event thread.
YAAC_HEADLESS_STDERR = """\
Sat Sep 05 22:00:45 EDT 2026: loading core GUI class....
Sat Sep 05 22:00:45 EDT 2026: YAAC raising splash screen....
java.lang.reflect.InvocationTargetException
\tat java.base/jdk.internal.reflect.DirectMethodHandleAccessor.invoke(DirectMethodHandleAccessor.java:118)
\tat org.ka2ddo.yaac.YAAC.main(YAAC.java:791)
Caused by: java.awt.HeadlessException: \n\
\tat java.desktop/java.awt.GraphicsEnvironment.checkHeadless(GraphicsEnvironment.java:164)
\tat java.desktop/java.awt.Window.<init>(Window.java:553)
\tat java.desktop/java.awt.Frame.<init>(Frame.java:428)
\tat java.desktop/java.awt.EventDispatchThread.pumpEvents(EventDispatchThread.java:109)
\tat java.desktop/java.awt.EventDispatchThread.pumpEvents(EventDispatchThread.java:101)
\tat java.desktop/java.awt.EventDispatchThread.run(EventDispatchThread.java:90)
"""


@pytest.fixture(scope="module")
def smoke() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "vm_gui_smoke_under_test", REPO_ROOT / "scripts" / "vm_gui_smoke.py"
    )
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["vm_gui_smoke_under_test"] = mod
    spec.loader.exec_module(mod)
    return mod


def test_exit_zero_with_an_exception_on_stderr_is_suspect_not_clean(smoke: ModuleType) -> None:
    verdict, tail = smoke.classify(0, YAAC_HEADLESS_STDERR)
    assert verdict == "suspect"
    assert "java.awt.HeadlessException" in tail


def test_the_tail_leads_with_the_line_that_names_the_fault(smoke: ModuleType) -> None:
    _, tail = smoke.classify(0, YAAC_HEADLESS_STDERR)
    assert tail.splitlines()[0].startswith("Caused by: java.awt.HeadlessException")


def test_exit_zero_with_quiet_stderr_stays_exited_clean(smoke: ModuleType) -> None:
    verdict, tail = smoke.classify(0, "gqrx: using PulseAudio backend\n")
    assert verdict == "exited-clean"
    assert tail == "gqrx: using PulseAudio backend"


def test_the_timeout_is_alive_whatever_stderr_says(smoke: ModuleType) -> None:
    # A live GUI that logged a caught exception on the way up is still a live
    # GUI; the lane's claim is "it came up", and it did.
    verdict, _ = smoke.classify(124, YAAC_HEADLESS_STDERR)
    assert verdict == "alive"


def test_non_zero_exit_is_failed_and_the_tail_names_the_fault(smoke: ModuleType) -> None:
    stderr = (
        "Traceback (most recent call last):\n"
        '  File "/usr/local/share/hammunition/js8spotter/js8spotter.py", line 3, in <module>\n'
        "    import tkinter\n"
        "ModuleNotFoundError: No module named 'tkinter'\n"
    )
    verdict, tail = smoke.classify(1, stderr)
    assert verdict == "failed"
    assert tail.splitlines()[0] == "Traceback (most recent call last):"
    assert "ModuleNotFoundError" in tail


@pytest.mark.parametrize(
    "line",
    [
        "error while loading shared libraries: libfftw3f.so.3: cannot open shared object file",
        'qt.qpa.plugin: Could not load the Qt platform plugin "xcb" in "" even though it was found.',
        "Segmentation fault (core dumped)",
        "Error: cannot open display: :99",
        # The JVM's own uncaught-exception line. yaac's *second* headless run
        # printed only this: with cached preferences the splash path that
        # raised HeadlessException is skipped, and the lane's first live
        # falsification on Debian 13 (2026-09-05) filed it exited-clean.
        'Exception in thread "AWT-EventQueue-0" java.lang.NullPointerException: '
        'Cannot invoke "org.ka2ddo.yaac.gui.FirstWindowInitIfc.initMenuBar()" '
        'because "this.initialWindow" is null',
    ],
)
def test_the_usual_launch_faults_are_recognised(smoke: ModuleType, line: str) -> None:
    verdict, tail = smoke.classify(0, f"starting up\n{line}\nbye\n")
    assert verdict == "suspect"
    assert tail.splitlines()[0] == line


def test_a_word_that_merely_contains_error_is_not_a_fault(smoke: ModuleType) -> None:
    # "errors=replace", "ErrorDialog.class", a log level of INFO about errors:
    # none of these is a fault line, and a lane that cried wolf on every
    # mention of the word would be ignored inside a week.
    verdict, _ = smoke.classify(0, "loaded ErrorDialog.class\nINFO no errors\n")
    assert verdict == "exited-clean"
