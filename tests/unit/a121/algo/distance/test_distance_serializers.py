# Copyright (c) Acconeer AB, 2022-2023
# All rights reserved
from __future__ import annotations

import itertools
import typing as t
from pathlib import Path

import h5py
import numpy as np
import pytest

from acconeer.exptool.a121.algo.distance import ProcessorResult, _serializers


def proper_subsets_minus_empty_set(
    collection: t.Collection[t.Any],
) -> t.Iterator[t.Collection[t.Any]]:
    return itertools.chain.from_iterable(
        itertools.combinations(iterable=collection, r=subset_size)
        for subset_size in range(1, len(collection) + 1)
    )


@pytest.fixture
def results() -> t.List[ProcessorResult]:
    return [
        ProcessorResult(
            estimated_distances=[float(i) for i in range(10)],
            estimated_rcs=[float(i) for i in range(10)],
            near_edge_status=True,
            recorded_threshold_mean_sweep=np.array(range(20)),
            recorded_threshold_noise_std=[
                np.float_(0.1),
            ]
            * 20,
            direct_leakage=np.arange(20, dtype=complex),
            phase_jitter_comp_reference=np.arange(10, dtype=float).reshape((10, 1)),
            extra_result=None,  # type: ignore[arg-type]
        ),
        ProcessorResult(
            estimated_distances=None,
            estimated_rcs=None,
            near_edge_status=True,
            recorded_threshold_mean_sweep=np.array(range(20)),
            recorded_threshold_noise_std=[np.float_(0.1)] * 20,
            direct_leakage=np.arange(20, dtype=complex),
            phase_jitter_comp_reference=np.arange(10, dtype=float).reshape((10, 1)),
            extra_result=None,  # type: ignore[arg-type]
        ),
        ProcessorResult(
            estimated_distances=[float(i) for i in range(10)],
            estimated_rcs=[float(i) for i in range(10)],
            near_edge_status=True,
            recorded_threshold_mean_sweep=None,
            recorded_threshold_noise_std=None,
            direct_leakage=np.arange(20, dtype=complex),
            phase_jitter_comp_reference=np.arange(10, dtype=float).reshape((10, 1)),
            extra_result=None,  # type: ignore[arg-type]
        ),
        ProcessorResult(
            estimated_distances=[float(i) for i in range(10)],
            estimated_rcs=[float(i) for i in range(10)],
            near_edge_status=True,
            recorded_threshold_mean_sweep=np.array(range(20)),
            recorded_threshold_noise_std=[
                np.float_(0.1),
            ]
            * 20,
            direct_leakage=None,
            phase_jitter_comp_reference=np.arange(10, dtype=float).reshape((10, 1)),
            extra_result=None,  # type: ignore[arg-type]
        ),
        ProcessorResult(
            estimated_distances=[float(i) for i in range(10)],
            estimated_rcs=[float(i) for i in range(10)],
            near_edge_status=True,
            recorded_threshold_mean_sweep=np.array(range(20)),
            recorded_threshold_noise_std=[
                np.float_(0.1),
            ]
            * 20,
            direct_leakage=np.arange(20, dtype=complex),
            phase_jitter_comp_reference=None,
            extra_result=None,  # type: ignore[arg-type]
        ),
    ]


class TestDistanceResultListH5Serializer:
    @pytest.fixture
    def tmp_h5_file(self, tmp_path: Path) -> h5py.File:
        tmp_file_path = tmp_path / "test.h5"

        with h5py.File(tmp_file_path, "a") as f:
            yield f

        tmp_file_path.unlink()

    @pytest.mark.parametrize(
        ("fields", "allow_missing_fields"),
        [
            (_serializers._ALL_PROCESSOR_RESULT_FIELDS, False),
            *[
                (subset, True)
                for subset in proper_subsets_minus_empty_set(
                    _serializers._ALL_PROCESSOR_RESULT_FIELDS
                )
            ],
        ],
        ids=str,
    )
    def test_results_to_from_h5_equality(
        self,
        results: t.List[ProcessorResult],
        tmp_h5_file: h5py.File,
        fields: t.Sequence[str],
        allow_missing_fields: bool,
    ) -> None:
        ser = _serializers.ProcessorResultListH5Serializer(
            tmp_h5_file, fields=fields, allow_missing_fields=allow_missing_fields
        )
        ser.serialize(results)
        reconstructed_results = ser.deserialize(None)

        assert len(results) == len(reconstructed_results)
        for result, reconstructed_result in zip(results, reconstructed_results):
            for field in fields:
                a = getattr(result, field)
                b = getattr(reconstructed_result, field)

                try:
                    assert a == b
                except ValueError:  # "truth value of an array is ambiguous ..."
                    assert (a == b).all()
