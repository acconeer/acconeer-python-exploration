# Copyright (c) Acconeer AB, 2022
# All rights reserved

from __future__ import annotations

import enum
from typing import Optional, Tuple

import attrs
import numpy as np
import numpy.typing as npt

from acconeer.exptool import a121
from acconeer.exptool.a121.algo import AlgoParamEnum
from acconeer.exptool.a121.algo.distance._processors import (
    Processor,
    ProcessorConfig,
    ProcessorContext,
    ProcessorResult,
)


class PeakSortingMethod(AlgoParamEnum):
    """Peak sorting methods.
    ``CLOSEST`` sort according to distance.
    ``STRONGEST`` sort according to amplitude
    ``HIGHEST_RCS`` sort according to RCS."""

    CLOSEST = enum.auto()
    STRONGEST = enum.auto()
    HIGHEST_RCS = enum.auto()


@attrs.frozen(kw_only=True)
class ProcessorSpec:
    processor_config: ProcessorConfig = attrs.field()
    group_index: int = attrs.field()
    sensor_id: int = attrs.field()
    subsweep_indexes: list[int] = attrs.field()
    processor_context: Optional[ProcessorContext] = attrs.field(default=None)


@attrs.mutable(kw_only=True)
class AggregatorConfig:
    peak_sorting_method: PeakSortingMethod = attrs.field(default=PeakSortingMethod.STRONGEST)


@attrs.frozen(kw_only=True)
class AggregatorContext:
    offset_m: float = attrs.field(default=0.0)


@attrs.frozen(kw_only=True)
class AggregatorResult:
    processor_results: list[ProcessorResult] = attrs.field()
    estimated_distances: npt.NDArray[np.float_] = attrs.field()
    service_extended_result: list[dict[int, a121.Result]] = attrs.field()


class Aggregator:
    """Aggregating class

    Instantiates Processor objects based configuration from Detector.

    Aggregates result, based on selected peak sorting strategy, from underlying Processor objects.
    """

    MIN_PEAK_DIST_M = 0.005

    def __init__(
        self,
        session_config: a121.SessionConfig,
        extended_metadata: list[dict[int, a121.Metadata]],
        config: AggregatorConfig,
        context: AggregatorContext,
        specs: list[ProcessorSpec],
    ):
        self.config = config
        self.context = context
        self.specs = specs

        self.processors: list[Processor] = []

        for spec in specs:
            metadata = extended_metadata[spec.group_index][spec.sensor_id]
            sensor_config = session_config.groups[spec.group_index][spec.sensor_id]

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
        for spec, processor in zip(self.specs, self.processors):
            processor_result = processor.process(extended_result[spec.group_index][spec.sensor_id])
            processors_result.append(processor_result)
            if processor_result.estimated_distances is not None:
                ampls = np.concatenate((ampls, np.array(processor_result.estimated_amplitudes)))
                dists = np.concatenate((dists, np.array(processor_result.estimated_distances)))

        (dists_merged, ampls_merged) = self._merge_peaks(self.MIN_PEAK_DIST_M, dists, ampls)
        dists_sorted = self._sort_peaks(
            dists_merged, ampls_merged, self.config.peak_sorting_method
        )
        dists_sorted -= self.context.offset_m
        return AggregatorResult(
            processor_results=processors_result,
            estimated_distances=dists_sorted,
            service_extended_result=extended_result,
        )

    @staticmethod
    def _merge_peaks(
        min_peak_to_peak_dist: float,
        dists: npt.NDArray[np.float_],
        ampls: npt.NDArray[np.float_],
    ) -> Tuple[npt.NDArray[np.float_], npt.NDArray[np.float_]]:
        sorting_order = np.argsort(dists)
        distances_sorted = dists[sorting_order]
        amplitudes_sorted = ampls[sorting_order]

        peak_cluster_idxs = np.where(min_peak_to_peak_dist < np.diff(distances_sorted))[0] + 1
        distances_merged = [
            np.mean(cluster) for cluster in np.split(distances_sorted, peak_cluster_idxs)
        ]
        amplitudes_merged = [
            np.mean(cluster) for cluster in np.split(amplitudes_sorted, peak_cluster_idxs)
        ]
        return (np.array(distances_merged), np.array(amplitudes_merged))

    @staticmethod
    def _sort_peaks(
        dists: npt.NDArray[np.float_],
        ampls: npt.NDArray[np.float_],
        method: PeakSortingMethod,
    ) -> npt.NDArray[np.float_]:
        if method == PeakSortingMethod.CLOSEST:
            quantity_to_sort = dists
        elif method == PeakSortingMethod.STRONGEST:
            quantity_to_sort = -ampls
        elif method == PeakSortingMethod.HIGHEST_RCS:
            quantity_to_sort = -ampls * dists**2
        else:
            raise ValueError("Unknown peak sorting method")
        return np.array([dists[i] for i in quantity_to_sort.argsort()])
