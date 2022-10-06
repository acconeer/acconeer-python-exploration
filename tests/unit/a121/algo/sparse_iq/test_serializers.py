# Copyright (c) Acconeer AB, 2022
# All rights reserved
from __future__ import annotations

import itertools
import typing as t

import h5py
import numpy as np
import pytest

from acconeer.exptool.a121.algo.sparse_iq import ProcessorResult, _serializers


def proper_subsets_minus_empty_set(
    collection: t.Collection[t.Any],
) -> t.Iterator[t.Collection[t.Any]]:
    return itertools.chain.from_iterable(
        itertools.combinations(iterable=collection, r=subset_size)
        for subset_size in range(1, len(collection) + 1)
    )


@pytest.fixture
def result():
    return ProcessorResult(
        frame=np.arange(20, dtype=float) + 1j * np.arange(20, dtype=float),
        distance_velocity_map=np.arange(100, dtype=float),
        amplitudes=np.arange(20, dtype=float),
        phases=np.arange(20, dtype=float),
    )


class TestSparseIqResultJSONSerializer:
    @pytest.mark.parametrize(
        ("fields", "allow_missing_fields"),
        [
            (_serializers._ALL_RESULT_FIELDS, False),
            *[
                (subset, True)
                for subset in proper_subsets_minus_empty_set(_serializers._ALL_RESULT_FIELDS)
            ],
        ],
        ids=str,
    )
    def test_results_to_from_json_equality(self, result, fields, allow_missing_fields):
        ser = _serializers.ProcessorResultJSONSerializer(
            fields=fields, allow_missing_fields=allow_missing_fields
        )

        reconstructed = ser.deserialize(ser.serialize(result))
        for field in fields:
            assert (getattr(result, field) == getattr(reconstructed, field)).all()


class TestSparseIqResultListH5Serializer:
    @pytest.fixture
    def tmp_h5_file(self, tmp_path):
        tmp_file_path = tmp_path / "test.h5"

        with h5py.File(tmp_file_path, "a") as f:
            yield f

        tmp_file_path.unlink()

    @pytest.mark.parametrize(
        ("fields", "allow_missing_fields"),
        [
            (_serializers._ALL_RESULT_FIELDS, False),
            *[
                (subset, True)
                for subset in proper_subsets_minus_empty_set(_serializers._ALL_RESULT_FIELDS)
            ],
        ],
        ids=str,
    )
    def test_results_to_from_h5_equality(
        self,
        result,
        tmp_h5_file,
        fields,
        allow_missing_fields,
    ):

        results = [result for _ in range(10)]
        ser = _serializers.ProcessorResultListH5Serializer(
            tmp_h5_file, fields=fields, allow_missing_fields=allow_missing_fields
        )
        ser.serialize(results)
        reconstructed_results = ser.deserialize(None)

        assert len(results) == len(reconstructed_results)
        for result, reconstructed_result in zip(results, reconstructed_results):
            for field in fields:
                assert (getattr(result, field) == getattr(reconstructed_result, field)).all()
