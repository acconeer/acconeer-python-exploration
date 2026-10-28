# Copyright (c) Acconeer AB, 2026
# All rights reserved

"""Unit tests for the common parts of the heatmap configs."""

from __future__ import annotations

from typing import Any

import pytest

from acconeer.exptool import a2
from acconeer.exptool._core.entities.validation_result import ValidationError
from acconeer.exptool.a2.algo.heatmap import (
    capon,
    coherent,
    config_legacy,
    conventional,
    robust_capon,
)
from acconeer.exptool.a2.algo.heatmap.config_common import HeatmapConfigCommon


HEATMAP_CONFIG_TYPES = [
    pytest.param(capon.HeatmapConfig, id="capon"),
    pytest.param(coherent.HeatmapConfig, id="coherent"),
    pytest.param(conventional.HeatmapConfig, id="conventional"),
    pytest.param(robust_capon.HeatmapConfig, id="robust_capon"),
]


def _session_config(num_subsweeps: int) -> a2.SessionConfig:
    return a2.SessionConfig(
        [a2.SensorConfig.identical_subsweeps(num_subsweeps=num_subsweeps)], update_rate=None
    )


@pytest.mark.parametrize("config_type", HEATMAP_CONFIG_TYPES)
def test_default_config_is_valid(config_type: type[HeatmapConfigCommon]) -> None:
    config_type.default().validate(_session_config(num_subsweeps=1))


@pytest.mark.parametrize("config_type", HEATMAP_CONFIG_TYPES)
def test_multiple_subsweeps_is_an_error(config_type: type[HeatmapConfigCommon]) -> None:
    """The processors take a single subsweep, which must not surface as an AttributeError"""
    session_config = _session_config(num_subsweeps=2)
    config = config_type.default()

    (result,) = config._collect_validation_results(session_config)

    assert isinstance(result, ValidationError)
    assert result.source is session_config.sensor_config
    assert result.aspect == "subsweeps"

    with pytest.raises(ValidationError):
        config.validate(session_config)


@pytest.mark.parametrize("config_type", HEATMAP_CONFIG_TYPES)
def test_multiple_subsweeps_keeps_the_other_checks(
    config_type: type[HeatmapConfigCommon],
) -> None:
    """Only the Tx mask check needs the subsweep"""
    session_config = _session_config(num_subsweeps=2)
    config = config_type.default()
    config.az_angle_range = (60.0, -60.0)

    aspects = {result.aspect for result in config._collect_validation_results(session_config)}

    assert aspects == {"subsweeps", "az_angle_range"}


@pytest.mark.parametrize(
    "timeline",
    [
        pytest.param(capon.heatmap_config_timeline, id="capon"),
        pytest.param(coherent.heatmap_config_timeline, id="coherent"),
        pytest.param(conventional.heatmap_config_timeline, id="conventional"),
        pytest.param(robust_capon.heatmap_config_timeline, id="robust_capon"),
    ],
)
def test_a_legacy_config_migrates(timeline: Any) -> None:
    """As recordings and caches of the first heatmap plugin hold it"""
    legacy = config_legacy.HeatmapConfigLegacy(
        antenna_array=a2.AntennaArray.AP212,
        heatmap_mode="MOVEMENT",
        covariance_matrix_smoothing_factor=0.9,
        high_pass_filter_smoothing_factor=0.9,
        beamforming_method="GENERAL",
        update_count=5,
        az_angle_range=(-30, 30),
        el_angle_range=(0, 0),
        num_az_angles=11,
        num_el_angles=1,
        normalized_heat_cutoff=0.5,
    )

    config = timeline.migrate(legacy.to_json())

    assert (config.az_angle_range, config.num_az_angles) == ((-30, 30), 11)
    if hasattr(config, "heatmap_mode"):
        assert config.heatmap_mode.name == "MOVEMENT"
