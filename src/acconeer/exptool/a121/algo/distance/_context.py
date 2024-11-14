# Copyright (c) Acconeer AB, 2024
# All rights reserved

from __future__ import annotations

import copy
from typing import Any, Dict, List, Optional, Tuple

import attrs
import h5py
import numpy as np
import numpy.typing as npt
import typing_extensions as te

from acconeer.exptool import a121, opser
from acconeer.exptool import type_migration as tm
from acconeer.exptool._core.class_creation.attrs import attrs_optional_ndarray_isclose
from acconeer.exptool.a121._h5_utils import _create_h5_string_dataset
from acconeer.exptool.a121.algo import (
    AlgoBase,
    calculate_loopback_peak_location,
)

from ._aggregator import Aggregator, AggregatorConfig, ProcessorSpec
from ._processors import ProcessorContext, ProcessorMode, calculate_bg_noise_std
from ._utils import (
    filter_close_range_spec,
    get_calibrate_noise_session_config,
    get_calibrate_offset_sensor_config,
    update_processor_mode,
)


@attrs.mutable(kw_only=True)
class DetectorContext(AlgoBase):
    offset_calibration: Optional[OffsetCalibration] = attrs.field(default=None)
    noise_calibration: Optional[NoiseCalibration] = attrs.field(default=None)
    close_range_calibration: Optional[CloseRangeCalibration] = attrs.field(default=None)
    recorded_threshold_calibration: Optional[RecordedThresholdCalibration] = attrs.field(
        default=None
    )
    sensor_ids: List[int] = attrs.field(factory=list)
    session_config_used_during_calibration: Optional[a121.SessionConfig] = attrs.field(
        default=None
    )


@attrs.frozen(kw_only=True)
class OffsetCalibration:
    """Estimates sensor offset error based on loopback measurement."""

    results: List[Dict[int, a121.Result]]

    @classmethod
    def create(cls, client: a121.Client, sensor_ids: List[int]) -> te.Self:
        sensor_config = get_calibrate_offset_sensor_config()

        session_config = a121.SessionConfig(
            {sensor_id: sensor_config for sensor_id in sensor_ids}, extended=True
        )
        client.setup_session(session_config)
        client.start_session()
        extended_result = client.get_next()
        client.stop_session()

        assert isinstance(extended_result, list)

        return cls(results=extended_result)

    def loopback_peak_location_m(self, sensor_id: int) -> float:
        sensor_config = get_calibrate_offset_sensor_config()
        lb_peak_location_m = calculate_loopback_peak_location(
            self.results[0][sensor_id], sensor_config
        )
        return lb_peak_location_m


@attrs.frozen(kw_only=True)
class NoiseCalibration:
    """Estimates the standard deviation of the noise in each subsweep by setting enable_tx to
    False and collecting data, used to calculate the deviation.

    The calibration procedure can be done at any time as it is performed with Tx off, and is
    not effected by objects in front of the sensor.

    This function is called from the start() in the case of CFAR and Fixed threshold and from
    record_threshold() in the case of Recorded threshold. The reason for calling from
    record_threshold() is that it is used when calculating the threshold.
    """

    results: List[Dict[int, a121.Result]]

    @classmethod
    def create(
        cls, client: a121.Client, sensor_ids: List[int], session_config: a121.SessionConfig
    ) -> te.Self:
        session_config = get_calibrate_noise_session_config(session_config, sensor_ids)

        extended_metadata = client.setup_session(session_config)
        assert isinstance(extended_metadata, list)

        client.start_session()
        extended_result = client.get_next()
        client.stop_session()

        assert isinstance(extended_result, list)
        return cls(results=extended_result)

    def bg_noise_std(
        self,
        sensor_id: int,
        processor_specs: List[ProcessorSpec],
        session_config: a121.SessionConfig,
    ) -> List[List[float]]:
        bg_noise_one_sensor = []
        for spec in processor_specs:
            result = self.results[spec.group_index][sensor_id]
            sensor_config = session_config.groups[spec.group_index][sensor_id]
            subsweep_configs = sensor_config.subsweeps
            bg_noise_std_in_subsweep = []
            for idx in spec.subsweep_indexes:
                if not subsweep_configs[idx].enable_loopback:
                    subframe = result.subframes[idx]
                    subsweep_std = calculate_bg_noise_std(subframe, subsweep_configs[idx])
                    bg_noise_std_in_subsweep.append(subsweep_std)
            bg_noise_one_sensor.append(bg_noise_std_in_subsweep)

        return bg_noise_one_sensor


