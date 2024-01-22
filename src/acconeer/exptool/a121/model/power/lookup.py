# Copyright (c) Acconeer AB, 2023-2024
# All rights reserved

from __future__ import annotations

import collections
import typing as t
from enum import Enum, auto

import attrs
import typing_extensions as te

from acconeer.exptool import a121


_ms = _mA = 1e-3
_us = _uA = 1e-6


@attrs.frozen
class Sensor:
    """
    Representation of a sensor.

    Consists of multiple table for different currents, overhead- and transition times.
    """

    class IdleState(Enum):
        OFF = auto()
        HIBERNATE = auto()

    class FixedOverhead(Enum):
        SUBSWEEP = auto()
        SWEEP = auto()
        FRAME = auto()

    LowerIdleState = te.Literal[IdleState.OFF, IdleState.HIBERNATE]

    inter_sweep_currents: t.Mapping[a121.IdleState, float]
    inter_sweep_currents_high_speed_mode: t.Mapping[a121.IdleState, float]
    inter_frame_currents: t.Mapping[t.Union[a121.IdleState, IdleState], float]
    measure_currents: t.Mapping[a121.Profile, float]

    time_for_measure_transition: t.Mapping[a121.IdleState, float]
    normal_overheads: t.Mapping[FixedOverhead, float]
    high_speed_mode_overheads: t.Mapping[FixedOverhead, float]
    pre_measure_setup_duration: float
    read_duration: float

    sample_durations: t.Mapping[a121.Profile, t.Mapping[a121.PRF, float]]
    point_overheads: t.Mapping[a121.Profile, t.Mapping[a121.PRF, float]]

    @classmethod
    def none(cls) -> te.Self:
        return attrs.evolve(
            cls.default(),
            inter_sweep_currents=collections.defaultdict(lambda: 0.0),
            inter_sweep_currents_high_speed_mode=collections.defaultdict(lambda: 0.0),
            inter_frame_currents=collections.defaultdict(lambda: 0.0),
            measure_currents=collections.defaultdict(lambda: 0.0),
        )

    @classmethod
    def default(cls) -> te.Self:
        idle_currents = {
            a121.IdleState.READY: 62.5 * _mA,
            a121.IdleState.SLEEP: 1.6 * _mA,
            a121.IdleState.DEEP_SLEEP: 1.1 * _mA,
        }

        return cls(
            inter_sweep_currents_high_speed_mode={
                a121.IdleState.READY: 68.5 * _mA,
                a121.IdleState.SLEEP: 1.6 * _mA,
                a121.IdleState.DEEP_SLEEP: 1.1 * _mA,
            },
            inter_sweep_currents=idle_currents,
            inter_frame_currents={
                **idle_currents,  # type: ignore[dict-item]
                cls.IdleState.OFF: 3 * _uA,
                cls.IdleState.HIBERNATE: 15 * _uA,
            },
            measure_currents={
                a121.Profile.PROFILE_1: 73.0 * _mA,
                a121.Profile.PROFILE_2: 72.5 * _mA,
                a121.Profile.PROFILE_3: 74.0 * _mA,
                a121.Profile.PROFILE_4: 75.0 * _mA,
                a121.Profile.PROFILE_5: 76.5 * _mA,
            },
            time_for_measure_transition={
                a121.IdleState.READY: 0,
                a121.IdleState.SLEEP: 55 * _us,
                a121.IdleState.DEEP_SLEEP: 670 * _us,
            },
            normal_overheads={
                cls.FixedOverhead.SUBSWEEP: 22 * _us,
                cls.FixedOverhead.SWEEP: 10 * _us,
                cls.FixedOverhead.FRAME: 4 * _us,
            },
            high_speed_mode_overheads={
                cls.FixedOverhead.SUBSWEEP: 0,
                cls.FixedOverhead.SWEEP: 0,
                cls.FixedOverhead.FRAME: 36 * _us,
            },
            pre_measure_setup_duration=600 * _us,
            read_duration=0.2 * _ms,
            sample_durations={
                a121.Profile.PROFILE_1: {
                    a121.PRF.PRF_19_5_MHz: 1.487 * _us,
                    a121.PRF.PRF_15_6_MHz: 1.795 * _us,
                    a121.PRF.PRF_13_0_MHz: 2.103 * _us,
                    a121.PRF.PRF_8_7_MHz: 3.026 * _us,
                    a121.PRF.PRF_6_5_MHz: 3.949 * _us,
                    a121.PRF.PRF_5_2_MHz: 4.872 * _us,
                },
                a121.Profile.PROFILE_2: {
                    a121.PRF.PRF_15_6_MHz: 1.344 * _us,
                    a121.PRF.PRF_13_0_MHz: 1.600 * _us,
                    a121.PRF.PRF_8_7_MHz: 2.369 * _us,
                    a121.PRF.PRF_6_5_MHz: 3.138 * _us,
                    a121.PRF.PRF_5_2_MHz: 3.908 * _us,
                },
                a121.Profile.PROFILE_3: {
                    a121.PRF.PRF_15_6_MHz: 1.026 * _us,
                    a121.PRF.PRF_13_0_MHz: 1.231 * _us,
                    a121.PRF.PRF_8_7_MHz: 1.846 * _us,
                    a121.PRF.PRF_6_5_MHz: 2.462 * _us,
                    a121.PRF.PRF_5_2_MHz: 3.077 * _us,
                },
                a121.Profile.PROFILE_4: {
                    a121.PRF.PRF_15_6_MHz: 1.026 * _us,
                    a121.PRF.PRF_13_0_MHz: 1.231 * _us,
                    a121.PRF.PRF_8_7_MHz: 1.846 * _us,
                    a121.PRF.PRF_6_5_MHz: 2.462 * _us,
                    a121.PRF.PRF_5_2_MHz: 3.077 * _us,
                },
                a121.Profile.PROFILE_5: {
                    a121.PRF.PRF_15_6_MHz: 1.026 * _us,
                    a121.PRF.PRF_13_0_MHz: 1.231 * _us,
                    a121.PRF.PRF_8_7_MHz: 1.846 * _us,
                    a121.PRF.PRF_6_5_MHz: 2.462 * _us,
                    a121.PRF.PRF_5_2_MHz: 3.077 * _us,
                },
            },
            point_overheads={
                a121.Profile.PROFILE_1: {
                    a121.PRF.PRF_19_5_MHz: 1.744 * _us,
                    a121.PRF.PRF_15_6_MHz: 2.102 * _us,
                    a121.PRF.PRF_13_0_MHz: 2.462 * _us,
                    a121.PRF.PRF_8_7_MHz: 3.539 * _us,
                    a121.PRF.PRF_6_5_MHz: 4.615 * _us,
                    a121.PRF.PRF_5_2_MHz: 5.692 * _us,
                },
                a121.Profile.PROFILE_2: {
                    a121.PRF.PRF_15_6_MHz: 1.612 * _us,
                    a121.PRF.PRF_13_0_MHz: 1.920 * _us,
                    a121.PRF.PRF_8_7_MHz: 2.844 * _us,
                    a121.PRF.PRF_6_5_MHz: 3.766 * _us,
                    a121.PRF.PRF_5_2_MHz: 4.689 * _us,
                },
                a121.Profile.PROFILE_3: {
                    a121.PRF.PRF_15_6_MHz: 1.282 * _us,
                    a121.PRF.PRF_13_0_MHz: 1.539 * _us,
                    a121.PRF.PRF_8_7_MHz: 2.308 * _us,
                    a121.PRF.PRF_6_5_MHz: 3.077 * _us,
                    a121.PRF.PRF_5_2_MHz: 4.689 * _us,
                },
                a121.Profile.PROFILE_4: {
                    a121.PRF.PRF_15_6_MHz: 1.282 * _us,
                    a121.PRF.PRF_13_0_MHz: 1.539 * _us,
                    a121.PRF.PRF_8_7_MHz: 2.308 * _us,
                    a121.PRF.PRF_6_5_MHz: 3.077 * _us,
                    a121.PRF.PRF_5_2_MHz: 4.689 * _us,
                },
                a121.Profile.PROFILE_5: {
                    a121.PRF.PRF_15_6_MHz: 1.282 * _us,
                    a121.PRF.PRF_13_0_MHz: 1.539 * _us,
                    a121.PRF.PRF_8_7_MHz: 2.308 * _us,
                    a121.PRF.PRF_6_5_MHz: 3.077 * _us,
                    a121.PRF.PRF_5_2_MHz: 4.689 * _us,
                },
            },
        )


@attrs.frozen
class Module:
    """
    Representation of a module.

    Consists of a current table for the different module power states.
    """

    class PowerState(Enum):
        PROCESSING = auto()
        AWAKE = auto()
        ASLEEP = auto()
        IO = auto()

    currents: t.Mapping[t.Union[PowerState, Sensor.IdleState], float]

    @classmethod
    def xm125(cls) -> te.Self:
        return cls(
            currents={
                cls.PowerState.PROCESSING: 13 * _mA,
                cls.PowerState.AWAKE: 4.8 * _mA,
                cls.PowerState.ASLEEP: 0.1 * _uA,
                cls.PowerState.IO: 13 * _mA,
            }
        )

    @classmethod
    def none(cls) -> te.Self:
        return cls(currents=collections.defaultdict(lambda: 0.0))
