# Copyright (c) Acconeer AB, 2022
# All rights reserved

from __future__ import annotations

import enum
from typing import Optional, Tuple

import attrs
import numpy as np
import numpy.typing as npt

from acconeer.exptool import a121
from acconeer.exptool.a121.algo import APPROX_BASE_STEP_LENGTH_M, ENVELOPE_FWHM_M, AlgoParamEnum
from acconeer.exptool.a121.algo.distance._processors import (
    MeasurementType,
    Processor,
    ProcessorConfig,
    ProcessorContext,
    ProcessorResult,
)


class PeakSortingMethod(AlgoParamEnum):
    """Peak sorting methods.
    ``CLOSEST`` sort according to distance.
    ``HIGHEST_RCS`` sort according to RCS."""

    CLOSEST = enum.auto()
    HIGHEST_RCS = enum.auto()


@attrs.frozen(kw_only=True)
class ProcessorSpec:
    processor_config: ProcessorConfig = attrs.field()
    group_index: int = attrs.field()
    subsweep_indexes: list[int] = attrs.field()
    processor_context: Optional[ProcessorContext] = attrs.field(default=None)


@attrs.mutable(kw_only=True)
class AggregatorConfig:
    peak_sorting_method: PeakSortingMethod = attrs.field(default=PeakSortingMethod.HIGHEST_RCS)


@attrs.frozen(kw_only=True)
class AggregatorResult:
    processor_results: list[ProcessorResult] = attrs.field()
    estimated_distances: npt.NDArray[np.float_] = attrs.field()
    estimated_rcs: npt.NDArray[np.float_] = attrs.field()
    service_extended_result: list[dict[int, a121.Result]] = attrs.field()


