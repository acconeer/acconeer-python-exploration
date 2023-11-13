# Copyright (c) Acconeer AB, 2022-2023
# All rights reserved

from __future__ import annotations

import typing as t

import attrs
import numpy as np
import typing_extensions as te


class _ResultTimeAspects(te.Protocol):
    @property
    def tick(self) -> int:
        ...

    @property
    def tick_time(self) -> float:
        ...

    @property
    def frame_delayed(self) -> bool:
        ...


@attrs.frozen(kw_only=True)
class _RateStats:
    rate: float = attrs.field(default=np.nan)
    rate_warning: bool = attrs.field(default=False)
    jitter: float = attrs.field(default=np.nan)
    jitter_warning: bool = attrs.field(default=False)


class _RateCalculator:
    _JITTER_WARNING_LIMIT = 1.0e-3  # Based on testing

    stats: _RateStats

    def __init__(
        self,
        update_rate: t.Optional[float],
        tick_period: int,
    ) -> None:
        self.tick_period = tick_period

        self.update_rate = update_rate

        self.last_result: t.Optional[_ResultTimeAspects] = None
        self.time_fifo = np.full(200, np.nan)
        self.tick_fifo = np.full(200, np.nan)
        self.stats = _RateStats()

    def update(self, result: _ResultTimeAspects) -> None:
        last_result = self.last_result
        self.last_result = result

        if last_result is None:
            return

        delta_time = result.tick_time - last_result.tick_time
        self.time_fifo = np.roll(self.time_fifo, -1)
        self.time_fifo[-1] = delta_time

        delta_tick = result.tick - last_result.tick
        self.tick_fifo = np.roll(self.tick_fifo, -1)
        self.tick_fifo[-1] = delta_tick

        mean_diff = np.nanmean(self.time_fifo)
        rate = 1.0 / mean_diff if mean_diff > 0 else 0
        jitter = np.nanstd(self.time_fifo)

        rate_warning = result.frame_delayed

        if self.update_rate is not None:
            limit = self.tick_period * 1.01 + 10
            rate_warning |= np.nanmean(self.tick_fifo) > limit

        jitter_warning = jitter > self._JITTER_WARNING_LIMIT

        self.stats = _RateStats(
            rate=float(rate),
            rate_warning=bool(rate_warning),
            jitter=float(jitter),
            jitter_warning=bool(jitter_warning),
        )
