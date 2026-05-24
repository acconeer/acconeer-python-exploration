# Copyright (c) Acconeer AB, 2024-2026
# All rights reserved

from __future__ import annotations

import copy
from typing import Any, Optional

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

from ._aggregator import ProcessorSpec
from ._processors import (
    DistanceFilter,
    MeasurementType,
    Processor,
    ProcessorContext,
    calculate_bg_noise_std,
)
from ._thresholds import sensitivity_to_standard_deviations
from ._utils import (
    get_calibrate_noise_session_config,
    get_calibrate_offset_sensor_config,
    get_close_range_spec,
)
from ._views import RangeSweepConfig


@attrs.mutable(kw_only=True)
class DetectorContext(AlgoBase):
    offset_calibration: Optional[OffsetCalibration] = attrs.field(default=None)
    noise_calibration: Optional[NoiseCalibration] = attrs.field(default=None)
    close_range_calibration: Optional[CloseRangeCalibration] = attrs.field(default=None)
    recorded_threshold_calibration: Optional[RecordedThresholdCalibration] = attrs.field(
        default=None
    )
    sensor_ids: list[int] = attrs.field(factory=list)
    session_config_used_during_calibration: Optional[a121.SessionConfig] = attrs.field(
        default=None
    )


@attrs.frozen(kw_only=True)
class OffsetCalibration:
    """Estimates sensor offset error based on loopback measurement."""

    results: list[dict[int, a121.Result]]

    @classmethod
    def create(cls, client: a121.Client, sensor_ids: list[int]) -> te.Self:
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

    This function is called from start() in the case of CFAR and Fixed threshold and from
    record_threshold() in the case of Recorded threshold. The reason for calling from
    record_threshold() is that it is used when calculating the threshold.
    """

    results: list[dict[int, a121.Result]]

    @classmethod
    def create(
        cls, client: a121.Client, sensor_ids: list[int], session_config: a121.SessionConfig
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
        processor_specs: list[ProcessorSpec],
        session_config: a121.SessionConfig,
    ) -> list[list[float]]:
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

    extended_metadata: list[dict[int, a121.Metadata]]
    results: list[dict[int, a121.Result]]
    sensor_calibrations: dict[int, a121.SensorCalibration]

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
        processor_specs: list[ProcessorSpec],
    ) -> tuple[npt.NDArray[np.complex128], npt.NDArray[np.float64]]:
        close_range_spec = get_close_range_spec(processor_specs)
        extended_result = self.results
        result = extended_result[close_range_spec.group_index][sensor_id]
        direct_leakage = result.subframes[Processor.CLOSE_RANGE_DIST_IDX]
        phase_jitter_comp_reference = np.angle(
            result.subframes[Processor.CLOSE_RANGE_LOOPBACK_IDX]
        ).astype(float)

        return (direct_leakage, phase_jitter_comp_reference)

    def direct_leakage(
        self,
        sensor_id: int,
        processor_specs: list[ProcessorSpec],
    ) -> npt.NDArray[np.complex128]:
        direct_leakage, _ = self._close_range_calibration(sensor_id, processor_specs)
        return direct_leakage

    def phase_jitter_comp_reference(
        self,
        sensor_id: int,
        processor_specs: list[ProcessorSpec],
    ) -> npt.NDArray[np.float64]:
        _, phase_jitter_comp_reference = self._close_range_calibration(sensor_id, processor_specs)
        return phase_jitter_comp_reference


@attrs.frozen(kw_only=True)
class RecordedThresholdCalibration:
    """Calibrates the parameters used when forming the recorded threshold."""

    MIN_NUM_FRAMES_IN_VALID_THRESHOLD = 2

    # Standard deviation of angle in direct leakage over multiple sensor restarts.
    PHASE_JITTER_RESTART_STD = 0.05

    extended_metadata: list[dict[int, a121.Metadata]]
    results: list[list[dict[int, a121.Result]]]

    @classmethod
    def create(
        cls,
        client: a121.Client,
        session_config: a121.SessionConfig,
        num_frames_in_recorded_threshold: int,
    ) -> te.Self:
        if num_frames_in_recorded_threshold < cls.MIN_NUM_FRAMES_IN_VALID_THRESHOLD:
            msg = (
                f"A minimum number of {cls.MIN_NUM_FRAMES_IN_VALID_THRESHOLD} frames is required "
                f"for the recorded threshold calibration, got {num_frames_in_recorded_threshold}."
            )
            raise ValueError(msg)

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

    def _get_frame_for_spec(
        self,
        close_range_calibration: CloseRangeCalibration,
        extended_result: list[dict[int, a121.Result]],
        sensor_id: int,
        processor_specs: list[ProcessorSpec],
    ) -> npt.NDArray[np.complex128]:
        close_range_spec = get_close_range_spec(processor_specs)
        if close_range_spec.processor_config.measurement_type != MeasurementType.CLOSE_RANGE:
            msg = (
                "Recorded threshold calibration is only implemented for close-range measurements."
            )
            raise ValueError(msg)

        if close_range_calibration is None:
            msg = "Calibration data must be provided for close-range recorded threshold."
            raise ValueError(msg)

        result = extended_result[close_range_spec.group_index][sensor_id]

        num_stds_in_threshold = sensitivity_to_standard_deviations(
            close_range_spec.processor_config.threshold_sensitivity
        )
        lb_frame = result.subframes[Processor.CLOSE_RANGE_LOOPBACK_IDX]
        lb_angle = np.angle(lb_frame).astype(float)
        lb_angle += self.PHASE_JITTER_RESTART_STD * num_stds_in_threshold

        context = ProcessorContext(
            direct_leakage=close_range_calibration.direct_leakage(sensor_id, processor_specs),
            phase_jitter_comp_ref=close_range_calibration.phase_jitter_comp_reference(
                sensor_id, processor_specs
            ),
        )

        return Processor._apply_phase_jitter_compensation(
            context=context,
            frame=result.subframes[Processor.CLOSE_RANGE_DIST_IDX],
            lb_angle=lb_angle,
        )

    def _recorded_threshold_calibration(
        self,
        sensor_id: int,
        processor_specs: list[ProcessorSpec],
        session_config: a121.SessionConfig,
        noise_calibration: NoiseCalibration,
        close_range_calibration: CloseRangeCalibration,
    ) -> tuple[
        list[Optional[npt.NDArray[np.float64]]],
        list[Optional[list[np.float64]]],
        int,
    ]:
        recorded_thresholds_mean_sweep = []
        recorded_thresholds_noise_std = []

        bg_noise_std_per_spec = noise_calibration.bg_noise_std(
            sensor_id, processor_specs, session_config
        )
        for spec, bg_noise_std in zip(processor_specs, bg_noise_std_per_spec):
            # Recorded threshold calibration is only implemented for close-range measurements
            if spec.processor_config.measurement_type == MeasurementType.CLOSE_RANGE:
                range_sweep_config = RangeSweepConfig.from_sensor_config(
                    sensor_config=session_config.groups[spec.group_index][sensor_id],
                    subsweep_indexes=[Processor.CLOSE_RANGE_DIST_IDX],
                )
                profile = range_sweep_config.profile
                start_point = range_sweep_config.start_point
                step_length = range_sweep_config.step_length
                distance_filter = DistanceFilter(profile, start_point, step_length)

                frames = [
                    self._get_frame_for_spec(
                        close_range_calibration,
                        extended_result,
                        sensor_id,
                        processor_specs,
                    )
                    for extended_result in self.results
                ]
                abs_sweeps = np.stack(
                    [distance_filter.compute_envelope(frame) for frame in frames]
                )
                rec_sweeps_mean = abs_sweeps.mean(axis=0)

                bessel_factor = len(abs_sweeps) / (len(abs_sweeps) - 1)
                mean_square = np.square(abs_sweeps).mean(axis=0)
                square_mean = np.square(abs_sweeps.mean(axis=0))
                bg_sc_sweep_std = np.sqrt(bessel_factor * np.abs(mean_square - square_mean))

                assert bg_noise_std is not None
                rec_noise_std = []
                subsweep_slices_cropped = range_sweep_config.subsweep_slices.cropped(
                    edge_margin=distance_filter.margin
                )
                for subsweep_slice, tx_off_noise_std in zip(subsweep_slices_cropped, bg_noise_std):
                    # Clamp negative values to zero as the variable is in square root below
                    sigma_square_diff = np.clip(
                        bg_sc_sweep_std[subsweep_slice] ** 2 - tx_off_noise_std**2,
                        a_min=0,
                        a_max=None,
                    )
                    rec_noise_std.append(
                        np.mean(np.sqrt(sigma_square_diff) / rec_sweeps_mean[subsweep_slice])
                    )

            else:
                rec_sweeps_mean = None
                rec_noise_std = None

            recorded_thresholds_mean_sweep.append(rec_sweeps_mean)
            recorded_thresholds_noise_std.append(rec_noise_std)

        return (
            recorded_thresholds_mean_sweep,
            recorded_thresholds_noise_std,
            self.results[-1][0][sensor_id].temperature,
        )

    def recorded_thresholds_mean_sweep(
        self,
        sensor_id: int,
        processor_specs: list[ProcessorSpec],
        session_config: a121.SessionConfig,
        noise_calibration: NoiseCalibration,
        close_range_calibration: CloseRangeCalibration,
    ) -> list[Optional[npt.NDArray[np.float64]]]:
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
        processor_specs: list[ProcessorSpec],
        session_config: a121.SessionConfig,
        noise_calibration: NoiseCalibration,
        close_range_calibration: CloseRangeCalibration,
    ) -> list[Optional[list[np.float64]]]:
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
        processor_specs: list[ProcessorSpec],
        session_config: a121.SessionConfig,
        noise_calibration: NoiseCalibration,
        close_range_calibration: CloseRangeCalibration,
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
    single_sensor_contexts: Optional[dict[int, _SingleSensorContext_v0]] = attrs.field(
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
        session_config: a121.SessionConfig, sensor_ids: list[int]
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
            ctx.extra_context.close_range_frames is not None
            for ctx in self.single_sensor_contexts.values()
        )
        has_recorded_threshold = any(
            ctx.extra_context.recorded_threshold_frames is not None
            for ctx in self.single_sensor_contexts.values()
        )

        # Session config
        session_config_used_during_calibration = next(
            iter(self.single_sensor_contexts.values())
        ).session_config_used_during_calibration

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
                result_frame: list[npt.NDArray[np.complex128]] = []
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
            rec_thres_frames = next(
                iter(self.single_sensor_contexts.values())
            ).extra_context.recorded_threshold_frames
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
        sensor_calibrations: dict[int, Optional[a121.SensorCalibration]] = {
            k: v.sensor_calibration for k, v in self.single_sensor_contexts.items()
        }
        sensor_calibrations_re: dict[int, a121.SensorCalibration] = (
            {k: v for k, v in sensor_calibrations.items() if v is not None}
            if all(x is not None for x in sensor_calibrations.values())
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
    offset_frames: Optional[list[list[npt.NDArray[np.complex128]]]] = attrs.field(
        default=None, eq=attrs_optional_ndarray_isclose
    )
    noise_frames: Optional[list[list[npt.NDArray[np.complex128]]]] = attrs.field(
        default=None, eq=attrs_optional_ndarray_isclose
    )
    close_range_frames: Optional[list[list[npt.NDArray[np.complex128]]]] = attrs.field(
        default=None, eq=attrs_optional_ndarray_isclose
    )
    recorded_threshold_frames: Optional[list[list[npt.NDArray[np.complex128]]]] = attrs.field(
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
    recorded_thresholds_mean_sweep: Optional[list[npt.NDArray[np.float64]]] = attrs.field(
        default=None, eq=attrs_optional_ndarray_isclose
    )
    recorded_thresholds_noise_std: Optional[list[list[np.float64]]] = attrs.field(
        default=None, eq=attrs_optional_ndarray_isclose
    )
    bg_noise_std: Optional[list[list[float]]] = attrs.field(
        default=None, eq=attrs_optional_ndarray_isclose
    )
    session_config_used_during_calibration: Optional[a121.SessionConfig] = attrs.field(
        default=None
    )
    reference_temperature: Optional[int] = attrs.field(default=None)
    sensor_calibration: Optional[a121.SensorCalibration] = attrs.field(default=None)
    extra_context: _SingleSensorExtraContext_v0 = attrs.field(factory=_SingleSensorExtraContext_v0)

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
        context_dict: dict[str, Any] = {}
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
