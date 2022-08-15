# Copyright (c) Acconeer AB, 2022
# All rights reserved

from __future__ import annotations

from typing import Optional, Tuple

import numpy as np


class RateCalculator:
    def __init__(self) -> None:
        self._reset()

    def _reset(self):
        self.last_time = None
        self.fifo = np.full(200, np.nan)

    def update(self, time: Optional[float]) -> Tuple[float, float]:
        if time is None:
            self._reset()
            return np.nan, np.nan

        last_time = self.last_time
        self.last_time = time

        if last_time is None:
            return np.nan, np.nan

        delta_time = time - last_time

        self.fifo = np.roll(self.fifo, -1)
        self.fifo[-1] = delta_time

        rate = 1.0 / np.nanmean(self.fifo)
        jitter = np.nanstd(self.fifo)

        return float(rate), float(jitter)
