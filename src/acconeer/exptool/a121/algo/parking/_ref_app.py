# Copyright (c) Acconeer AB, 2023-2024
# All rights reserved

from __future__ import annotations

import copy
import enum
import warnings
from typing import Any, Dict, Optional, Tuple

import attrs
import h5py
import numpy as np
import numpy.typing as npt
from attributes_doc import attributes_doc

from acconeer.exptool import a121, opser
from acconeer.exptool.a121._h5_utils import _create_h5_string_dataset
from acconeer.exptool.a121.algo import (
    APPROX_BASE_STEP_LENGTH_M,
    ENVELOPE_FWHM_M,
    AlgoBase,
    AlgoConfigBase,
    Controller,
)
from acconeer.exptool.a121.algo._utils import get_distances_m
from acconeer.exptool.a121.algo.parking._processors import (
    ObstructionProcessor,
    ObstructionProcessorConfig,
    Processor,
    ProcessorConfig,
)


opser.register_json_presentable(a121.SensorConfig)


class DetailedStatus(enum.Enum):
    OK = enum.auto()
    CALIBRATION_MISSING = enum.auto()
    CONFIG_MISMATCH = enum.auto()
    OBSTRUCTION_CALIBRATION_MISSING = enum.auto()


@attrs.frozen(kw_only=True)
class RefAppStatus:
    ref_app_state: DetailedStatus
    ready_to_start: bool


@attrs.mutable(kw_only=True)
class RefAppContext(AlgoBase):
    noise_level: float = attrs.field(default=1.0)
    obstruction_center: npt.NDArray[np.float_] = attrs.field(default=np.array([0.0, 0.0]))
    calibration_temperature: float = attrs.field(default=0.0)
    calibration_done: bool = attrs.field(default=False)
    calibration_sensor_config: a121.SensorConfig = attrs.field(default=a121.SensorConfig())
    obstruction_calibration_done: bool = attrs.field(default=False)
    obstruction_noise_level: float = attrs.field(default=0.0)
    obstruction_sensor_config: a121.SensorConfig = attrs.field(default=a121.SensorConfig())


@attributes_doc
@attrs.mutable(kw_only=True)
class RefAppConfig(AlgoConfigBase):
    range_start_m: float = attrs.field(default=0.3)
    """Start of measurement range (m)."""

    range_end_m: float = attrs.field(default=1.5)
    """End of measurement range (m)."""

    hwaas: int = attrs.field(default=32)
    """HWAAS."""

    profile: a121.Profile = attrs.field(default=a121.Profile.PROFILE_2, converter=a121.Profile)
    """Profile."""

    update_rate: float = attrs.field(default=10.0)
    """Frame rate."""

    queue_length_n: int = attrs.field(default=5)
    """Number of consecutive samples stored."""

    amplitude_threshold: float = attrs.field(default=15.0)
    """Threshold level in times the noise level to trigger."""

    weighted_distance_threshold_m: float = attrs.field(default=0.1)
    """Max distance between two signatures to consider samples similar."""

    signature_similarity_threshold: Optional[float] = attrs.field(default=60.0)
    """How large fraction of signatures have to be within distance threshold to detect car."""

    obstruction_detection: bool = attrs.field(default=False)
    """If obstruction detection should be active. This costs some extra battery power."""

    obstruction_distance_threshold: float = attrs.field(default=0.06)
    """Distance in similarity space of obstruction signature to consider sensor obstructed."""

    obstruction_start_m: float = attrs.field(default=0.03)
    """Start of obstruction detection range."""

    obstruction_end_m: float = attrs.field(default=0.05)
    """End of obstruction detection range."""

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> RefAppConfig:
        return cls(**d)

    def _collect_validation_results(self) -> list[a121.ValidationResult]:
        validation_results: list[a121.ValidationResult] = []
        fwhm = ENVELOPE_FWHM_M[self.profile]

        if self.range_start_m < 2 * fwhm:
            validation_results.append(
                a121.ValidationError(
                    self,
                    "range_start_m",
                    "Start point inside direct leakage",
                )
            )

        if self.range_end_m < self.range_start_m:
            validation_results.append(
                a121.ValidationError(
                    self,
                    "range_end_m",
                    "End point must be greater than start point",
                )
            )

        if self.range_end_m > 5.0:
            validation_results.append(
                a121.ValidationError(
                    self,
                    "range_end_m",
                    "End point must be within 5m, see documentation for details.",
                )
            )
        return validation_results


