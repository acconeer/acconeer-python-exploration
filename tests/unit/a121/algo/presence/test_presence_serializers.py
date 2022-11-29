# Copyright (c) Acconeer AB, 2022
# All rights reserved
from __future__ import annotations

import itertools
import typing as t
from pathlib import Path

import h5py
import pytest

from acconeer.exptool.a121.algo.presence import ProcessorResult, _serializers


def proper_subsets_minus_empty_set(
    collection: t.Collection[t.Any],
) -> t.Iterator[t.Collection[t.Any]]:
    return itertools.chain.from_iterable(
        itertools.combinations(iterable=collection, r=subset_size)
        for subset_size in range(1, len(collection) + 1)
    )


@pytest.fixture
def result() -> ProcessorResult:
    return ProcessorResult(
        intra_presence_score=0.1,
        inter_presence_score=0.2,
        presence_detected=False,
        presence_distance=0.4,
        extra_result=None,  # type: ignore[arg-type]
    )


class TestPresenceResultListH5Serializer:
    @pytest.fixture
    def tmp_h5_file(self, tmp_path: Path) -> h5py.File:
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
        result: ProcessorResult,
        tmp_h5_file: h5py.File,
        fields: t.Sequence[str],
        allow_missing_fields: bool,
    ) -> None:

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
