# Copyright (c) Acconeer AB, 2022-2023
# All rights reserved
from __future__ import annotations

import importlib.resources
import typing as t
from pathlib import Path

import h5py
import pytest

from acconeer.exptool import a121

from . import distance_test, presence_test, resources
from .misc import AlgorithmFactory, AlgorithmResult, H5ResultSerializer


@pytest.fixture
def output_path(input_path: Path, algorithm_factory: AlgorithmFactory) -> Path:
    """Returns the output path, that is based on the input path."""
    return input_path.with_name(f"{input_path.stem}-{algorithm_factory.__name__}-output.h5")


@pytest.fixture
def input_path(resource_name: str) -> Path:
    """Returns the input path, given a resource name (in the "resources" package)"""
    with importlib.resources.path(resources, resource_name) as path:
        return path


@pytest.mark.parametrize(
    (
        "algorithm_factory",
        "serializer",
        "comparator",
        "resource_name",
    ),
    [
        (
            presence_test.presence_default,
            presence_test.PresenceResultH5Serializer,
            presence_test.result_comparator,
            "input-frame_rate_10Hz-sweeps_per_frame_4.h5",
        ),
        (
            presence_test.presence_default,
            presence_test.PresenceResultH5Serializer,
            presence_test.result_comparator,
            "input-presence-default.h5",
        ),
        (
            presence_test.presence_timeout_3s,
            presence_test.PresenceResultH5Serializer,
            presence_test.result_comparator,
            "input-presence-presence_timeout3s.h5",
        ),
        (
            presence_test.presence_timeout_2s_phase_boost,
            presence_test.PresenceResultH5Serializer,
            presence_test.result_comparator,
            "input-presence-0p35m_phase_boost.h5",
        ),
        (
            distance_test.distance_default,
            distance_test.DistanceResultH5Serializer,
            distance_test.result_comparator,
            "input.h5",
        ),
    ],
)
def test_input_output(
    algorithm_factory: AlgorithmFactory,
    serializer: t.Type[H5ResultSerializer[t.List[AlgorithmResult]]],
    comparator: t.Callable[[AlgorithmResult, AlgorithmResult], bool],
    input_path: Path,
    output_path: Path,
    should_update_outputs: bool,  # from conftest.py
) -> None:
    with h5py.File(input_path) as f:
        r = a121.H5Record(f)
        algorithm = algorithm_factory(r)
        actual_results = [algorithm.process(result) for result in r.results]

    if should_update_outputs:
        output_path.unlink(missing_ok=True)
        with h5py.File(output_path, "w") as out:
            serializer(out.create_group("results")).serialize(actual_results)

    with h5py.File(output_path, "r") as out:
        expected_algorithm_results = serializer(out.require_group("results")).deserialize(None)

    assert len(expected_algorithm_results) == len(actual_results)
    for expected_result, actual_result in zip(expected_algorithm_results, actual_results):
        assert comparator(expected_result, actual_result)