@attrs.frozen(kw_only=True)
class RefAppExtraResult:
    signature_history: npt.NDArray[np.float_] = attrs.field()
    """Array containing queue_length_n last signatures."""

    parking_data: npt.NDArray[np.float_] = attrs.field()
    """The scaled amplitude array used to calculate the last signature."""

    closest_object_dist: float = attrs.field(default=0.0)
    """Location of closest signature in cluster. Only availible if car is detected."""

    obstruction_data: Optional[npt.NDArray[np.float_]] = attrs.field(default=None)
    """Array with obstruction amplitudes (usually direct leakage)."""

    obstruction_signature: npt.NDArray[np.float_] = attrs.field(default=(0.0, 0.0))
    """Signature of amplitudes used for the obstruction detection."""

    obstruction_center: npt.NDArray[np.float_] = attrs.field(default=(0.0, 0.0))
    """Signature of amplitudes used in calibration."""

    obstruction_distance: float = attrs.field(default=0.0)
    """Obstruction distance threshold, same as in configuration."""


@attrs.frozen(kw_only=True)
class RefAppResult:
    car_detected: bool = attrs.field(default=False)
    """Boolean indicating if a car is present."""

    obstruction_detected: bool = attrs.field(default=False)
    """Boolean indicating whether something is obstructing the sensor."""

    extra_result: RefAppExtraResult = attrs.field()
    """Extra information for plotting."""


