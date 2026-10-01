# Copyright (c) Acconeer AB, 2026
# All rights reserved

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest


_SCRIPT = """
import sys, time

import numpy as np

from acconeer.exptool.mpl_process import FigureUpdater, PlotProcess
from acconeer.exptool import PGProcess


class StuckUpdater(FigureUpdater):
    # Never reads its queue, like a plot that has fallen far behind.
    def setup(self, fig_or_win) -> None:
        time.sleep(60)


if __name__ == "__main__":
    plotting_process = {"PGProcess": PGProcess, "PlotProcess": PlotProcess}[sys.argv[1]]
    p = plotting_process(StuckUpdater())
    p.start()
    for _ in range(50):
        p.put_data(np.zeros(20_000))
"""


@pytest.mark.parametrize("plotting_process", ["PGProcess", "PlotProcess"])
def test_exit_does_not_wait_for_a_lagging_plot(plotting_process: str, tmp_path: Path) -> None:
    path = tmp_path / "script.py"
    path.write_text(_SCRIPT)
    env = {**os.environ, "QT_QPA_PLATFORM": "offscreen", "MPLBACKEND": "Agg"}
    subprocess.run([sys.executable, str(path), plotting_process], check=True, env=env, timeout=30)