@attrs.frozen(kw_only=True)
class CloseRangeCalibration:
    """Calibrates the close range measurement parameters used when subtracting the direct
    leakage from the measured signal.

    The parameters calibrated are the direct leakage and a phase reference, used to reduce
    the amount of phase jitter, with the purpose of reducing the residual.
    """

    extended_metadata: List[Dict[int, a121.Metadata]]
    results: List[Dict[int, a121.Result]]
    sensor_calibrations: Dict[int, a121.SensorCalibration]

    @classmethod
    def create(cls, client: a121.Client, session_config: a121.SessionConfig) -> te.Self:
        extended_metadata = client.setup_session(session_config)
        assert isinstance(extended_metadata, list)

        client.start_session()
        extended_result = client.get_next()
        client.stop_session()

        assert isinstance(extended_result, list)

        return cls(
            extended_metadata=extended_metadata,
            results=extended_result,
            sensor_calibrations=client.calibrations,
        )

    def _close_range_calibration(
        self,
        sensor_id: int,
        processor_specs: List[ProcessorSpec],
        session_config: a121.SessionConfig,
    ) -> Tuple[npt.NDArray[np.complex128], npt.NDArray[np.float64]]:
        close_range_spec = filter_close_range_spec(processor_specs)
        spec = update_processor_mode(close_range_spec, ProcessorMode.LEAKAGE_CALIBRATION)

        aggregator = Aggregator(
            session_config=session_config,
            extended_metadata=self.extended_metadata,
            config=AggregatorConfig(),
            specs=spec,
            sensor_id=sensor_id,
        )

        aggregator_result = aggregator.process(extended_result=self.results)
        (processor_result,) = aggregator_result.processor_results
        assert processor_result.direct_leakage is not None
        assert processor_result.phase_jitter_comp_reference is not None

        return (processor_result.direct_leakage, processor_result.phase_jitter_comp_reference)

    def direct_leakage(
        self,
        sensor_id: int,
        processor_specs: List[ProcessorSpec],
        session_config: a121.SessionConfig,
    ) -> npt.NDArray[np.complex128]:
        direct_leakage, _ = self._close_range_calibration(
            sensor_id, processor_specs, session_config
        )
        return direct_leakage

    def phase_jitter_comp_reference(
        self,
        sensor_id: int,
        processor_specs: List[ProcessorSpec],
        session_config: a121.SessionConfig,
    ) -> npt.NDArray[np.float64]:
        _, phase_jitter_comp_reference = self._close_range_calibration(
            sensor_id, processor_specs, session_config
        )
        return phase_jitter_comp_reference