class RefApp(Controller[RefAppConfig, RefAppResult]):
    def __init__(
        self,
        *,
        client: a121.Client,
        sensor_id: int,
        ref_app_config: RefAppConfig,
        context: RefAppContext = RefAppContext(),
    ) -> None:
        super().__init__(client=client, config=ref_app_config)

        self.all_sensor_configs = get_sensor_configs(ref_app_config)
        self.sensor_config = self.all_sensor_configs["full_config"]
        self.sensor_id = sensor_id
        self.n_samples_to_calibrate = 3  # number of samples used for calibration.

        groups = [{sensor_id: self.sensor_config}]
        if ref_app_config.obstruction_detection:
            self.obstruction_config = self.all_sensor_configs["obstruction_config"]
            groups.append({sensor_id: self.obstruction_config})
        self.session_config = a121.SessionConfig(groups, update_rate=ref_app_config.update_rate)

        if ref_app_config.signature_similarity_threshold is not None:
            # input is a percentage, divide to get useful value
            signature_similarity_threshold = ref_app_config.signature_similarity_threshold / 100.0
        else:
            signature_similarity_threshold = 0.6

        self.processor_config = ProcessorConfig(
            queue_length=ref_app_config.queue_length_n,
            amplitude_threshold=ref_app_config.amplitude_threshold,
            weighted_distance_threshold_m=ref_app_config.weighted_distance_threshold_m,
            signature_similarity_threshold=signature_similarity_threshold,
        )
        self.ref_app_config = ref_app_config
        self.sensor_id = sensor_id

        self.context = context

        self.noise_level = self.context.noise_level  # noise level estimated at calibration
        self.calibration_temperature = self.context.calibration_temperature

        if ref_app_config.obstruction_detection:
            self.obstruction_center = self.context.obstruction_center
            self.obstruction_noise_level = self.context.obstruction_noise_level

        self.calibration_done = False
        self.started = False

    def start(
        self,
        recorder: Optional[a121.Recorder] = None,
        algo_group: Optional[h5py.Group] = None,
    ) -> None:
        if self.started:
            raise RuntimeError("Already started")

        self.all_metadata = self.client.setup_session(self.session_config)

        if self.ref_app_config.obstruction_detection:
            assert isinstance(self.all_metadata, list)
            self.metadata = self.all_metadata[0][self.sensor_id]
            self.obs_metadata = self.all_metadata[1][self.sensor_id]
        else:
            assert isinstance(self.all_metadata, a121.Metadata)
            self.metadata = self.all_metadata

        if recorder is not None:
            if isinstance(recorder, a121.H5Recorder):
                if algo_group is None:
                    algo_group = recorder.require_algo_group("parking")
                _record_algo_data(
                    algo_group,
                    self.sensor_id,
                    self.config,
                    self.context,
                )
            else:
                # Should never happen as we currently only have the H5Recorder
                warnings.warn("Will not save algo data")

            self.client.attach_recorder(recorder)

        base_sensor_config = self.all_sensor_configs["full_config"]

        self.base_processor = Processor(
            sensor_config=base_sensor_config,
            processor_config=self.processor_config,
            metadata=self.metadata,
            noise_estimate=self.noise_level,
            noise_estimate_temperature=self.calibration_temperature,
        )

        if self.ref_app_config.obstruction_detection:
            obstruction_sensor_config = self.all_sensor_configs["obstruction_config"]
            obstruction_distance_threshold = self.ref_app_config.obstruction_distance_threshold
            obstruction_processor_config = ObstructionProcessorConfig(
                distance_threshold=obstruction_distance_threshold
            )
            self.obs_distances = get_distances_m(obstruction_sensor_config, self.obs_metadata)

            self.obstruction_processor = ObstructionProcessor(
                sensor_config=obstruction_sensor_config,
                processor_config=obstruction_processor_config,
                metadata=self.metadata,
                update_rate=self.ref_app_config.update_rate,
                calibration_center=self.obstruction_center,
                calibration_noise_mean=self.obstruction_noise_level,
                calibration_temperature=self.calibration_temperature,
            )

        self.client.start_session()

        self.started = True

    def calibrate_ref_app(self) -> None:
        obstruction_detection = self.ref_app_config.obstruction_detection

        temp_config = copy.deepcopy(self.ref_app_config)
        sensor_configs = get_sensor_configs(temp_config)
        sensor_config = sensor_configs["full_config"]

        sensor_config.enable_tx = False

        if obstruction_detection:
            # We need two calibration values, one to determine the signature and one to determine the noise level.
            obstruction_config = sensor_configs["obstruction_config"]
            obstruction_config_tx_off = copy.deepcopy(obstruction_config)
            obstruction_config_tx_off.enable_tx = False
            assert isinstance(obstruction_config, a121.SensorConfig)
            groups = [
                {self.sensor_id: sensor_config},
                {self.sensor_id: obstruction_config},
                {self.sensor_id: obstruction_config_tx_off},
            ]
            session_config = a121.SessionConfig(groups, update_rate=self.n_samples_to_calibrate)
        else:
            session_config = a121.SessionConfig(
                {self.sensor_id: sensor_config}, update_rate=self.n_samples_to_calibrate
            )

        metadata = self.client.setup_session(session_config)

        if obstruction_detection:
            assert isinstance(metadata, list)
            obs_metadata = metadata[1][self.sensor_id]
            obs_distances = get_distances_m(obstruction_config, obs_metadata)

        noise_levels = []
        obs_noise_levels = []
        signatures = []
        temperatures = []

        self.client.start_session()
        for i in range(self.n_samples_to_calibrate):
            main_result = self.client.get_next()
            if obstruction_detection:
                assert isinstance(main_result, list)
                result = main_result[0][self.sensor_id]
                obs_result = main_result[1][self.sensor_id]
                obs_tx_off_result = main_result[2][self.sensor_id]
                noise_level = ObstructionProcessor.get_noise_level(obs_tx_off_result.frame)
                obs_noise_levels.append(noise_level)
                signature, _ = ObstructionProcessor.get_signature(
                    obs_result.frame, noise_level, obs_distances
                )
                signatures.append(signature)
            else:
                assert isinstance(main_result, a121.Result)
                result = main_result

            temperature = result.temperature
            temperatures.append(temperature)

            noise_frame = result.frame
            noise_level = Processor.process_noise_frame(noise_frame)
            noise_levels.append(noise_level)

        if obstruction_detection:
            self.obstruction_center = np.mean(signatures, axis=0)
            self.context.obstruction_noise_level = float(np.mean(obs_noise_levels))
            self.context.obstruction_center = self.obstruction_center
            self.context.obstruction_calibration_done = True
            self.context.obstruction_sensor_config = obstruction_config
        else:
            self.context.obstruction_calibration_done = False

        self.client.stop_session()

        self.calibration_temperature = float(np.median(temperatures))
        self.noise_level = float(np.mean(noise_levels))

        # Update the context
        sensor_config.enable_tx = True
        self.context.noise_level = self.noise_level
        self.context.calibration_temperature = self.calibration_temperature
        self.context.calibration_sensor_config = sensor_config
        self.context.calibration_done = True

    def get_next(self) -> RefAppResult:
        if not self.started:
            raise RuntimeError("Not started")

        result = self.client.get_next()

        if self.ref_app_config.obstruction_detection:
            assert isinstance(result, list)
            base_res = result[0][self.sensor_id]
            obs_res = result[1][self.sensor_id]
        else:
            assert isinstance(result, a121.Result)
            base_res = result

        processor_result = self.base_processor.process(base_res)

        if self.ref_app_config.obstruction_detection:
            obstruction_result = self.obstruction_processor.process(obs_res)

            obstruction_found = obstruction_result.obstruction_found

            extra_result = RefAppExtraResult(
                signature_history=processor_result.extra_result.signature_history,
                parking_data=processor_result.extra_result.parking_data,
                closest_object_dist=processor_result.extra_result.closest_observation,
                obstruction_data=obstruction_result.extra_result.obstruction_data,
                obstruction_signature=obstruction_result.extra_result.obstruction_signature,
                obstruction_center=obstruction_result.extra_result.obstruction_center,
                obstruction_distance=obstruction_result.extra_result.obstruction_distance,
            )
        else:
            obstruction_found = False
            extra_result = RefAppExtraResult(
                signature_history=processor_result.extra_result.signature_history,
                parking_data=processor_result.extra_result.parking_data,
                closest_object_dist=processor_result.extra_result.closest_observation,
            )

        ref_app_result = RefAppResult(
            car_detected=processor_result.car_detected,
            obstruction_detected=obstruction_found,
            extra_result=extra_result,
        )

        return ref_app_result

    def stop(self) -> Any:
        if not self.started:
            raise RuntimeError("Already stopped")

        self.client.stop_session()
        recorder = self.client.detach_recorder()
        if recorder is None:
            recorder_result = None
        else:
            recorder_result = recorder.close()

        self.started = False

        return recorder_result

    @classmethod
    def get_ref_app_status(
        cls, ref_app_config: RefAppConfig, context: RefAppContext
    ) -> RefAppStatus:
        calibration_done = context.calibration_done

        sensor_settings = get_sensor_configs(ref_app_config)
        sensor_conf = sensor_settings["full_config"]

        config_match = context.calibration_sensor_config == sensor_conf

        if ref_app_config.obstruction_detection:
            obstruction_conf = sensor_settings["obstruction_config"]
            obstruction_config_match = obstruction_conf == context.obstruction_sensor_config
            obstruction_ready = context.obstruction_calibration_done and obstruction_config_match
        else:
            obstruction_ready = True

        if not calibration_done:
            ret = RefAppStatus(
                ready_to_start=False,
                ref_app_state=DetailedStatus.CALIBRATION_MISSING,
            )
        elif not config_match:
            ret = RefAppStatus(
                ready_to_start=False,
                ref_app_state=DetailedStatus.CONFIG_MISMATCH,
            )
        elif not obstruction_ready:
            ret = RefAppStatus(
                ready_to_start=False,
                ref_app_state=DetailedStatus.OBSTRUCTION_CALIBRATION_MISSING,
            )
        else:
            ret = RefAppStatus(ready_to_start=True, ref_app_state=DetailedStatus.OK)

        return ret


