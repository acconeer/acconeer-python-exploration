# Copyright (c) Acconeer AB, 2022-2023
# All rights reserved

from __future__ import annotations

import math
import statistics
import typing as t
from collections import deque

import attrs
import typing_extensions as te


@attrs.frozen
class _RateStats:
    rate: float
    rate_warning: bool
    jitter: float
    jitter_warning: bool

    @classmethod
    def invalid(cls) -> te.Self:
        return cls(rate=math.nan, rate_warning=False, jitter=math.nan, jitter_warning=False)


@attrs.mutable
class _RateCalculator:
    """Stateful class that monitors result rate and jitter.

    Since the ``_RateCalculator`` compares time differances between results, the first call
    to ``update`` will "prime" it and will not produce any meaningful statistics.

    >>> rc = _RateCalculator(ticks_per_second=1000, tick_period=100)
    >>> rc.update(tick=0, frame_delayed=False)
    _RateStats(rate=nan, rate_warning=False, jitter=nan, jitter_warning=False)

    Once the ``_RateCalculator`` is passed its second result, statistics are meaningful:

    >>> rc.update(tick=100, frame_delayed=False)
    _RateStats(rate=10.0, rate_warning=False, jitter=0.0, jitter_warning=False)

    Once the passed result aren't exactly equidistant in time, jitter will be non-zero:

    >>> rc.update(tick=201, frame_delayed=False)
    _RateStats(rate=9.95..., rate_warning=False, jitter=0.0005..., jitter_warning=False)

    If the result has the indication ``frame_delayed``, ``rate_warning`` will always be true.

    >>> rc.update(tick=300, frame_delayed=True)
    _RateStats(rate=10.0, rate_warning=True, jitter=0.0008..., jitter_warning=False)

    If the measured rate or its jitter becomes too large, both warning flag will be
    set to True:

    >>> rc.update(tick=600, frame_delayed=False)
    _RateStats(rate=6.66..., rate_warning=True, jitter=0.08..., jitter_warning=True)
    """

    _JITTER_WARNING_LIMIT: t.ClassVar[float] = 1.0e-3  # Based on testing

    ticks_per_second: int
    tick_period: int

    ticks: deque[int] = attrs.field(factory=lambda: deque([], maxlen=200), init=False)

    @property
    def tick_period_upper_bound(self) -> float:
        if self.tick_period == 0:
            return math.inf
        else:
            return self.tick_period * 1.01 + 10

    @property
    def tick_diffs(self) -> list[int]:
        return [rhs - lhs for lhs, rhs in zip(self.ticks, list(self.ticks)[1:])]

    def update(self, tick: int, frame_delayed: bool) -> _RateStats:
        self.ticks.append(tick)

        if len(self.ticks) < 2:
            return _RateStats.invalid()

        measured_tick_period = statistics.mean(self.tick_diffs)
        measured_rate = 1.0 / (measured_tick_period / self.ticks_per_second)
        rate_warning = frame_delayed or measured_tick_period > self.tick_period_upper_bound

        if len(self.tick_diffs) < 2:
            return _RateStats(measured_rate, rate_warning, jitter=0.0, jitter_warning=False)
        else:
            jitter_s = statistics.pstdev(self.tick_diffs) / self.ticks_per_second
            jitter_warning = jitter_s > self._JITTER_WARNING_LIMIT
            return _RateStats(measured_rate, rate_warning, jitter_s, jitter_warning)
