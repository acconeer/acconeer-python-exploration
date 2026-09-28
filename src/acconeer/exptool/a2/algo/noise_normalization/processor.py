# Copyright (c) Acconeer AB, 2025-2026
# All rights reserved

from __future__ import annotations

import copy
import typing as t

import attrs
import h5py
import numpy as np
import typing_extensions as te
from numpy import typing as npt

import acconeer.exptool.type_migration as tm
from acconeer.exptool import a2, opser
from acconeer.exptool.a2._core import channel_convention as ch_conv
from acconeer.exptool.a2._core.entities.containers.result import (
    _GroupResult_v0,
    _GroupResult_v1,
    _GroupResult_v2,
    group_result_timeline,
)


NUM_RX = 4

NOISE_NORMALIZATION_GROUP_NAME = "_noise_normalization_group"

"""
Contains functionality for creation and application of NoiseNormalization
A NoiseNormalizationRecording is a recording of a number of samples
that gives an indication of the noise level of the sensor.

The NoiseNormalizationResultProcessor provides functionality to apply the normalization to a a2.Result.
This should provide a more uniform result among different sensor individuals.
In addition, applying the normalization in combination with dynamic HWAAS will give a more uniform SnR over distances.
This allows for a flat threshold to be applied either directly to the data or a heatmap.
"""

_A2ResultType = t.TypeVar("_A2ResultType", a2.Result, a2.GroupResult)

N_WANTED_SAMPLES = 900
NUM_SWEEPS = 3


@attrs.frozen
class NoiseNormalizationRecording:
    group_results: list[a2.GroupResult]
    """ The sensor data in the recording."""
    noise_values: list[npt.NDArray[np.float64]]
    """ Noise data to be applied by the processor."""
    noise_config: a2.SessionConfig
    """ A2 config used to record the noise data."""

    @staticmethod
    def _calc_noise_values(
        noise_frames: npt.NDArray[t.Any],
        subsweep_config: a2.SubsweepConfig,
    ) -> npt.NDArray[np.float64]:
        num_channels = subsweep_config.num_channels

        scale_values = np.repeat(subsweep_config.hwaas_points, num_channels)

        used_channels = ch_conv.get_tx_major_channel_numbers(
            tx_mask=subsweep_config.tx_antenna_mask,
            rx_mask=subsweep_config.rx_antenna_mask,
        )
        rx_groups: list[list[int]] = [[] for _ in range(NUM_RX)]
        for ch_ind, ch in enumerate(used_channels):
            (_, rx) = used_channels[ch]
            rx_groups[rx].append(ch_ind)

        frame_by_channel = np.reshape(noise_frames, (-1, num_channels))
        noise_value_by_channel = np.zeros(num_channels)
        for rx_ind in range(NUM_RX):
            if (1 << rx_ind) & subsweep_config.rx_antenna_mask:
                ch_inds = rx_groups[rx_ind]
                noise_value_by_channel[ch_inds] = np.std(frame_by_channel[:, ch_inds])
        noise_values = np.tile(noise_value_by_channel, subsweep_config.num_points)
        noise_values = noise_values / np.sqrt(scale_values)

        return noise_values

    @classmethod
    def create(cls, client: a2.Client, session_config: a2.SessionConfig) -> te.Self:
        if client is None:
            raise RuntimeError
        if not client.connected:
            raise RuntimeError

        min_tx_count = min(
            bin(subsweep_config.tx_antenna_mask).count("1")
            for sensor_config in session_config.sensor_configs
            for subsweep_config in sensor_config.subsweeps
        )
        n_samples = int(np.ceil(N_WANTED_SAMPLES / (min_tx_count * NUM_SWEEPS)))

        # Build expanded noise session: one sensor config per (sensor_config, subsweep) pair.
        # Keeps each noise sensor config to a single subsweep with high num_points,
        # avoiding chip buffer exhaustion when the original config has many subsweeps.
        noise_sensor_configs: list[a2.SensorConfig] = []
        noise_mapping: list[tuple[int, int]] = []  # (original_sensor_config_idx, subsweep_idx)

        for sensor_idx, sensor_config in enumerate(session_config.sensor_configs):
            for subsweep_idx, subsweep_config in enumerate(sensor_config.subsweeps):
                noise_subsweep_config = copy.deepcopy(subsweep_config)
                noise_subsweep_config.enable_tx = False
                noise_subsweep_config.hwaas_exponent = 0
                noise_subsweep_config.hwaas_max = 1
                noise_subsweep_config.hwaas_min = 1
                noise_subsweep_config.num_points = n_samples

                noise_sensor_config = copy.deepcopy(sensor_config)
                noise_sensor_config.subsweeps = [noise_subsweep_config]
                noise_sensor_config.sweeps_per_frame = NUM_SWEEPS
                noise_sensor_config.sweep_rate = None
                noise_sensor_config.frame_rate = None

                noise_sensor_configs.append(noise_sensor_config)
                noise_mapping.append((sensor_idx, subsweep_idx))

        noise_config = copy.deepcopy(session_config)
        noise_config.update_rate = None
        noise_config.sensor_configs = noise_sensor_configs

        client.setup_session(noise_config)
        client.start_session()

        group_result = client.get_next(format=a2.Client.ResultFormat.FULL)
        frames = [result.frame for result in group_result.results]
        client.stop_session()

        num_original_sensor_configs = len(session_config.sensor_configs)
        subsweep_noise: list[list[npt.NDArray[np.float64]]] = [
            [] for _ in range(num_original_sensor_configs)
        ]

        for noise_idx, (sensor_idx, subsweep_idx) in enumerate(noise_mapping):
            original_subsweep = session_config.sensor_configs[sensor_idx].subsweeps[subsweep_idx]
            noise_values = cls._calc_noise_values(frames[noise_idx], original_subsweep)
            subsweep_noise[sensor_idx].append(noise_values)

        group_noise = [np.concatenate(per_subsweep) for per_subsweep in subsweep_noise]

        return cls(
            group_results=[group_result],
            noise_values=group_noise,
            noise_config=session_config,
        )


