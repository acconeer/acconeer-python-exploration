# Copyright (c) Acconeer AB, 2023-2026
# All rights reserved

from __future__ import annotations

import typing as t

import attrs
import attrs.validators as av
import numpy as np
import numpy.typing as npt
from attributes_doc import attributes_doc

import acconeer.exptool.type_migration as tm
from acconeer.exptool._core.class_creation.attrs import (
    attrs_ndarray_isclose,
    attrs_ndarray_validator,
)
from acconeer.exptool._core.class_creation.descriptors import Descriptor, delegate_field
from acconeer.exptool._core.int_16_complex import complex_array_to_int16_complex
from acconeer.exptool.a2._core.entities.configs import SensorConfig

from .frame_column_masks import ALL, subframe_column_mask


_T = t.TypeVar("_T")

_TOO_MANY_RESULTS_ERROR_FORMAT = (
    'GroupResult has too many results to use accessor "{}". '
    + 'Specify a specific result with ".results[x]".'
)


@attributes_doc
@attrs.frozen
class Result:
    """Result

    Represents the RSS ``processing_result``.
    """

    temperature: int = attrs.field(validator=av.instance_of(int), converter=int)
    """
    Temperature in sensor during measurement (in degree Celsius). Notice that this has poor
    absolute accuracy.
    """

    frame: npt.NDArray[np.complex128] = attrs.field(
        eq=attrs_ndarray_isclose,
        validator=attrs_ndarray_validator(ndim=2, element_type=np.complex128),
    )
    """Frame data in a complex float data format"""

    tick: int
    """Server tick when the server got the interrupt from the sensor"""

    data_saturated: list[bool] = attrs.field(
        validator=[
            av.deep_iterable(
                member_validator=av.instance_of(bool),
                iterable_validator=av.instance_of(list),
            ),
            av.min_len(1),
            av.max_len(SensorConfig.MAX_NUM_SUBSWEEPS),
        ],
    )
    """
    Indication of sensor data being saturated, can cause data corruption. Lower the receiver gain
    if this indication is set.
    """

    measured_sweep_rate: float | None
    """
    Sweep rate measured by RSS. This value might differ from the configured sweep rate since the
    configured sweep rate represents the maximum requested sweep rate, whereas the measured sweep
    rate reflects the actual rate achieved during operation, which may be lower if the sensor
    cannot keep up with the requested speed.

    If the configuration includes only a single sweep per frame, the measured sweep rate will
    be ``None``.
    """

    frame_delayed: bool = attrs.field(validator=av.instance_of(bool), converter=bool)
    """
    Indication of a delayed frame.

    A frame is considered delayed when it could not be measured at the specified frame rate.
    This means that only a set frame rate can produce delayed frames.
    If the frame rate is uncapped, the frame cannot be delayed.

    The frame rate might need to be lowered if this indication is set.
    """

    calibration_temperature: int = attrs.field(validator=av.instance_of(int), converter=int)
    """
    The temperature of previously performed calibration
    """

    calibration_needed: bool = attrs.field(validator=av.instance_of(bool), converter=bool)
    """
    Whether the current calibration has become invalid.

    Recalibration is performed by setting up a new session (see :py:meth:`acconeer.exptool.a2.Client.setup_session`).
    """

    def seconds_since_server_start(self, ticks_per_second: int) -> float:
        """Return how many seconds the server has been running before producing this result"""
        return self.seconds_since_tick(ticks_per_second, tick=0)

    def seconds_since_tick(self, ticks_per_second: int, tick: int) -> float:
        """Return how many seconds has elapsed between the specified server tick and this result.

        Note that the specified tick needs to be less than this Result's tick.
        """
        if tick > self.tick:
            msg = f"The tick ({tick}) cannot be greater than this Result's tick ({self.tick})"
            raise ValueError(msg)

        return (self.tick - tick) / ticks_per_second

    @property
    def int16_complex_frame(self) -> npt.NDArray[t.Any]:
        """Frame data in the original data format (complex int16)"""
        return complex_array_to_int16_complex(self.frame)

    def get_subframe(
        self,
        config: SensorConfig,
        subsweep_index: int,
        channel_indexes: t.Container[int] = ALL,
    ) -> npt.NDArray[np.complex128]:
        """Get the list of subframes (data collected by a subsweep) given a SensorConfig

        The channel index is Tx-major

        Examples:

        >>> r = Result(frame=np.array([[0.+0.j, 1.+1.j, 2.+2.j, 3.+3.j],
        ...                            [4.+4.j, 5.+5.j, 6.+6.j, 7.+7.j]]),
        ...            temperature=21, tick=0, data_saturated=[False],
        ...            measured_sweep_rate=7.35, frame_delayed=False,
        ...            calibration_temperature=25, calibration_needed=False)
        ...
        >>> config = SensorConfig.single_subsweep(num_points=4, tx_antenna_mask=0b001, rx_antenna_mask=0b0001)
        >>> r.get_subframe(config, 0)
        array([[0.+0.j, 1.+1.j, 2.+2.j, 3.+3.j],
               [4.+4.j, 5.+5.j, 6.+6.j, 7.+7.j]])

        >>> config = SensorConfig.identical_subsweeps(num_subsweeps=2, num_points=2, tx_antenna_mask=0b001, rx_antenna_mask=0b0001)
        >>> r.get_subframe(config, 0)
        array([[0.+0.j, 1.+1.j],
               [4.+4.j, 5.+5.j]])
        >>> r.get_subframe(config, 1)
        array([[2.+2.j, 3.+3.j],
               [6.+6.j, 7.+7.j]])

        It's also possible to extract only the data of specified channels using ``channel_indexes``:

        >>> config_2_channels = SensorConfig.identical_subsweeps(num_subsweeps=2,
        ...                                                      num_points=1,
        ...                                                      tx_antenna_mask=0b001,
        ...                                                      rx_antenna_mask=0b0011)
        ...
        >>> r.get_subframe(config_2_channels, 0, channel_indexes=[1])
        array([[1.+1.j],
               [5.+5.j]])
        >>> r.get_subframe(config_2_channels, 1, channel_indexes=[1])
        array([[3.+3.j],
               [7.+7.j]])
        """
        return np.compress(
            subframe_column_mask(
                config, subsweep_indexes=[subsweep_index], channel_indexes=channel_indexes
            ),
            self.frame,
            axis=1,
        )


