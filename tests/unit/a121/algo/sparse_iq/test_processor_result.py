# Copyright (c) Acconeer AB, 2022
# All rights reserved

import json

import numpy as np
import pytest

from acconeer.exptool.a121.algo.sparse_iq import ProcessorResult, _serializers


class TestSparseIqProcessorResult:
    @pytest.fixture
    def result(self):
        return ProcessorResult(
            frame=np.arange(20, dtype=float) + 1j * np.arange(20, dtype=float),
            distance_velocity_map=np.arange(100, dtype=float),
            amplitudes=np.arange(20, dtype=float),
            phases=np.arange(20, dtype=float),
        )

    def test_identical_results_are_equal(self, result: ProcessorResult) -> None:
        assert result == ProcessorResult(
            frame=np.arange(20, dtype=float) + 1j * np.arange(20, dtype=float),
            distance_velocity_map=np.arange(100, dtype=float),
            amplitudes=np.arange(20, dtype=float),
            phases=np.arange(20, dtype=float),
        )

    def test_different_results_are_not_equal(self, result: ProcessorResult) -> None:
        assert result != ProcessorResult(
            frame=np.arange(19, dtype=float) + 1j * np.arange(19, dtype=float),
            distance_velocity_map=np.arange(99, dtype=float),
            amplitudes=np.arange(19, dtype=float),
            phases=np.arange(19, dtype=float),
        )

    def test_results_to_from_json_equality(self, result: ProcessorResult) -> None:
        assert result == json.loads(
            json.dumps(result, cls=_serializers.ProcessorResultJSONEncoder),
            cls=_serializers.ProcessorResultJSONDecoder,
        )
