# Copyright (c) Acconeer AB, 2024
# All rights reserved

from __future__ import annotations

from typing import Any, Dict, List, Optional

import attrs
import h5py
import numpy as np
import numpy.typing as npt

from acconeer.exptool import a121
from acconeer.exptool._core.class_creation.attrs import attrs_optional_ndarray_isclose
from acconeer.exptool.a121._h5_utils import _create_h5_string_dataset
from acconeer.exptool.a121.algo import AlgoBase


@attrs.mutable(kw_only=True)
class DetectorContext(AlgoBase):
    single_sensor_contexts: Dict[int, SingleSensorContext] = attrs.field(default=None)
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
    def from_h5(cls, group: h5py.Group) -> DetectorContext:
        context_dict = {}

        for key in group.keys():  # noqa: SIM118
            if cls._GROUP_NAME in key:
                sensor_id = int(key.split("_")[-1])
                context_dict[sensor_id] = SingleSensorContext.from_h5(group[key])

        return DetectorContext(single_sensor_contexts=context_dict)


@attrs.mutable(kw_only=True)
class SingleSensorExtraContext(AlgoBase):
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
class SingleSensorContext(AlgoBase):
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
    extra_context: SingleSensorExtraContext = attrs.field(factory=SingleSensorExtraContext)
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
    def from_h5(cls, group: h5py.Group) -> SingleSensorContext:
        context_dict: Dict[str, Any] = {}
        context_dict["extra_context"] = {}

        unknown_keys = set(group.keys()) - set(attrs.fields_dict(SingleSensorContext).keys())
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

        context_dict["extra_context"] = SingleSensorExtraContext(**context_dict["extra_context"])

        return SingleSensorContext(**context_dict)


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
