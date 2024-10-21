# Copyright (c) Acconeer AB, 2023-2024
# All rights reserved

from __future__ import annotations

from typing import Optional, Tuple

import attrs
import numpy as np
import numpy.typing as npt

from acconeer.exptool import a121
from acconeer.exptool.a121.algo import ENVELOPE_FWHM_M, PeakSortingMethod
from acconeer.exptool.a121.algo.distance._processors import (
    Processor,
    ProcessorConfig,
    ProcessorContext,
    ProcessorResult,
)


@attrs.frozen(kw_only=True)
class ProcessorSpec:
    processor_config: ProcessorConfig = attrs.field()
    group_index: int = attrs.field()
    subsweep_indexes: list[int] = attrs.field()
    processor_context: Optional[ProcessorContext] = attrs.field(default=None)


@attrs.mutable(kw_only=True)
class AggregatorConfig:
    peak_sorting_method: PeakSortingMethod = attrs.field(default=PeakSortingMethod.STRONGEST)


@attrs.frozen(kw_only=True)
class AggregatorResult:
    processor_results: list[ProcessorResult] = attrs.field()
    estimated_distances: npt.NDArray[np.float64] = attrs.field()
    estimated_strengths: npt.NDArray[np.float64] = attrs.field()
    near_edge_status: Optional[bool] = attrs.field(default=None)
    service_extended_result: list[dict[int, a121.Result]] = attrs.field()


class Aggregator:
    """Aggregating class

    Instantiates Processor objects based configuration from Detector.

    Aggregates result, based on selected peak sorting strategy, from underlying Processor objects.
    """

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
        dists: npt.NDArray[np.float64] = np.array([])
        strengths: npt.NDArray[np.float64] = np.array([])
        profile_fwhms: npt.NDArray[np.float64] = np.array([])

        for spec, processor in zip(self.specs, self.processors):
            processor_result = processor.process(extended_result[spec.group_index][self.sensor_id])
            processors_result.append(processor_result)
            if processor_result.estimated_distances is not None:
                strengths = np.concatenate(
                    (strengths, np.array(processor_result.estimated_strengths))
                )
                dists = np.concatenate((dists, np.array(processor_result.estimated_distances)))
                profile_fwhms = np.concatenate(
                    (
                        profile_fwhms,
                        np.ones_like(np.array(processor_result.estimated_distances))
                        * ENVELOPE_FWHM_M[processor.profile],
                    )
                )
        # Remove first element as the FWHM of the subsweep with greater profile is used when
        # determining the distance for merging two peaks.
        if profile_fwhms.shape[0] != 0:
            profile_fwhms = np.delete(profile_fwhms, 0)

        (dists_merged, strengths_merged) = self._merge_peaks(profile_fwhms, dists, strengths)
        (dists_sorted, strengths_sorted) = self._sort_peaks(
            dists_merged, strengths_merged, self.config.peak_sorting_method
        )

        return AggregatorResult(
            processor_results=processors_result,
            estimated_distances=dists_sorted,
            estimated_strengths=strengths_sorted,
            near_edge_status=processors_result[0].near_edge_status,
            service_extended_result=extended_result,
        )

    @staticmethod
    def _merge_peaks(
        profile_fwhms: npt.NDArray[np.float64],
        dists: npt.NDArray[np.float64],
        strengths: npt.NDArray[np.float64],
    ) -> Tuple[npt.NDArray[np.float64], npt.NDArray[np.float64]]:
        sorting_order = np.argsort(dists)
        distances_sorted = dists[sorting_order]
        strengths_sorted = strengths[sorting_order]
        profile_fwhms = profile_fwhms[sorting_order[1:] - 1]

        peak_cluster_idxs = np.where(profile_fwhms < np.diff(distances_sorted))[0] + 1
        distances_merged = [
            np.mean(cluster)
            for cluster in np.split(distances_sorted, peak_cluster_idxs)
            if dists.size != 0
        ]
        strengths_merged = [
            np.mean(cluster)
            for cluster in np.split(strengths_sorted, peak_cluster_idxs)
            if dists.size != 0
        ]
        return (np.array(distances_merged), np.array(strengths_merged))

    @staticmethod
    def _sort_peaks(
        dists: npt.NDArray[np.float64],
        strengths: npt.NDArray[np.float64],
        method: PeakSortingMethod,
    ) -> Tuple[npt.NDArray[np.float64], npt.NDArray[np.float64]]:
        if method == PeakSortingMethod.CLOSEST:
            quantity_to_sort = dists
        elif method == PeakSortingMethod.STRONGEST:
            quantity_to_sort = -strengths
        else:
            msg = "Unknown peak sorting method"
            raise ValueError(msg)
        return (
            np.array([dists[i] for i in quantity_to_sort.argsort()]),
            np.array([strengths[i] for i in quantity_to_sort.argsort()]),
        )