class NoiseNormalizationResultProcessor:
    """
    Noise normalization functionality.
    Applies a noise normalization to the frame and modifies it.
    The noise can be either recorded or model based.
    """

    def __init__(
        self,
        session_config: a2.SessionConfig,
        noise_recording: NoiseNormalizationRecording,
    ) -> None:
        self.sensor_configs = session_config.sensor_configs
        self.noise_recording = noise_recording

    @staticmethod
    def normalize_frame(
        frame: npt.NDArray[np.complex128], noise: npt.NDArray[np.float64]
    ) -> npt.NDArray[np.complex128]:
        return frame / noise

    def get_result(self, result: a2.Result, noise: npt.NDArray[np.float64]) -> a2.Result:
        return attrs.evolve(result, frame=self.normalize_frame(result.frame, noise))

    def process_recorded(
        self,
        result: a2.Result,
        noise_values: npt.NDArray[np.float64],
    ) -> a2.Result:
        assert self.noise_recording is not None

        return self.get_result(result, noise_values)

    def process_result(self, result: a2.Result) -> a2.Result:
        return self.process_recorded(result, self.noise_recording.noise_values[0])

    def process_group_result(self, group_result: a2.GroupResult) -> a2.GroupResult:
        group_list = []
        for i, result in enumerate(group_result.results):
            noise = self.noise_recording.noise_values[i]
            group_list.append(self.process_recorded(result, noise))
        return a2.GroupResult(results=group_list)

    def process(self, result: _A2ResultType) -> _A2ResultType:
        if isinstance(result, a2.Result):
            return self.process_result(result)
        else:
            return self.process_group_result(result)


@attrs.frozen
class _NoiseNormalizationRecording_v0:
    group_results: list[_GroupResult_v0]
    noise_values: list[npt.NDArray[np.float64]]
    noise_config: a2.SessionConfig
    noise_temperature: int


@attrs.frozen
class NoiseNormalizationRecording_v1:
    group_results: list[_GroupResult_v1]
    noise_values: list[npt.NDArray[np.float64]]
    noise_config: a2.SessionConfig
    noise_temperature: int


@attrs.frozen
class NoiseNormalizationRecording_v2:
    group_results: list[_GroupResult_v2]
    noise_values: list[npt.NDArray[np.float64]]
    noise_config: a2.SessionConfig


def save_noise_normalization_recording(
    group: h5py.Group, noise_normalization_recording: NoiseNormalizationRecording | None
) -> None:
    """
    Provides saving functionality between plugins.
    """
    if noise_normalization_recording is not None:
        noise_group = group.create_group(NOISE_NORMALIZATION_GROUP_NAME)
        opser.serialize(noise_normalization_recording, noise_group)


def load_noise_normalization_recording(
    group: h5py.Group,
) -> NoiseNormalizationRecording | None:
    """
    Provides loading functionality between plugins.
    """
    noise_group = group.get(NOISE_NORMALIZATION_GROUP_NAME, None)
    if noise_group is not None:
        noise_normalization_recording = noise_normalization_recording_timeline.migrate(noise_group)
        return noise_normalization_recording
    return None


noise_normalization_recording_timeline = (
    tm.start(_NoiseNormalizationRecording_v0)
    .load(
        h5py.Group,
        lambda g: opser.deserialize(g, _NoiseNormalizationRecording_v0),
        fail=[opser.LoadError],
    )
    .nop()
    .epoch(
        NoiseNormalizationRecording_v1,
        lambda old: NoiseNormalizationRecording_v1(
            group_results=[
                group_result_timeline.migrate(group_result, target_type=_GroupResult_v1)
                for group_result in old.group_results
            ],
            noise_values=old.noise_values,
            noise_config=old.noise_config,
            noise_temperature=old.noise_temperature,
        ),
        fail=[tm.MigrationError],
    )
    .load(
        h5py.Group,
        lambda g: opser.deserialize(g, NoiseNormalizationRecording_v1),
        fail=[opser.LoadError],
    )
    .nop()
    .epoch(
        NoiseNormalizationRecording_v2,
        lambda old: NoiseNormalizationRecording_v2(
            group_results=[
                group_result_timeline.migrate(group_result, target_type=_GroupResult_v2)
                for group_result in old.group_results
            ],
            noise_values=old.noise_values,
            noise_config=old.noise_config,
            # ignore noise temperature
        ),
        fail=[tm.MigrationError],
    )
    .load(
        h5py.Group,
        lambda g: opser.deserialize(g, NoiseNormalizationRecording_v2),
        fail=[opser.LoadError],
    )
    .nop()
    .epoch(
        NoiseNormalizationRecording,
        lambda old: NoiseNormalizationRecording(
            group_results=[
                group_result_timeline.migrate(group_result, target_type=a2.GroupResult)
                for group_result in old.group_results
            ],
            noise_values=old.noise_values,
            noise_config=old.noise_config,
        ),
        fail=[tm.MigrationError],
    )
    .load(
        h5py.Group,
        lambda g: opser.deserialize(g, NoiseNormalizationRecording),
        fail=[opser.LoadError],
    )
)
