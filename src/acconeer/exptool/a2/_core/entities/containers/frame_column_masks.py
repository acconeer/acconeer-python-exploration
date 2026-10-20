# Copyright (c) Acconeer AB, 2023-2026
# All rights reserved

from __future__ import annotations

import itertools
import typing as t

import attrs

from acconeer.exptool.a2._core.entities.configs import SensorConfig, SubsweepConfig


@attrs.frozen
class _PhonyContainer:
    contains_result: bool
    repr_string: str

    def __contains__(self, _: t.Any) -> bool:
        return self.contains_result

    def __repr__(self) -> str:
        return self.repr_string


ALL = _PhonyContainer(True, "ALL")
NONE = _PhonyContainer(False, "NONE")


def channel_column_mask(config: SubsweepConfig, channel_indexes: t.Container[int]) -> list[bool]:
    """Return a mask that keeps the data points from ``channel_indexes`` of a subframe

    Examples:

    >>> config = SubsweepConfig(num_points=2, tx_antenna_mask=0b001, rx_antenna_mask=0b0001)
    >>> channel_column_mask(config, channel_indexes=[0])
    [True, True]

    >>> channel_column_mask(config, channel_indexes=ALL)
    [True, True]

    >>> config = SubsweepConfig(num_points=2, tx_antenna_mask=0b001, rx_antenna_mask=0b0011)
    >>> channel_column_mask(config, channel_indexes=[0])
    [True, False, True, False]
    >>> channel_column_mask(config, channel_indexes=[1])
    [False, True, False, True]
    >>> channel_column_mask(config, channel_indexes=[2])  # does not exist
    [False, False, False, False]
    """
    return [
        channel_position in channel_indexes
        for _ in range(config.num_points)
        for channel_position in range(config.num_channels)
    ]


def subframe_column_mask(
    config: SensorConfig,
    subsweep_indexes: t.Container[int],
    channel_indexes: t.Container[int] = ALL,
) -> list[bool]:
    """Return a mask that keeps the specified subsweeps

    Examples:

    >>> config = SensorConfig.identical_subsweeps(num_subsweeps=3, num_points=2, tx_antenna_mask=0b001, rx_antenna_mask=0b0001)
    >>> subframe_column_mask(config, subsweep_indexes=[1])
    [False, False, True, True, False, False]

    It can also be combined with ``channel_indexes`` to only get data of certain
    subframes and channels:

    >>> config = SensorConfig.identical_subsweeps(num_subsweeps=3,
    ...                                           num_points=1,
    ...                                           tx_antenna_mask=0b111,
    ...                                           rx_antenna_mask=0b0001)
    ...
    >>> subframe_column_mask(config, subsweep_indexes=[1], channel_indexes=[0, 2])
    [False, False, False, True, False, True, False, False, False]

    Trying to get a mask for things that doesn't exist
    (subsweep with index 3 or channel with index 3 below) does nothing.

    >>> subframe_column_mask(config, subsweep_indexes=[1, 3], channel_indexes=[0, 2])
    [False, False, False, True, False, True, False, False, False]

    >>> subframe_column_mask(config, subsweep_indexes=[1], channel_indexes=[0, 2, 3])
    [False, False, False, True, False, True, False, False, False]
    """
    return list(
        itertools.chain(
            *[
                channel_column_mask(
                    subsweep_config,
                    channel_indexes=channel_indexes
                    if subsweep_index in subsweep_indexes
                    else NONE,
                )
                for subsweep_index, subsweep_config in enumerate(config.subsweeps)
            ]
        )
    )