def _record_algo_data(
    algo_group: h5py.Group,
    sensor_id: int,
    ref_app_config: RefAppConfig,
    context: RefAppContext,
) -> None:
    algo_group.create_dataset(
        "ref_app_sensor_id",
        data=sensor_id,
        track_times=False,
    )
    _create_h5_string_dataset(algo_group, "ref_app_config", ref_app_config.to_json())

    context_group = algo_group.create_group("context")
    opser.serialize(context, context_group)


def _load_algo_data(algo_group: h5py.Group) -> Tuple[int, RefAppConfig, RefAppContext]:
    sensor_id = int(algo_group["ref_app_sensor_id"][()])

    config = RefAppConfig.from_json(algo_group["ref_app_config"][()])

    context_group = algo_group["context"]
    context = opser.deserialize(context_group, RefAppContext)

    return sensor_id, config, context


def get_obstruction_sensor_config(ref_app_config: RefAppConfig) -> a121.SensorConfig:
    step_length = 2  # Typically not very important, we just want a few points close to the sensor.

    start_point = int(round(ref_app_config.obstruction_start_m / APPROX_BASE_STEP_LENGTH_M))
    num_points = int(
        round(
            np.ceil(
                (ref_app_config.obstruction_end_m - ref_app_config.obstruction_start_m)
                / (step_length * APPROX_BASE_STEP_LENGTH_M)
            )
        )
    )
    conf_obstruction = a121.SensorConfig(
        start_point=start_point,
        num_points=num_points,
        step_length=step_length,
        profile=a121.Profile.PROFILE_1,
        hwaas=16,
        sweeps_per_frame=1,
    )
    return conf_obstruction


