# Copyright (c) Acconeer AB, 2024
# All rights reserved

from __future__ import annotations

import warnings
from typing import Any, Optional, Tuple

import attrs
import h5py
import numpy as np
import numpy.typing as npt
from attributes_doc import attributes_doc

from acconeer.exptool import a121
from acconeer.exptool._core.class_creation.attrs import (
    attrs_ndarray_isclose,
    attrs_optional_ndarray_isclose,
)
from acconeer.exptool.a121._core.entities.configs.config_enums import IdleState, Profile
from acconeer.exptool.a121._h5_utils import _create_h5_string_dataset
from acconeer.exptool.a121.algo import (
    AlgoConfigBase,
    Controller,
    select_prf,
)
from acconeer.exptool.utils import is_power_of_2

from ._processor import Processor, ProcessorConfig, ProcessorExtraResult, ReportedDisplacement


def optional_profile_converter(profile: Optional[Profile]) -> Optional[Profile]:
    if profile is None:
        return None

    return Profile(profile)


def idle_state_converter(idle_state: IdleState) -> IdleState:
    return IdleState(idle_state)


@attributes_doc
@attrs.mutable(kw_only=True)
class ExampleAppConfig(AlgoConfigBase):
    measured_point: int = attrs.field(default=80)
    """Measured point."""

    time_series_length: int = attrs.field(default=1024)
    """Length of time series.
    This value will be overridden by the number of sweeps per frame if continuous sweep mode is not enabled."""

    lp_coeff: float = attrs.field(default=0.95)
    """Specify filter coefficient of the exponential filter for the FFT.
    A higher value means more filtering, i.e., slower response to changes."""

    threshold_margin: float = attrs.field(default=10.0)
    """Specify threshold margin (micrometer)."""

    amplitude_threshold: float = attrs.field(default=100.0)
    """Specify minimum amplitude for calculating vibration."""

    reported_displacement_mode: ReportedDisplacement = attrs.field(
        default=ReportedDisplacement.AMPLITUDE,
        converter=ReportedDisplacement,
    )
    """Selects whether to report the amplitude or peak to peak of the estimated frequency."""

    low_frequency_enhancement: bool = attrs.field(default=False)
    """Adds a loopback subsweep for phase correction to enhance low frequency detection."""

    profile: a121.Profile = attrs.field(default=a121.Profile.PROFILE_3, converter=a121.Profile)
    """Sets the profile."""

    frame_rate: Optional[float] = attrs.field(default=None)
    """Frame rate in Hz."""

    sweep_rate: float = attrs.field(default=3000)
    """Sweep rate in Hz."""

    sweeps_per_frame: int = attrs.field(default=128)
    """Number of sweeps per frame."""

    hwaas: int = attrs.field(default=16)
    """Number of HWAAS."""

    double_buffering: bool = attrs.field(default=True)
    """Enables double buffering."""

    continuous_sweep_mode: bool = attrs.field(default=True)
    """Enables continuous sweep mode."""

    inter_frame_idle_state: a121.IdleState = attrs.field(
        default=a121.IdleState.READY, converter=idle_state_converter
    )
    """Sets the inter frame idle state."""

    inter_sweep_idle_state: a121.IdleState = attrs.field(
        default=a121.IdleState.READY, converter=idle_state_converter
    )
    """Sets the inter sweep idle state."""

    def _collect_validation_results(self) -> list[a121.ValidationResult]:
        validation_results: list[a121.ValidationResult] = []

        if not is_power_of_2(self.time_series_length):
            validation_results.append(
                a121.ValidationWarning(
                    self,
                    "time_series_length",
                    "Should be power of 2 for efficient usage of fast fourier transform",
                )
            )

        if self.sweep_rate is None:
            validation_results.append(
                a121.ValidationError(
                    self,
                    "sweep_rate",
                    "Must be set",
                )
            )

        if self.continuous_sweep_mode and not self.double_buffering:
            validation_results.append(
                a121.ValidationError(
                    self,
                    "continuous_sweep_mode",
                    "Continuous sweep mode requires double buffering to be enabled",
                )
            )

        return validation_results


@attrs.frozen(kw_only=True)
class ExampleAppResult:
    max_sweep_amplitude: float
    """Max amplitude in sweep.

    Used to determine whether an object is in front of the sensor.
    """

    lp_displacements: Optional[npt.NDArray[np.float64]] = attrs.field(
        default=None, eq=attrs_optional_ndarray_isclose
    )
    """Array of estimated displacement (μm) per frequency."""

    lp_displacements_freqs: npt.NDArray[np.float64] = attrs.field(eq=attrs_ndarray_isclose)
    """Array of frequencies where displacement is estimated (Hz)."""

    max_displacement: Optional[float] = attrs.field(default=None)
    """Largest detected displacement (μm)."""

    max_displacement_freq: Optional[float] = attrs.field(default=None)
    """Frequency of largest detected displacement (Hz)."""

    time_series_std: Optional[float] = attrs.field(default=None)
    """Time series standard deviation."""

    processor_extra_result: ProcessorExtraResult = attrs.field()
    """Processor extra result, used for plotting only."""

    service_result: a121.Result = attrs.field()