@attrs.frozen(kw_only=True)
class RecordedThresholdCalibration:
    """Calibrates the parameters used when forming the recorded threshold."""

    extended_metadata: List[Dict[int, a121.Metadata]]
    results: List[List[Dict[int, a121.Result]]]

    @classmethod
    def create(
        cls,
        client: a121.Client,
        session_config: a121.SessionConfig,
        num_frames_in_recorded_threshold: int,
    ) -> te.Self:
        extended_metadata = client.setup_session(session_config)
        assert isinstance(extended_metadata, list)

        recorded_threshold_result = []

        client.start_session()
        for _ in range(num_frames_in_recorded_threshold):
            extended_result = client.get_next()
            assert isinstance(extended_result, list)
            recorded_threshold_result.append(extended_result)
        client.stop_session()

        return cls(extended_metadata=extended_metadata, results=recorded_threshold_result)

    @staticmethod
    def _add_context_to_processor_spec(
        noise_calibration: NoiseCalibration,
        close_range_calibration: Optional[CloseRangeCalibration],
        sensor_id: int,
        processor_specs: list[ProcessorSpec],
        session_config: a121.SessionConfig,
    ) -> List[ProcessorSpec]:
        """
        Create and add processor context to processor specification.
        """

        bg_noise_stds = noise_calibration.bg_noise_std(sensor_id, processor_specs, session_config)
        updated_specs: List[ProcessorSpec] = []

        for idx, (spec, bg_noise_std) in enumerate(zip(processor_specs, bg_noise_stds)):
            processor_context = ProcessorContext(
                recorded_threshold_mean_sweep=None,
                recorded_threshold_noise_std=None,
                bg_noise_std=bg_noise_std,
                direct_leakage=close_range_calibration.direct_leakage(
                    sensor_id,
                    processor_specs,
                    session_config,
                )
                if close_range_calibration is not None
                else None,
                phase_jitter_comp_ref=close_range_calibration.phase_jitter_comp_reference(
                    sensor_id,
                    processor_specs,
                    session_config,
                )
                if close_range_calibration is not None
                else None,
                reference_temperature=None,
                loopback_peak_location_m=None,
            )
            updated_specs.append(attrs.evolve(spec, processor_context=processor_context))
        return updated_specs

    def _recorded_threshold_calibration(
        self,
        sensor_id: int,
        processor_specs: List[ProcessorSpec],
        session_config: a121.SessionConfig,
        noise_calibration: NoiseCalibration,
        close_range_calibration: Optional[CloseRangeCalibration],
    ) -> Tuple[
        List[npt.NDArray[np.float64]],
        List[List[np.float64]],
        int,
    ]:
        specs_updated = update_processor_mode(
            processor_specs, ProcessorMode.RECORDED_THRESHOLD_CALIBRATION
        )

        specs = self._add_context_to_processor_spec(
            noise_calibration,
            close_range_calibration,
            sensor_id,
            specs_updated,
            session_config,
        )

        aggregator = Aggregator(
            session_config=session_config,
            extended_metadata=self.extended_metadata,
            config=AggregatorConfig(),
            specs=specs,
            sensor_id=sensor_id,
        )

        for extended_result in self.results:
            aggregator_result = aggregator.process(extended_result=extended_result)

        recorded_thresholds_mean_sweep = []
        recorded_thresholds_noise_std = []
        for processor_result in aggregator_result.processor_results:
            # Since we know what mode the processor is running in
            assert processor_result.recorded_threshold_mean_sweep is not None
            assert processor_result.recorded_threshold_noise_std is not None

            recorded_thresholds_mean_sweep.append(processor_result.recorded_threshold_mean_sweep)
            recorded_thresholds_noise_std.append(processor_result.recorded_threshold_noise_std)

        return (
            recorded_thresholds_mean_sweep,
            recorded_thresholds_noise_std,
            extended_result[0][sensor_id].temperature,
        )

    def recorded_thresholds_mean_sweep(
        self,
        sensor_id: int,
        processor_specs: List[ProcessorSpec],
        session_config: a121.SessionConfig,
        noise_calibration: NoiseCalibration,
        close_range_calibration: Optional[CloseRangeCalibration],
    ) -> List[npt.NDArray[np.float64]]:
        mean_sweep, _, _ = self._recorded_threshold_calibration(
            sensor_id,
            processor_specs,
            session_config,
            noise_calibration,
            close_range_calibration,
        )
        return mean_sweep

    def recorded_thresholds_noise_std(
        self,
        sensor_id: int,
        processor_specs: List[ProcessorSpec],
        session_config: a121.SessionConfig,
        noise_calibration: NoiseCalibration,
        close_range_calibration: Optional[CloseRangeCalibration],
    ) -> List[List[np.float64]]:
        _, noise_std, _ = self._recorded_threshold_calibration(
            sensor_id,
            processor_specs,
            session_config,
            noise_calibration,
            close_range_calibration,
        )
        return noise_std

    def reference_temperature(
        self,
        sensor_id: int,
        processor_specs: List[ProcessorSpec],
        session_config: a121.SessionConfig,
        noise_calibration: NoiseCalibration,
        close_range_calibration: Optional[CloseRangeCalibration],
    ) -> int:
        _, _, ref_temp = self._recorded_threshold_calibration(
            sensor_id,
            processor_specs,
            session_config,
            noise_calibration,
            close_range_calibration,
        )
        return ref_temp


