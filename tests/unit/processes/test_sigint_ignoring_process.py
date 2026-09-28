# Copyright (c) Acconeer AB, 2026
# All rights reserved

from __future__ import annotations

import multiprocessing as mp
import subprocess
import sys
from pathlib import Path

import pytest


_INTERRUPT_SCRIPT = """
import multiprocessing as mp, os, signal, sys, time

from acconeer.exptool._processes.sigint_ignoring_process import SigintIgnoringProcess


class SlowToIgnoreSigint(SigintIgnoringProcess):
    # A child that takes a while to ignore SIGINT, which start() must wait out.
    def run(self) -> None:
        time.sleep(0.5)
        super().run()


if __name__ == "__main__":
    mp.set_start_method(sys.argv[1])
    p = SlowToIgnoreSigint(target=time.sleep, args=(0.5,))
    p.start()
    # Not at once, as a child still forking can drop a SIGINT and hide the bug.
    time.sleep(0.1)
    os.kill(p.pid, signal.SIGINT)
    p.join()
    if p.exitcode != 0:
        sys.exit(f"SIGINT right after start() ended the child ({p.exitcode})")
"""

_EXIT_SCRIPT = """
import multiprocessing as mp, os, sys, time

from acconeer.exptool._processes.sigint_ignoring_process import (
    SigintIgnoringProcess,
    SigintIgnoringProcessStartError,
)


class ExitsBeforeIgnoringSigint(SigintIgnoringProcess):
    def run(self) -> None:
        os._exit(3)


if __name__ == "__main__":
    mp.set_start_method(sys.argv[1])
    start = mp.Process.start

    def start_and_let_the_child_exit(self) -> None:
        start(self)
        time.sleep(0.5)

    # With no target, the child exits as soon as it has ignored SIGINT, here before
    # start() checks on it.
    mp.Process.start = start_and_let_the_child_exit
    SigintIgnoringProcess().start()
    try:
        ExitsBeforeIgnoringSigint().start()
    except SigintIgnoringProcessStartError:
        pass
    else:
        sys.exit("start() returned for a child that exited before ignoring SIGINT")
"""

_DIED_AT_START_SCRIPT = """
import multiprocessing as mp, os, sys

from acconeer.exptool._processes import mpl_process, pg_process
from acconeer.exptool._processes.sigint_ignoring_process import SigintIgnoringProcess


class ExitsBeforeIgnoringSigint(SigintIgnoringProcess):
    def run(self) -> None:
        os._exit(3)


if __name__ == "__main__":
    mp.set_start_method(sys.argv[1])
    for module, plotting_process, died in [
        (pg_process, pg_process.PGProcess, pg_process.PGProccessDiedException),
        (mpl_process, mpl_process.PlotProcess, mpl_process.PlotProccessDiedException),
    ]:
        module.SigintIgnoringProcess = ExitsBeforeIgnoringSigint
        p = plotting_process(None)
        p.start()
        try:
            p.put_data(None)
        except died:
            pass
        else:
            sys.exit(f"put_data() took data for a dead {plotting_process.__name__}")
"""


def run_script(script: str, start_method: str, tmp_path: Path) -> None:
    # A fresh interpreter, as the start method can be set only once per process.
    path = tmp_path / "script.py"
    path.write_text(script)
    subprocess.run([sys.executable, str(path), start_method], check=True, timeout=120)


@pytest.mark.parametrize("start_method", mp.get_all_start_methods())
def test_sigint_right_after_start_is_ignored(start_method: str, tmp_path: Path) -> None:
    run_script(_INTERRUPT_SCRIPT, start_method, tmp_path)


@pytest.mark.parametrize("start_method", mp.get_all_start_methods())
def test_start_fails_only_for_a_child_that_exits_before_ignoring_sigint(
    start_method: str, tmp_path: Path
) -> None:
    run_script(_EXIT_SCRIPT, start_method, tmp_path)


@pytest.mark.parametrize("start_method", mp.get_all_start_methods())
def test_plotting_processes_report_a_child_that_died_at_start_on_put_data(
    start_method: str, tmp_path: Path
) -> None:
    run_script(_DIED_AT_START_SCRIPT, start_method, tmp_path)
