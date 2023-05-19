# Copyright (c) Acconeer AB, 2023
# All rights reserved
from __future__ import annotations

from pathlib import Path
from typing import List, Sequence

import h5py
import numpy as np
import pytest

from acconeer.exptool.a121.algo.smart_presence import _serializer
from acconeer.exptool.a121.algo.smart_presence._ref_app import RefAppResult, _Mode

from utils.test_utils import subsets_minus_empty_set  # type: ignore[import]


@pytest.fixture
def results() -> List[RefAppResult]:
    return [
        RefAppResult(
            zone_limits=np.array(range(10)),
            presence_detected=True,
            max_presence_zone=3,
            total_zone_detections=np.array(range(10)),
            inter_presence_score=1.0,
            inter_zone_detections=np.array(range(10)),
            max_inter_zone=2,
            intra_presence_score=0.0,
            intra_zone_detections=np.array(range(10)),
            max_intra_zone=2,
            used_config=_Mode.NOMINAL_CONFIG,
            wake_up_detections=np.array(range(10)),
            switch_delay=False,
            service_result=None,  # type: ignore[arg-type]
        )
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