def result_delegate_field(descriptor: Descriptor[_T] | _T, type_: t.Any) -> Descriptor[_T]:
    # type_ is only used to annotate the generated property, so it accepts
    # type expressions that are not classes, such as npt.NDArray[...].
    return delegate_field(
        "result",
        descriptor,
        type_=type_,
        doc=Result,
        error_format=_TOO_MANY_RESULTS_ERROR_FORMAT.format("{descriptor_name}"),
    )


@attrs.frozen
class _Result_v0:
    temperature: int
    frame: npt.NDArray[np.complex128] = attrs.field(
        eq=attrs_ndarray_isclose,
        validator=attrs_ndarray_validator(ndim=2, element_type=np.complex128),
    )
    tick: int
    _tick_period: int


@attrs.frozen
class _Result_v1:
    temperature: int
    frame: npt.NDArray[np.complex128] = attrs.field(
        eq=attrs_ndarray_isclose,
        validator=attrs_ndarray_validator(ndim=2, element_type=np.complex128),
    )
    tick: int
    _tick_period: int

    data_saturated: list[bool] = attrs.field(
        validator=[
            av.deep_iterable(
                member_validator=av.instance_of(bool),
                iterable_validator=av.instance_of(list),
            ),
            av.min_len(1),
            av.max_len(SensorConfig.MAX_NUM_SUBSWEEPS),
        ],
    )
    measured_sweep_rate: float | None