def _get_group_items(group: h5py.Group) -> list[npt.NDArray[Any]]:
    group_items = []

    i = 0
    while True:
        try:
            v = group[f"index_{i}"][()]
        except KeyError:
            break

        group_items.append(v)
        i += 1
    return group_items


############################
# For migration purpose only
############################


@attrs.mutable(kw_only=True)
class _DetectorContext_v0(AlgoBase):
    single_sensor_contexts: Optional[Dict[int, _SingleSensorContext_v0]] = attrs.field(
        default=None
    )
    _GROUP_NAME = "sensor_id_"

    @property
    def sensor_ids(self) -> Optional[list[int]]:
        if self.single_sensor_contexts:
            return list(self.single_sensor_contexts.keys())
        else:
            return None

    def to_h5(self, group: h5py.Group) -> None:
        if self.single_sensor_contexts is not None:
            for sensor_id, context in self.single_sensor_contexts.items():
                context.to_h5(group.create_group(self._GROUP_NAME + str(sensor_id)))

    @classmethod
    def from_h5(cls, group: h5py.Group) -> _DetectorContext_v0:
        context_dict = {}

        for key in group.keys():  # noqa: SIM118
            if cls._GROUP_NAME in key:
                sensor_id = int(key.split("_")[-1])
                context_dict[sensor_id] = _SingleSensorContext_v0.from_h5(group[key])

        return _DetectorContext_v0(single_sensor_contexts=context_dict)

    @staticmethod
    def _get_calibrate_noise_session_config(
        session_config: a121.SessionConfig, sensor_ids: List[int]
    ) -> a121.SessionConfig:
        noise_session_config = copy.deepcopy(session_config)

        for sensor_id in sensor_ids:
            for group in noise_session_config.groups:
                group[sensor_id].sweeps_per_frame = 1
                # Set num_points to a high number to get sufficient number of data points to
                # estimate the standard deviation. Extra num_points for step_length = 1 together
                # with profile = 5 due to filter margin and cropping
                if any(
                    ss.step_length == 1 and ss.profile == a121.Profile.PROFILE_5
                    for ss in group[sensor_id].subsweeps
                ):
                    num_points = 352
                else:
                    num_points = 220
                for subsweep in group[sensor_id].subsweeps:
                    subsweep.enable_tx = False
                    subsweep.step_length = 1
                    subsweep.start_point = 0
                    subsweep.num_points = num_points

        return noise_session_config

    def migrate(self) -> DetectorContext:
        if not self.single_sensor_contexts:
            return DetectorContext()

        base_step_length_m = 0.00250227400101721
        has_close_range = any(
            [
                ctx.extra_context.close_range_frames is not None
                for ctx in self.single_sensor_contexts.values()
            ]
        )
        has_recorded_threshold = any(
            [
                ctx.extra_context.recorded_threshold_frames is not None
                for ctx in self.single_sensor_contexts.values()
            ]
        )

        # Session config
        session_config_used_during_calibration = list(self.single_sensor_contexts.values())[
            0
        ].session_config_used_during_calibration

        assert session_config_used_during_calibration is not None

        # Metadata
        metadata = a121.Metadata(
            frame_data_length=0,
            sweep_data_length=0,
            subsweep_data_offset=np.array([0]),
            subsweep_data_length=np.array([0]),
            calibration_temperature=25,
            tick_period=0,
            base_step_length_m=base_step_length_m,
            max_sweep_rate=0,
            high_speed_mode=False,
        )
        extended_metadata = [
            {k: metadata for k in group} for group in session_config_used_during_calibration.groups
        ]

        # Offset result
        offset_result = [
            {
                k: a121.Result(
                    data_saturated=False,
                    frame_delayed=False,
                    calibration_needed=False,
                    temperature=ctx.reference_temperature
                    if ctx.reference_temperature is not None
                    else 25,
                    frame=ctx.extra_context.offset_frames[0][0]
                    if ctx.extra_context.offset_frames is not None
                    else np.array([]),
                    tick=0,
                    context=a121._core.entities.ResultContext(
                        metadata=a121.Metadata(
                            frame_data_length=50,
                            sweep_data_length=50,
                            subsweep_data_offset=np.array([0]),
                            subsweep_data_length=np.array([50]),
                            calibration_temperature=ctx.reference_temperature
                            if ctx.reference_temperature is not None
                            else 25,
                            tick_period=0,
                            base_step_length_m=base_step_length_m,
                            max_sweep_rate=168,
                            high_speed_mode=False,
                        ),
                        ticks_per_second=1000,
                    ),
                )
                for k, ctx in self.single_sensor_contexts.items()
            }
        ]

        # Noise result
        sensor_ids = self.sensor_ids
        assert sensor_ids is not None

        noise_session_config = _DetectorContext_v0._get_calibrate_noise_session_config(
            session_config_used_during_calibration, sensor_ids
        )
        noise_result = []

        for group_idx, group in enumerate(noise_session_config.groups):
            group_result = {}
            frame_offset = {}
            for sensor_id, sensor_config in group.items():
                noise_frames = self.single_sensor_contexts[sensor_id].extra_context.noise_frames
                assert noise_frames is not None
                if sensor_id not in frame_offset:
                    frame_offset[sensor_id] = 0
                result_frame: List[npt.NDArray[np.complex128]] = []
                num_points = []
                subsweep_data_offset = []
                total_num_points = 0
                for ss in sensor_config.subsweeps:
                    subsweep_data_offset.append(total_num_points)
                    total_num_points += ss.num_points
                    result_frame.extend(
                        noise_frames[group_idx][0][
                            frame_offset[sensor_id] : ss.num_points
                            * sensor_config.sweeps_per_frame
                        ]
                    )
                    frame_offset[sensor_id] += ss.num_points * sensor_config.sweeps_per_frame
                    num_points.append(ss.num_points)
                result = a121.Result(
                    data_saturated=False,
                    frame_delayed=False,
                    calibration_needed=False,
                    temperature=27,
                    frame=np.array(result_frame),
                    tick=0,
                    context=a121._core.entities.ResultContext(
                        metadata=a121.Metadata(
                            frame_data_length=np.sum(num_points) * sensor_config.sweeps_per_frame,
                            sweep_data_length=np.sum(num_points),
                            subsweep_data_offset=np.array(subsweep_data_offset),
                            subsweep_data_length=np.array(num_points),
                            calibration_temperature=27,
                            tick_period=0,
                            base_step_length_m=base_step_length_m,
                            max_sweep_rate=168,
                            high_speed_mode=False,
                        ),
                        ticks_per_second=1000,
                    ),
                )

                group_result[sensor_id] = result

            noise_result.append(group_result)

        # Close range result
        if has_close_range:
            close_range_result = []

            for group in session_config_used_during_calibration.groups:
                group_result = {}
                frame_offset = {}
                for sensor_id, sensor_config in group.items():
                    close_range_frames = self.single_sensor_contexts[
                        sensor_id
                    ].extra_context.close_range_frames
                    assert close_range_frames is not None
                    if sensor_id not in frame_offset:
                        frame_offset[sensor_id] = 0
                    result_frame = []
                    num_points = []
                    subsweep_data_offset = []
                    total_num_points = 0
                    for ss in sensor_config.subsweeps:
                        subsweep_data_offset.append(total_num_points)
                        total_num_points += ss.num_points
                        result_frame.extend(
                            close_range_frames[0][0][:][
                                frame_offset[sensor_id] : ss.num_points
                                * sensor_config.sweeps_per_frame
                            ]
                        )
                        frame_offset[sensor_id] += ss.num_points * sensor_config.sweeps_per_frame
                        num_points.append(ss.num_points)
                    result = a121.Result(
                        data_saturated=False,
                        frame_delayed=False,
                        calibration_needed=False,
                        temperature=25,
                        frame=np.array(result_frame),
                        tick=0,
                        context=a121._core.entities.ResultContext(
                            metadata=a121.Metadata(
                                frame_data_length=np.sum(num_points)
                                * sensor_config.sweeps_per_frame,
                                sweep_data_length=np.sum(num_points),
                                subsweep_data_offset=np.array(subsweep_data_offset),
                                subsweep_data_length=np.array(num_points),
                                calibration_temperature=25,
                                tick_period=0,
                                base_step_length_m=base_step_length_m,
                                max_sweep_rate=168,
                                high_speed_mode=False,
                            ),
                            ticks_per_second=1000,
                        ),
                    )

                    group_result[sensor_id] = result

                close_range_result.append(group_result)

        # Recorded threshold result
        if has_recorded_threshold:
            recorded_threshold_result = []
            rec_thres_frames = list(self.single_sensor_contexts.values())[
                0
            ].extra_context.recorded_threshold_frames
            assert rec_thres_frames is not None
            num_rec_sweeps = len(rec_thres_frames[0])

            for i in range(num_rec_sweeps):
                group_results = []
                for group_idx, group in enumerate(session_config_used_during_calibration.groups):
                    group_result = {}
                    frame_offset = {}
                    for sensor_id, sensor_config in group.items():
                        recorded_threshold_frames = self.single_sensor_contexts[
                            sensor_id
                        ].extra_context.recorded_threshold_frames
                        assert recorded_threshold_frames is not None
                        if sensor_id not in frame_offset:
                            frame_offset[sensor_id] = 0
                        result_frame = []
                        num_points = []
                        subsweep_data_offset = []
                        total_num_points = 0
                        for ss in sensor_config.subsweeps:
                            subsweep_data_offset.append(total_num_points)
                            total_num_points += ss.num_points
                            result_frame.extend(
                                recorded_threshold_frames[group_idx][i][:][
                                    frame_offset[sensor_id] : ss.num_points
                                    * sensor_config.sweeps_per_frame
                                ]
                            )
                            frame_offset[sensor_id] += (
                                ss.num_points * sensor_config.sweeps_per_frame
                            )
                            num_points.append(ss.num_points)

                        result = a121.Result(
                            data_saturated=False,
                            frame_delayed=False,
                            calibration_needed=False,
                            temperature=25,
                            frame=np.array(result_frame),
                            tick=0,
                            context=a121._core.entities.ResultContext(
                                metadata=a121.Metadata(
                                    frame_data_length=np.sum(num_points)
                                    * sensor_config.sweeps_per_frame,
                                    sweep_data_length=np.sum(num_points),
                                    subsweep_data_offset=np.array(subsweep_data_offset),
                                    subsweep_data_length=np.array(num_points),
                                    calibration_temperature=25,
                                    tick_period=0,
                                    base_step_length_m=base_step_length_m,
                                    max_sweep_rate=168,
                                    high_speed_mode=False,
                                ),
                                ticks_per_second=1000,
                            ),
                        )

                        group_result[sensor_id] = result
                    group_results.append(group_result)
                recorded_threshold_result.append(group_results)

        # Sensor calibrations
        sensor_calibrations: Dict[int, Optional[a121.SensorCalibration]] = {
            k: v.sensor_calibration for k, v in self.single_sensor_contexts.items()
        }
        sensor_calibrations_re: Dict[int, a121.SensorCalibration] = (
            {k: v for k, v in sensor_calibrations.items() if v is not None}
            if all([x is not None for x in sensor_calibrations.values()])
            else {}
        )
        return DetectorContext(
            offset_calibration=OffsetCalibration(results=offset_result),
            noise_calibration=NoiseCalibration(results=noise_result),
            close_range_calibration=CloseRangeCalibration(
                extended_metadata=extended_metadata,
                results=close_range_result,
                sensor_calibrations=sensor_calibrations_re,
            )
            if has_close_range
            else None,
            recorded_threshold_calibration=RecordedThresholdCalibration(
                extended_metadata=extended_metadata, results=recorded_threshold_result
            )
            if has_recorded_threshold
            else None,
            sensor_ids=list(self.single_sensor_contexts.keys()),
            session_config_used_during_calibration=session_config_used_during_calibration,
        )