class Aggregator:
    """Aggregating class

    Instantiates Processor objects based configuration from Detector.

    Aggregates result, based on selected peak sorting strategy, from underlying Processor objects.
    """

    MIN_PEAK_DIST_M = 0.005

    RLG_PER_HWAAS_MAP = {
        a121.Profile.PROFILE_1: 11.3,
        a121.Profile.PROFILE_2: 13.7,
        a121.Profile.PROFILE_3: 19.0,
        a121.Profile.PROFILE_4: 20.5,
        a121.Profile.PROFILE_5: 21.6,
    }

    def __init__(
        self,
        session_config: a121.SessionConfig,
        extended_metadata: list[dict[int, a121.Metadata]],
        config: AggregatorConfig,
        specs: list[ProcessorSpec],
        sensor_id: int,
    ):
        self.config = config
        self.specs = specs
        self.sensor_id = sensor_id

        self.processors: list[Processor] = []

        for spec in specs:
            metadata = extended_metadata[spec.group_index][self.sensor_id]
            sensor_config = session_config.groups[spec.group_index][self.sensor_id]

            processor = Processor(
                sensor_config=sensor_config,
                metadata=metadata,
                processor_config=spec.processor_config,
                subsweep_indexes=spec.subsweep_indexes,
                context=spec.processor_context,
            )
            self.processors.append(processor)

    def process(self, extended_result: list[dict[int, a121.Result]]) -> AggregatorResult:
        processors_result = []
        ampls: npt.NDArray[np.float_] = np.array([])
        dists: npt.NDArray[np.float_] = np.array([])
        rcs: npt.NDArray[np.float_] = np.array([])

        for spec, processor in zip(self.specs, self.processors):
            processor_result = processor.process(extended_result[spec.group_index][self.sensor_id])
            processors_result.append(processor_result)
            if processor_result.estimated_distances is not None:
                assert spec.processor_context is not None
                assert spec.processor_context.bg_noise_std is not None
                ampls_from_processor = np.array(processor_result.estimated_amplitudes)
                dists_from_processor = np.array(processor_result.estimated_distances)

                if spec.processor_config.measurement_type == MeasurementType.CLOSE_RANGE:
                    # Close range measurements consist of two subsweeps(Loopback and distance
                    # measurement). Select the one corresponding to the distance measurement.
                    subsweep_configs = [
                        processor.sensor_config.subsweeps[Processor.CLOSE_RANGE_DIST_IDX]
                    ]
                elif spec.processor_config.measurement_type == MeasurementType.FAR_RANGE:
                    subsweep_slice = slice(spec.subsweep_indexes[0], spec.subsweep_indexes[-1] + 1)
                    subsweep_configs = processor.sensor_config.subsweeps[subsweep_slice]
                else:
                    raise RuntimeError("Invalid measurement type.")

                (
                    stds,
                    profiles,
                    hwaas,
                    step_lengths,
                ) = self._get_subsweep_info_at_estimated_distance(
                    subsweep_configs, dists_from_processor, spec.processor_context.bg_noise_std
                )

                rcs_from_processor = self._get_rcs_of_peaks(
                    ampls_from_processor,
                    stds,
                    hwaas,
                    dists_from_processor,
                    profiles,
                    step_lengths,
                )

                rcs = np.concatenate((rcs, rcs_from_processor))
                ampls = np.concatenate((ampls, ampls_from_processor))
                dists = np.concatenate((dists, dists_from_processor))
        (dists_merged, ampls_merged, rcs_merged) = self._merge_peaks(
            self.MIN_PEAK_DIST_M, dists, ampls, rcs
        )
        (dists_sorted, rcs_sorted) = self._sort_peaks(
            dists_merged, ampls_merged, rcs_merged, self.config.peak_sorting_method
        )

        return AggregatorResult(
            processor_results=processors_result,
            estimated_distances=dists_sorted,
            estimated_rcs=rcs_sorted,
            service_extended_result=extended_result,
        )

    def _get_subsweep_info_at_estimated_distance(
        self,
        subsweeps: list[a121.SubsweepConfig],
        distances: npt.NDArray[np.float_],
        bg_noise_std: list[float],
    ) -> Tuple[list[float], list[a121.Profile], list[int], list[int]]:
        """Extracts the subsweep parameters and the noise estimates corresponding to the
        location of the estimated distances"""

        start_points = [subsweep.start_point for subsweep in subsweeps]
        bpts_m = np.array(start_points) * APPROX_BASE_STEP_LENGTH_M

        stds = []
        hwaas = []
        profiles = []
        step_lengths = []
        for distance in distances:
            # Find subsweep index corresponding to subsweep containing estimated distance.
            subsweep_idx = np.sum(bpts_m < distance) - 1
            subsweep = subsweeps[subsweep_idx]
            stds.append(bg_noise_std[subsweep_idx])
            hwaas.append(subsweep.hwaas)
            profiles.append(subsweep.profile)
            step_lengths.append(subsweep.step_length)

        return (stds, profiles, hwaas, step_lengths)

    @staticmethod
    def _merge_peaks(
        min_peak_to_peak_dist: float,
        dists: npt.NDArray[np.float_],
        ampls: npt.NDArray[np.float_],
        rcs: npt.NDArray[np.float_],
    ) -> Tuple[npt.NDArray[np.float_], npt.NDArray[np.float_], npt.NDArray[np.float_]]:
        sorting_order = np.argsort(dists)
        distances_sorted = dists[sorting_order]
        amplitudes_sorted = ampls[sorting_order]
        rcs_sorted = rcs[sorting_order]

        peak_cluster_idxs = np.where(min_peak_to_peak_dist < np.diff(distances_sorted))[0] + 1
        distances_merged = [
            np.mean(cluster)
            for cluster in np.split(distances_sorted, peak_cluster_idxs)
            if dists.size != 0
        ]
        amplitudes_merged = [
            np.mean(cluster)
            for cluster in np.split(amplitudes_sorted, peak_cluster_idxs)
            if dists.size != 0
        ]
        rcs_merged = [
            np.mean(cluster)
            for cluster in np.split(rcs_sorted, peak_cluster_idxs)
            if dists.size != 0
        ]
        return (np.array(distances_merged), np.array(amplitudes_merged), np.array(rcs_merged))

    @staticmethod
    def _sort_peaks(
        dists: npt.NDArray[np.float_],
        ampls: npt.NDArray[np.float_],
        rcs: npt.NDArray[np.float_],
        method: PeakSortingMethod,
    ) -> Tuple[npt.NDArray[np.float_], npt.NDArray[np.float_]]:
        if method == PeakSortingMethod.CLOSEST:
            quantity_to_sort = dists
        elif method == PeakSortingMethod.HIGHEST_RCS:
            quantity_to_sort = -rcs
        else:
            raise ValueError("Unknown peak sorting method")
        return (
            np.array([dists[i] for i in quantity_to_sort.argsort()]),
            np.array([rcs[i] for i in quantity_to_sort.argsort()]),
        )

    @classmethod
    def _get_rcs_of_peaks(
        cls,
        amplitudes: npt.NDArray[np.float_],
        sigmas: list[float],
        hwaases: list[int],
        distances: npt.NDArray[np.float_],
        profiles: list[a121.Profile],
        step_lengths: list[int],
    ) -> npt.NDArray[np.float_]:
        """Prepares the inputs to the rcs calculation and map them to _calculate_rcs."""

        processing_gains_db = [
            10 * np.log10(cls.calc_processing_gain(profile, step_length))
            for (profile, step_length) in zip(profiles, step_lengths)
        ]
        s_db = 20 * np.log10(amplitudes)
        n_db = 20 * np.log10(sigmas)
        rlg_db = [
            cls.RLG_PER_HWAAS_MAP[profile] + 10 * np.log10(hwaas)
            for (profile, hwaas) in zip(profiles, hwaases)
        ]
        r_db = 40 * np.log10(distances)
        rcs = list(map(cls._calculate_rcs, s_db, n_db, rlg_db, r_db, processing_gains_db))
        return np.array(rcs)

    @staticmethod
    def _calculate_rcs(
        s_db: float, n_db: float, rlg_db: float, r_db: float, processing_gain_db: float
    ) -> float:

        """
        Calculate the RCS of a target based on the radar equation.

        SNR_dB = RLG_dB + RCS_dB - 40log(distance) + processnig_gain_db
        =>
        RCS_dB = SNR_dB - RLG_dB + 40log(distance) - processnig_gain_db

        RLG_dB = RLG_PER_HWAAS_MAP[profile] + 10log(HWAAS)
        """
        return s_db - n_db - rlg_db + r_db - processing_gain_db

    @staticmethod
    def calc_processing_gain(profile: a121.Profile, step_length: int) -> float:
        """
        Approximates the processing gain of the matched filter.
        """
        envelope_base_length_m = ENVELOPE_FWHM_M[profile] * 2  # approx envelope width
        num_points_in_envelope = (
            int(envelope_base_length_m / (step_length * APPROX_BASE_STEP_LENGTH_M)) + 2
        )
        mid_point = num_points_in_envelope // 2
        pulse = np.concatenate(
            (
                np.linspace(0, 1, mid_point),
                np.linspace(1, 0, num_points_in_envelope - mid_point),
            )
        )
        return float(np.sum(pulse**2))