def get_sensor_configs(ref_app_config: RefAppConfig) -> Dict[str, a121.SensorConfig]:
    start_point = int(round(ref_app_config.range_start_m / APPROX_BASE_STEP_LENGTH_M))
    profile = a121.Profile(ref_app_config.profile)

    fwhm = ENVELOPE_FWHM_M[profile]

    step_length_ideal = int(round((fwhm / APPROX_BASE_STEP_LENGTH_M)))
    if step_length_ideal >= 24:
        step_length = int(np.floor(step_length_ideal / 24) * 24)
    else:
        step_length = step_length_ideal
        while step_length > 2 and 24 % step_length != 0:
            step_length -= 1
    hwaas = ref_app_config.hwaas
    num_points = int(
        round(
            np.ceil(
                (ref_app_config.range_end_m - ref_app_config.range_start_m)
                / (step_length * APPROX_BASE_STEP_LENGTH_M)
            )
        )
    )

    subsweeps = []
    conf_base = a121.SubsweepConfig(
        start_point=start_point,
        num_points=num_points,
        step_length=step_length,
        profile=profile,
        enable_tx=True,
        hwaas=hwaas,
    )

    ret = {}
    ret["base_config"] = a121.SensorConfig(subsweeps=[conf_base])

    subsweeps.append(conf_base)

    if ref_app_config.obstruction_detection:
        conf_obstruction = get_obstruction_sensor_config(ref_app_config)
        ret["obstruction_config"] = conf_obstruction

    conf = a121.SensorConfig(subsweeps=subsweeps, sweeps_per_frame=1)
    ret["full_config"] = conf

    return ret
