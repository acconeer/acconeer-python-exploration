# Copyright (c) Acconeer AB, 2026
# All rights reserved

# This module exists only for backwards compatibility reasons.

from ._processes.mpl_process import (
    ExampleFigureUpdater,
    FigureUpdater,
    PlotProccessDiedException,
    PlotProcess,
)


__all__ = ["ExampleFigureUpdater", "FigureUpdater", "PlotProccessDiedException", "PlotProcess"]