@attrs.frozen
class _Result_v2:
    temperature: int
    frame: npt.NDArray[np.complex128] = attrs.field(
        eq=attrs_ndarray_isclose,
        validator=attrs_ndarray_validator(ndim=2, element_type=np.complex128),
    )
    tick: int
    data_saturated: list[bool] = attrs.field(
        validator=[
            av.deep_iterable(
                member_validator=av.instance_of(bool),
                iterable_validator=av.instance_of(list),
            ),
            av.min_len(1),
            av.max_len(SensorConfig.MAX_NUM_SUBSWEEPS),
        ],
    )
    measured_sweep_rate: float | None


@attrs.frozen
class GroupResult:
    """Group result

    Represent the result of an Exploration Server group (multiple results)
    """

    results: list[Result] = attrs.field(
        validator=[av.min_len(1), av.deep_iterable(av.instance_of(Result))]
    )
    """List of results"""

    frame = result_delegate_field(Result.frame, type_=npt.NDArray[np.complex128])
    tick = result_delegate_field(Result.tick, type_=int)
    temperature = result_delegate_field(Result.temperature, type_=int)
    data_saturated = result_delegate_field(Result.data_saturated, type_=list[bool])
    measured_sweep_rate = result_delegate_field(Result.measured_sweep_rate, type_=float)

    @property
    def result(self) -> Result:
        """Retrieves the sole result

        :raises AttributeError: if there are more than 1 result
        """
        num_results = len(self.results)
        if num_results > 1:
            raise AttributeError(_TOO_MANY_RESULTS_ERROR_FORMAT.format("result"))

        return self.results[0]


@attrs.frozen
class _GroupResult_v0:
    results: list[_Result_v0] = attrs.field(
        validator=[av.min_len(1), av.deep_iterable(av.instance_of(_Result_v0))]
    )


@attrs.frozen
class _GroupResult_v1:
    results: list[_Result_v1] = attrs.field(
        validator=[av.min_len(1), av.deep_iterable(av.instance_of(_Result_v1))]
    )


@attrs.frozen
class _GroupResult_v2:
    results: list[_Result_v2] = attrs.field(
        validator=[av.min_len(1), av.deep_iterable(av.instance_of(_Result_v2))]
    )


result_timeline = (
    tm.start(_Result_v0)
    .nop()
    .epoch(
        _Result_v1,
        lambda old: _Result_v1(
            temperature=old.temperature,
            frame=old.frame,
            tick=old.tick,
            data_saturated=[False] * SensorConfig.MAX_NUM_SUBSWEEPS,
            measured_sweep_rate=None,
            tick_period=old._tick_period,
        ),
        fail=[],
    )
    .epoch(
        _Result_v2,
        lambda old: _Result_v2(
            temperature=old.temperature,
            frame=old.frame,
            tick=old.tick,
            data_saturated=old.data_saturated,
            measured_sweep_rate=old.measured_sweep_rate,
        ),
        fail=[],
    )
    .epoch(
        Result,
        lambda old: Result(
            temperature=old.temperature,
            frame=old.frame,
            tick=old.tick,
            data_saturated=old.data_saturated,
            measured_sweep_rate=old.measured_sweep_rate,
            # Arbitrary values below
            frame_delayed=False,
            calibration_temperature=25,
            calibration_needed=False,
        ),
        fail=[],
    )
)

group_result_timeline = (
    tm.start(_GroupResult_v0)
    .nop()
    .epoch(
        _GroupResult_v1,
        lambda old: _GroupResult_v1(
            results=[
                result_timeline.migrate(result, target_type=_Result_v1) for result in old.results
            ],
        ),
        fail=[tm.MigrationError],
    )
    .epoch(
        _GroupResult_v2,
        lambda old: _GroupResult_v2(
            results=[
                result_timeline.migrate(result, target_type=_Result_v2) for result in old.results
            ],
        ),
        fail=[tm.MigrationError],
    )
    .epoch(
        GroupResult,
        lambda old: GroupResult(
            results=[result_timeline.migrate(result) for result in old.results],
        ),
        fail=[tm.MigrationError],
    )
)
