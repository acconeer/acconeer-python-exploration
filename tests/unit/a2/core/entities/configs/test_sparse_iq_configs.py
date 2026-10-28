# Copyright (c) Acconeer AB, 2022-2026
# All rights reserved
from __future__ import annotations

import json
import typing as t

import pytest

from acconeer.exptool import a2
from acconeer.exptool.a2._core.entities.configs.sensor_config import sensor_config_timeline


def test_dyn_hwaas_values() -> None:
    ssc = a2.SubsweepConfig()
    ssc.hwaas_max = 50
    ssc.hwaas_exponent = 4
    ssc.hwaas_min = 1
    hwaas_points = ssc.hwaas_points
    expected_output = [
        *[1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 2, 2, 2, 3, 3, 4, 5],
        *[6, 6, 8, 9, 9, 11, 14, 14, 16, 20, 20, 24, 24, 29, 29, 34, 42, 42, 42, 50],
    ]
    assert (hwaas_points == expected_output).all()


def test_dyn_hwaas_rss_values() -> None:
    """Reflection of the dynamic HWAAS unit test in the A2 RSS"""
    ssc = a2.SubsweepConfig()
    ssc.start_point = 1
    ssc.num_points = 100
    ssc.step_length = 4
    ssc.hwaas_max = 100
    ssc.hwaas_exponent = 4
    ssc.hwaas_min = 5
    scaled_hwaas = ssc._calc_scaled_hwaas()
    stepped_hwaas = ssc._calc_stepped_hwaas(scaled_hwaas)
    switch_points, hwaas = ssc._get_dyn_hwaas_table(scaled_hwaas, stepped_hwaas)
    rss_hwaas = [
        *[5, 6, 7, 8, 9, 10, 12, 14, 16, 18, 21],
        *[24, 28, 32, 37, 42, 49, 57, 65, 75, 87, 100],
    ]
    rss_switch_points = [
        *[48, 50, 52, 54, 55, 57, 60, 62, 64, 66, 69],
        *[71, 74, 76, 79, 82, 85, 88, 91, 94, 98],
    ]
    assert rss_switch_points == switch_points
    assert rss_hwaas == hwaas


def test_dyn_hwaas_values_all_neg_points() -> None:
    ssc = a2.SubsweepConfig()
    ssc.hwaas_max = 50
    ssc.num_points = 5
    ssc.hwaas_exponent = 4
    ssc.hwaas_min = 1
    ssc.start_point = -10
    ssc.step_length = 1
    hwaas_points = ssc.hwaas_points
    expected_output = [50, 50, 50, 50, 50]
    assert (hwaas_points == expected_output).all()


def test_dyn_hwaas_values_zero_exponent() -> None:
    ssc = a2.SubsweepConfig()
    ssc.hwaas_max = 50
    ssc.num_points = 5
    ssc.hwaas_exponent = 0
    ssc.hwaas_min = 1
    ssc.start_point = 10
    ssc.step_length = 1
    hwaas_points = ssc.hwaas_points
    expected_output = [50, 50, 50, 50, 50]
    assert (hwaas_points == expected_output).all()


cmn_kws = {"step_length": 1, "num_points": 1}


@pytest.mark.parametrize(
    ("is_valid", "config_kws"),
    [
        (True, {"prf": a2.PRF.PRF_27_7_MHZ, "start_point": 960, **cmn_kws}),
        (False, {"prf": a2.PRF.PRF_27_7_MHZ, "start_point": 961, **cmn_kws}),
        (True, {"prf": a2.PRF.PRF_20_8_MHZ, "start_point": 1680, **cmn_kws}),
        (False, {"prf": a2.PRF.PRF_20_8_MHZ, "start_point": 1681, **cmn_kws}),
        (True, {"prf": a2.PRF.PRF_15_8_MHZ, "start_point": 2640, **cmn_kws}),
        (False, {"prf": a2.PRF.PRF_15_8_MHZ, "start_point": 2641, **cmn_kws}),
        (True, {"prf": a2.PRF.PRF_12_5_MHZ, "start_point": 3600, **cmn_kws}),
        (False, {"prf": a2.PRF.PRF_12_5_MHZ, "start_point": 3601, **cmn_kws}),
        (True, {"prf": a2.PRF.PRF_8_3_MHZ, "start_point": 6000, **cmn_kws}),
        (False, {"prf": a2.PRF.PRF_8_3_MHZ, "start_point": 6001, **cmn_kws}),
        (True, {"prf": a2.PRF.PRF_5_3_MHZ, "start_point": 10008, **cmn_kws}),
        (False, {"prf": a2.PRF.PRF_5_3_MHZ, "start_point": 10009, **cmn_kws}),
    ],
)
def test_end_point_prf_check(is_valid: bool, config_kws: dict[str, t.Any]) -> None:
    try:
        a2.SubsweepConfig(**config_kws).validate()
    except a2.ValidationError as ve:
        assert not is_valid, f"SubsweepConfig should have been valid: {ve}"
    else:
        assert is_valid, "SubsweepConfig should have been invalid"

    try:
        a2.SensorConfig.single_subsweep(**config_kws).validate()
    except a2.ValidationError as ve:
        assert not is_valid, f"SensorConfig should have been valid: {ve}"
    else:
        assert is_valid, "SensorConfig should have been invalid"

    try:
        a2.SessionConfig(
            sensor_configs=[a2.SensorConfig.single_subsweep(**config_kws)],
            update_rate=1.0,
        ).validate()
    except a2.ValidationError as ve:
        assert not is_valid, f"SessionConfig should have been valid: {ve}"
    else:
        assert is_valid, "SessionConfig should have been invalid"


@pytest.mark.parametrize(
    ("num_subsweeps", "jitter_compensation", "is_valid"),
    [(4, True, True), (5, False, True), (5, True, False)],
)
def test_jitter_compensation_needs_a_free_subsweep_slot(
    num_subsweeps: int, jitter_compensation: bool, is_valid: bool
) -> None:
    config = a2.SensorConfig.identical_subsweeps(
        num_subsweeps=num_subsweeps, jitter_compensation=jitter_compensation
    )

    if is_valid:
        config.validate()
    else:
        with pytest.raises(a2.ValidationError) as excinfo:
            config.validate()

        assert excinfo.value.aspect == "jitter_compensation"


def _ready_sensor_config(jitter_compensation: bool) -> a2.SensorConfig:
    return a2.SensorConfig.single_subsweep(
        sweeps_per_frame=4,
        sweep_rate=1000.0,
        inter_frame_idle_state=a2.IdleState.READY,
        inter_sweep_idle_state=a2.IdleState.READY,
        jitter_compensation=jitter_compensation,
    )


@pytest.mark.parametrize("as_json", [False, True])
def test_a_config_from_before_jitter_compensation_loads_without_it(as_json: bool) -> None:
    config = _ready_sensor_config(jitter_compensation=True)
    saved = json.loads(config.to_json()) if as_json else config.to_dict()
    del saved["jitter_compensation"]

    loaded = sensor_config_timeline.migrate(json.dumps(saved) if as_json else saved)

    assert loaded == _ready_sensor_config(jitter_compensation=False)


@pytest.mark.parametrize("jitter_compensation", [False, True])
def test_a_current_config_loads_as_saved(jitter_compensation: bool) -> None:
    config = _ready_sensor_config(jitter_compensation)

    assert sensor_config_timeline.migrate(config.to_dict()) == config
    assert sensor_config_timeline.migrate(config.to_json()) == config
