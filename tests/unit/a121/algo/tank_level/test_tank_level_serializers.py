# Copyright (c) Acconeer AB, 2023
# All rights reserved
from __future__ import annotations

from pathlib import Path
from typing import List, Sequence

import h5py
import numpy as np
import pytest

from acconeer.exptool.a121.algo.tank_level import ProcessorLevelStatus, RefAppResult, _serializer

from utils.test_utils import subsets_minus_empty_set  # type: ignore[import]


@pytest.fixture
def results() -> List[RefAppResult]:
    return [
        RefAppResult(
            peak_detected=True,
            peak_status=ProcessorLevelStatus.IN_RANGE,
            level=5.0,
            extra_result=None,  # type: ignore[arg-type]
        ),
        RefAppResult(
            peak_detected=False,
            peak_status=ProcessorLevelStatus.NO_DETECTION,
            level=np.nan,
            extra_result=None,  # type: ignore[arg-type]
        ),
        RefAppResult(
            peak_detected=False,
            peak_status=ProcessorLevelStatus.OVERFLOW,
            level=np.nan,
            extra_result=None,  # type: ignore[arg-type]
        ),
        RefAppResult(
            peak_detected=True,
            peak_status=ProcessorLevelStatus.OUT_OF_RANGE,
            level=5.0,
            extra_result=None,  # type: ignore[arg-type]
        ),
    ]


@pytest.fixture
def tmp_h5_file(tmp_path: Path) -> h5py.File:
    tmp_file_path = tmp_path / "test.h5"

    with h5py.File(tmp_file_path, "a") as f:
        yield f

    tmp_file_path.unlink()


@pytest.mark.parametrize(
    ("fields", "allow_missing_fields"),
    [
        (_serializer._ALL_REF_APP_RESULT_FIELDS, False),
        *[
            (subset, True)
            for subset in subsets_minus_empty_set(_serializer._ALL_REF_APP_RESULT_FIELDS)
        ],
    ],
    ids=str,
)
def test_results_to_from_h5_equality(
    results: List[RefAppResult],
    tmp_h5_file: h5py.File,
    fields: Sequence[str],
    allow_missing_fields: bool,
) -> None:
    ser = _serializer.RefAppResultListH5Serializer(
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
                assert a == b or (np.isnan(a) and np.isnan(b))
            except ValueError:  # "truth value of an array is ambiguous ..."
                assert (a == b).all()
