# Copyright (c) Acconeer AB, 2022
# All rights reserved

from __future__ import annotations

import typing as t

import attrs
import numpy as np

from acconeer.exptool import a121


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
        session_config: a121.SessionConfig,
        metadata: t.Union[a121.Metadata, list[dict[int, a121.Metadata]]],
    ) -> None:
        if isinstance(metadata, list):
            metadata = next(a121.iterate_extended_structure_values(metadata))

        self.metadata = metadata

        self.session_config = session_config  # TODO: For performance calculator based warning
        self.sensor_config = next(a121.iterate_extended_structure_values(session_config.groups))

        self.last_result: t.Optional[a121.Result] = None
        self.time_fifo = np.full(200, np.nan)
        self.tick_fifo = np.full(200, np.nan)
        self.stats = _RateStats()

    def update(
        self,
        result: t.Union[a121.Result, list[dict[int, a121.Result]]],
    ) -> None:
        if isinstance(result, list):
            result = next(a121.iterate_extended_structure_values(result))

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

        rate = 1.0 / np.nanmean(self.time_fifo)
        jitter = np.nanstd(self.time_fifo)

        rate_warning = result.frame_delayed

        if self.session_config.update_rate is not None:
            limit = self.metadata.tick_period * 1.01 + 10
            rate_warning |= np.nanmean(self.tick_fifo) > limit

        jitter_warning = jitter > self._JITTER_WARNING_LIMIT

        self.stats = _RateStats(
            rate=float(rate),
            rate_warning=bool(rate_warning),
            jitter=float(jitter),
            jitter_warning=bool(jitter_warning),
        )
