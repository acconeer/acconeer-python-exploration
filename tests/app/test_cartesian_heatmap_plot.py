# Copyright (c) Acconeer AB, 2026
# All rights reserved
from __future__ import annotations

import pytest

from PySide6.QtGui import QImage, QPainter

from acconeer.exptool.a2.algo.heatmap.cartesian_plot import CartesianHeatmapPlotWithGrid


pytestmark = pytest.mark.usefixtures("qapplication")


def test_painting_before_update_grid() -> None:
    """Qt can paint the plot before the backend's first state reaches update_grid()."""
    plot = CartesianHeatmapPlotWithGrid()
    image = QImage(100, 100, QImage.Format.Format_ARGB32)

    with QPainter(image) as painter:
        plot.paint(painter)