@attrs.mutable(kw_only=True)
class _SingleSensorExtraContext_v0(AlgoBase):
    offset_frames: Optional[List[List[npt.NDArray[np.complex128]]]] = attrs.field(
        default=None, eq=attrs_optional_ndarray_isclose
    )
    noise_frames: Optional[List[List[npt.NDArray[np.complex128]]]] = attrs.field(
        default=None, eq=attrs_optional_ndarray_isclose
    )
    close_range_frames: Optional[List[List[npt.NDArray[np.complex128]]]] = attrs.field(
        default=None, eq=attrs_optional_ndarray_isclose
    )
    recorded_threshold_frames: Optional[List[List[npt.NDArray[np.complex128]]]] = attrs.field(
        default=None, eq=attrs_optional_ndarray_isclose
    )


@attrs.mutable(kw_only=True)
class _SingleSensorContext_v0(AlgoBase):
    loopback_peak_location_m: Optional[float] = attrs.field(default=None)
    direct_leakage: Optional[npt.NDArray[np.complex128]] = attrs.field(
        default=None, eq=attrs_optional_ndarray_isclose
    )
    phase_jitter_comp_reference: Optional[npt.NDArray[np.float64]] = attrs.field(
        default=None, eq=attrs_optional_ndarray_isclose
    )
    recorded_thresholds_mean_sweep: Optional[List[npt.NDArray[np.float64]]] = attrs.field(
        default=None, eq=attrs_optional_ndarray_isclose
    )
    recorded_thresholds_noise_std: Optional[List[List[np.float64]]] = attrs.field(
        default=None, eq=attrs_optional_ndarray_isclose
    )
    bg_noise_std: Optional[List[List[float]]] = attrs.field(
        default=None, eq=attrs_optional_ndarray_isclose
    )
    session_config_used_during_calibration: Optional[a121.SessionConfig] = attrs.field(
        default=None
    )
    reference_temperature: Optional[int] = attrs.field(default=None)
    sensor_calibration: Optional[a121.SensorCalibration] = attrs.field(default=None)
    extra_context: _SingleSensorExtraContext_v0 = attrs.field(factory=_SingleSensorExtraContext_v0)
    # TODO: Make recorded_thresholds Optional[List[Optional[npt.NDArray[np.float64]]]]

    def to_h5(self, group: h5py.Group) -> None:
        for k, v in attrs.asdict(self, recurse=False).items():
            if k in [
                "recorded_thresholds_mean_sweep",
                "recorded_thresholds_noise_std",
                "bg_noise_std",
                "extra_context",
            ]:
                continue

            if v is None:
                continue

            if isinstance(v, a121.SessionConfig):
                _create_h5_string_dataset(group, k, v.to_json())
            elif isinstance(v, a121.SensorCalibration):
                sensor_calibration_group = group.create_group("sensor_calibration")
                v.to_h5(sensor_calibration_group)
            elif isinstance(v, (np.ndarray, float, int, np.integer)):
                group.create_dataset(k, data=v, track_times=False)
            else:
                msg = f"Unexpected {type(self).__name__} field '{k}' of type '{type(v)}'"
                raise RuntimeError(msg)

        if self.recorded_thresholds_mean_sweep is not None:
            recorded_thresholds_mean_sweep_group = group.create_group(
                "recorded_thresholds_mean_sweep"
            )

            for i, v in enumerate(self.recorded_thresholds_mean_sweep):
                recorded_thresholds_mean_sweep_group.create_dataset(
                    f"index_{i}", data=v, track_times=False
                )

        if self.recorded_thresholds_noise_std is not None:
            recorded_thresholds_std_group = group.create_group("recorded_thresholds_noise_std")

            for i, v in enumerate(self.recorded_thresholds_noise_std):
                recorded_thresholds_std_group.create_dataset(
                    f"index_{i}", data=v, track_times=False
                )

        if self.bg_noise_std is not None:
            bg_noise_std_group = group.create_group("bg_noise_std")

            for i, v in enumerate(self.bg_noise_std):
                bg_noise_std_group.create_dataset(f"index_{i}", data=v, track_times=False)

        extra_group = group.create_group("extra_context")

        if self.extra_context.offset_frames is not None:
            offset_frames_group = extra_group.create_group("offset_frames")

            for i, v in enumerate(self.extra_context.offset_frames):
                offset_frames_group.create_dataset(f"index_{i}", data=v, track_times=False)

        if self.extra_context.noise_frames is not None:
            noise_frames_group = extra_group.create_group("noise_frames")

            for i, v in enumerate(self.extra_context.noise_frames):
                noise_frames_group.create_dataset(f"index_{i}", data=v, track_times=False)

        if self.extra_context.close_range_frames is not None:
            close_range_frames_group = extra_group.create_group("close_range_frames")

            for i, v in enumerate(self.extra_context.close_range_frames):
                close_range_frames_group.create_dataset(f"index_{i}", data=v, track_times=False)

        if self.extra_context.recorded_threshold_frames is not None:
            recorded_threshold_frames_group = extra_group.create_group("recorded_threshold_frames")

            for i, v in enumerate(self.extra_context.recorded_threshold_frames):
                recorded_threshold_frames_group.create_dataset(
                    f"index_{i}", data=v, track_times=False
                )

    @classmethod
    def from_h5(cls, group: h5py.Group) -> _SingleSensorContext_v0:
        context_dict: Dict[str, Any] = {}
        context_dict["extra_context"] = {}

        unknown_keys = set(group.keys()) - set(attrs.fields_dict(_SingleSensorContext_v0).keys())
        if unknown_keys:
            msg = f"Unknown field(s) in stored context: {unknown_keys}"
            raise Exception(msg)

        field_map = {
            "loopback_peak_location_m": None,
            "direct_leakage": None,
            "reference_temperature": None,
            "phase_jitter_comp_reference": None,
            "session_config_used_during_calibration": a121.SessionConfig.from_json,
        }
        for k, func in field_map.items():
            try:
                v = group[k][()]
            except KeyError:
                continue

            context_dict[k] = func(v) if func else v

        if "recorded_thresholds_mean_sweep" in group:
            mean_sweeps = _get_group_items(group["recorded_thresholds_mean_sweep"])
            context_dict["recorded_thresholds_mean_sweep"] = mean_sweeps

        if "recorded_thresholds_noise_std" in group:
            noise_stds = _get_group_items(group["recorded_thresholds_noise_std"])
            context_dict["recorded_thresholds_noise_std"] = noise_stds

        if "bg_noise_std" in group:
            bg_noise_std = _get_group_items(group["bg_noise_std"])
            context_dict["bg_noise_std"] = bg_noise_std

        if "sensor_calibration" in group:
            context_dict["sensor_calibration"] = a121.SensorCalibration.from_h5(
                group["sensor_calibration"]
            )

        if "extra_context" in group:
            extra_group = group["extra_context"]

            if "offset_frames" in extra_group:
                offset_frames = _get_group_items(extra_group["offset_frames"])
                context_dict["extra_context"]["offset_frames"] = offset_frames

            if "noise_frames" in extra_group:
                noise_frames = _get_group_items(extra_group["noise_frames"])
                context_dict["extra_context"]["noise_frames"] = noise_frames

            if "close_range_frames" in extra_group:
                close_range_frames = _get_group_items(extra_group["close_range_frames"])
                context_dict["extra_context"]["close_range_frames"] = close_range_frames

            if "recorded_threshold_frames" in extra_group:
                recorded_threshold_frames = _get_group_items(
                    extra_group["recorded_threshold_frames"]
                )
                context_dict["extra_context"]["recorded_threshold_frames"] = (
                    recorded_threshold_frames
                )

        context_dict["extra_context"] = _SingleSensorExtraContext_v0(
            **context_dict["extra_context"]
        )

        return _SingleSensorContext_v0(**context_dict)


detector_context_timeline = (
    tm.start(_DetectorContext_v0)
    .load(str, _DetectorContext_v0.from_json, fail=[])
    .load(h5py.Group, _DetectorContext_v0.from_h5, fail=[])
    .nop()
    .epoch(DetectorContext, _DetectorContext_v0.migrate, fail=[])
    .load(str, DetectorContext.from_json, fail=[])
    .load(
        h5py.Group,
        lambda x: opser.deserialize(x, DetectorContext),
        fail=[opser.core.LoadErrorGroup],
    )
)
