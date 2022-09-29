# Copyright (c) Acconeer AB, 2022
# All rights reserved
from typing import Any

import numpy as np

from ._processor import ProcessorResult


class Easing:
    def __init__(self, tc: float = 0.05, y0: float = 0.0) -> None:
        self.tc = tc
        self.y = y0

    def update(self, x: float, dt: float) -> float:
        d = x - self.y
        self.y += d * (1.0 - np.exp(-(dt / self.tc)))
        return self.y


class BlinkstickUpdater:
    def __init__(self) -> None:
        self.e_close = Easing()
        self.e_far = Easing()
        self.last_t = -1

    def update(self, data: ProcessorResult, data_index: int, t: int, stick: Any) -> None:
        dt = t - self.last_t
        self.last_t = t

        stick.set_max_rgb_value(150)

        v_close = self.e_close.update(float(bool(data.detection_close)), dt)
        v_far = self.e_far.update(float(bool(data.detection_far)), dt)

        stick.set_color(blue=255 * v_far, index=0)
        stick.set_color(blue=255 * v_far, index=1)
        stick.set_color(red=255 * v_close, index=2)
        stick.set_color(red=255 * v_close, index=3)