class ExampleApp(Controller[ExampleAppConfig, ExampleAppResult]):
    def __init__(
        self,
        *,
        client: a121.Client,
        sensor_id: int,
        example_app_config: ExampleAppConfig,
    ) -> None:
        super().__init__(client=client, config=example_app_config)
        self.sensor_id = sensor_id

        self.started = False

    def start(
        self, recorder: Optional[a121.Recorder] = None, _algo_group: Optional[h5py.Group] = None
    ) -> None:
        if self.started:
            msg = "Already started"
            raise RuntimeError(msg)

        sensor_config = self._get_sensor_config(self.config)
        self.session_config = a121.SessionConfig(
            {self.sensor_id: sensor_config},
            extended=False,
        )

        metadata = self.client.setup_session(self.session_config)
        assert isinstance(metadata, a121.Metadata)

        processor_config = self._get_processor_config(self.config)

        self.processor = Processor(
            sensor_config=sensor_config,
            metadata=metadata,
            processor_config=processor_config,
            context=None,
        )

        if recorder is not None:
            if isinstance(recorder, a121.H5Recorder):
                if _algo_group is None:
                    _algo_group = recorder.require_algo_group("vibration")
                _record_algo_data(
                    _algo_group,
                    self.sensor_id,
                    self.config,
                )
            else:
                # Should never happen as we currently only have the H5Recorder
                warnings.warn("Will not save algo data")

            self.client.attach_recorder(recorder)

        self.client.start_session()

        self.started = True

    @classmethod
    def _get_sensor_config(cls, config: ExampleAppConfig) -> a121.SensorConfig:
        measure_config = a121.SubsweepConfig(
            start_point=config.measured_point,
            num_points=1,
            profile=config.profile,
            hwaas=config.hwaas,
            prf=select_prf(config.measured_point, config.profile),
            receiver_gain=10,
        )

        if config.low_frequency_enhancement:
            loopback_config = a121.SubsweepConfig(
                profile=a121.Profile.PROFILE_5,
                enable_loopback=True,
                hwaas=8,
                start_point=0,
                num_points=1,
                prf=select_prf(0, config.profile),
                receiver_gain=10,
            )

            subsweeps = [measure_config, loopback_config]
        else:
            subsweeps = [measure_config]

        sensor_config = a121.SensorConfig(
            subsweeps=subsweeps,
            sweeps_per_frame=config.sweeps_per_frame,
            sweep_rate=config.sweep_rate,
            continuous_sweep_mode=config.continuous_sweep_mode,
            double_buffering=config.double_buffering,
            inter_frame_idle_state=config.inter_frame_idle_state,
            inter_sweep_idle_state=config.inter_sweep_idle_state,
        )

        return sensor_config

    @classmethod
    def _get_processor_config(cls, config: ExampleAppConfig) -> ProcessorConfig:
        return ProcessorConfig(
            time_series_length=config.time_series_length,
            lp_coeff=config.lp_coeff,
            threshold_margin=config.threshold_margin,
            amplitude_threshold=config.amplitude_threshold,
            low_frequency_enhancement=config.low_frequency_enhancement,
        )

    def get_next(self) -> ExampleAppResult:
        if not self.started:
            msg = "Not started"
            raise RuntimeError(msg)

        result = self.client.get_next()
        assert isinstance(result, a121.Result)

        assert self.processor is not None
        processor_result = self.processor.process(result)

        return ExampleAppResult(
            max_sweep_amplitude=processor_result.max_sweep_amplitude,
            lp_displacements=processor_result.lp_displacements,
            lp_displacements_freqs=processor_result.lp_displacements_freqs,
            max_displacement=processor_result.max_displacement,
            max_displacement_freq=processor_result.max_displacement_freq,
            time_series_std=processor_result.time_series_std,
            processor_extra_result=processor_result.extra_result,
            service_result=result,
        )

    def update_config(self, config: ExampleAppConfig) -> None:
        raise NotImplementedError

    def stop(self) -> Any:
        if not self.started:
            msg = "Already stopped"
            raise RuntimeError(msg)

        self.client.stop_session()
        recorder = self.client.detach_recorder()
        if recorder is None:
            recorder_result = None
        else:
            recorder_result = recorder.close()

        self.started = False

        return recorder_result


def _record_algo_data(
    algo_group: h5py.Group,
    sensor_id: int,
    config: ExampleAppConfig,
) -> None:
    algo_group.create_dataset(
        "sensor_id",
        data=sensor_id,
        track_times=False,
    )
    _create_h5_string_dataset(algo_group, "example_app_config", config.to_json())


def _load_algo_data(algo_group: h5py.Group) -> Tuple[int, ExampleAppConfig]:
    sensor_id = algo_group["sensor_id"][()]
    config = ExampleAppConfig.from_json(algo_group["example_app_config"][()])
    return sensor_id, config
