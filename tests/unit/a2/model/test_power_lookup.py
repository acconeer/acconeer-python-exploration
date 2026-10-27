# Copyright (c) Acconeer AB, 2026
# All rights reserved

from __future__ import annotations

import copy
import re
import typing as t
from pathlib import Path

import pytest
import yaml

from acconeer.exptool import a2
from acconeer.exptool.a2.model import power


# A complete but minimal lookup, with every current as a plain total. The tests
# build their variants from this so that each one states its own shape.
SCALAR_LOOKUP: dict[str, t.Any] = {
    "sleep_currents": {
        "SHALLOW_SLEEP": 243.0e-6,
        "DEEP_SLEEP": 22.0e-6,
        "ULTRA_DEEP_SLEEP": 17.0e-6,
    },
    "aps_idle_currents": {
        "APS_HF_WFI": 14.255e-3,
        "APS_MF_WFI": 3.609e-3,
        "APS_LF_WFI": 1.066e-3,
    },
    "idle_currents": {"ARMED": 97.949e-3, "READY": 21.759e-3},
    "hsm_armed_offset": 10.0e-3,
    "aps_active_currents": {
        "APS_HF": 31.879e-3,
        "APS_MF": 5.248e-3,
        "APS_LF": 1.060e-3,
    },
    "aps_hf_wfi_rs_measure_model": {
        profile: {"intercept": 148.5e-3, "slope_per_mhz": 0.76e-3} for profile in range(1, 8)
    },
    "rx_antenna_current": {profile: dict.fromkeys(range(4), 7.5e-3) for profile in range(1, 8)},
    "aps_sleep_wakeup_state": {
        "SHALLOW_SLEEP": {"current": 4.7e-3, "duration": 6.156e-3},
        "DEEP_SLEEP": {"current": 4.7e-3, "duration": 31.4e-3},
        "ULTRA_DEEP_SLEEP": {"current": 4.7e-3, "duration": 31.4e-3},
    },
    "aps_go_to_sleep_state": {
        "SHALLOW_SLEEP": {"current": 9.0e-3, "duration": 513.0e-6},
        "DEEP_SLEEP": {"current": 11.7e-3, "duration": 650.0e-6},
        "ULTRA_DEEP_SLEEP": {"current": 11.7e-3, "duration": 650.0e-6},
    },
    "calibration_state": {"current": 133.0e-3, "duration": 26.6e-3},
    "radar_prepare_state": {"current": 26.0e-3, "duration": 263.0e-6},
    "radar_prepare_rs_init_state": {"current": 53.0e-3, "duration": 914.0e-6},
    "radar_power_on_state": {"current": 21.8e-3, "duration": 2.12e-3},
    "radar_power_off_state": {"current": 150.0e-3, "duration": 3.85e-6},
    "aps_lf_to_hf_state": {"current": 3.5e-3, "duration": 7.0e-3},
    "aps_mf_to_hf_state": {"current": "APS_MF", "duration": 127.0e-6},
    "aps_hf_to_lf_state": {"current": 2.9e-3, "duration": 6.1e-3},
    "aps_hf_to_mf_state": {"current": "APS_HF", "duration": 3.2e-6},
    "frame_overhead": 4.0e-6,
    "frame_overhead_hsm": 4.0e-6,
    "sweep_setup_times": {"ARMED": 1.82e-6, "READY": 92.8e-6},
    "subsweep_setup_times_hsm": {"ARMED": 20.4e-6, "READY": 112.5e-6},
    "subsweep_setup_time": 32.6e-6,
    "subsweep_setup_time_loopback": 23.3e-6,
    "sample_durations": {profile: {prf.name: 1.0e-6 for prf in a2.PRF} for profile in range(1, 8)},
    "jitter_compensation_duration": 84.638e-6,
    "iq_processing_fixed": 413.0e-9,
    "iq_processing_per_point": 385.0e-9,
    "capon_processing_per_param": 225.0e-9,
    "capon_update_per_point": 1.149e-6,
    "coherent_processing_per_param": 75.6e-9,
    "coherent_update_per_point": 29.8e-9,
    "conventional_processing_per_param": 187.0e-9,
    "conventional_update_per_point": 1.0e-6,
    "robust_capon_processing_per_param": 650.0e-9,
    "robust_capon_update_per_point": 6.5e-6,
}

SPLIT_MODEL = {
    profile: {
        "dig": {"intercept": 100.0e-3, "slope_per_mhz": 0.50e-3},
        "rx": {"intercept": 48.5e-3, "slope_per_mhz": 0.26e-3},
    }
    for profile in range(1, 8)
}


def _write(tmp_path: Path, lookup: dict[str, t.Any], name: str = "lookup.yaml") -> Path:
    path = tmp_path / name
    path.write_text(yaml.safe_dump(lookup, sort_keys=False), encoding="utf-8")
    return path


def _split(value: t.Any) -> dict[str, t.Any]:
    """Split a current into two components, following the section's nesting."""
    if isinstance(value, dict):
        return {key: _split(inner) for key, inner in value.items()}
    return {"dig": value * 0.9, "rx": value * 0.1}


def _split_currents(lookup: dict[str, t.Any], *sections: str) -> dict[str, t.Any]:
    """Turn whole current sections from totals into two components."""
    out = copy.deepcopy(lookup)
    for section in sections:
        out[section] = {key: _split(value) for key, value in out[section].items()}
    return out


SPLIT_SECTIONS = (
    "sleep_currents",
    "aps_idle_currents",
    "idle_currents",
    "aps_active_currents",
    "rx_antenna_current",
)


def _measure_current(path: Path) -> power.CurrentBreakdown:
    constants = power.SensorConstants.from_yaml(path)
    return constants.measure_currents[a2.Profile(1)][a2.PRF.PRF_27_7_MHZ]


def test_the_fixture_is_a_complete_lookup(tmp_path: Path) -> None:
    """SCALAR_LOOKUP mirrors the schema by hand, so it drifts when keys are added."""
    power.SensorConstants.from_yaml(_write(tmp_path, SCALAR_LOOKUP))


def test_packaged_lookup_is_total_only() -> None:
    """The packaged data set carries totals only."""
    assert not power.SensorConstants.default().has_current_breakdown


def test_packaged_lookup_loads_at_every_temperature_it_declares() -> None:
    constants = power.SensorConstants.default()

    assert constants.measure_currents[a2.Profile(1)][a2.PRF.PRF_27_7_MHZ].total > 0
    for temperature in constants.available_temperatures:
        at_temperature = power.SensorConstants.at_temperature(temperature)
        assert at_temperature.idle_currents[a2.IdleState.ARMED].total > 0


def test_total_only_model_gives_a_single_component(tmp_path: Path) -> None:
    current = _measure_current(_write(tmp_path, SCALAR_LOOKUP))

    assert set(current.currents) == {"total"}
    # intercept + slope * 27.7 MHz - the APS idle current the model subtracts
    assert current.total == pytest.approx(148.5e-3 + 0.76e-3 * 27.7 - 14.255e-3)


def test_split_model_keeps_the_total_and_adds_components(tmp_path: Path) -> None:
    split = _split_currents(SCALAR_LOOKUP, *SPLIT_SECTIONS)
    split["aps_hf_wfi_rs_measure_model"] = SPLIT_MODEL

    current = _measure_current(_write(tmp_path, split))

    # Each component is its own fit less its share of the APS idle current.
    assert current.currents["dig"] == pytest.approx(100.0e-3 + 0.50e-3 * 27.7 - 0.9 * 14.255e-3)
    assert current.currents["rx"] == pytest.approx(48.5e-3 + 0.26e-3 * 27.7 - 0.1 * 14.255e-3)
    # The components carry the same intercept and slope in total as the single
    # pair of the total-only model, so the total has to come out equal.
    assert current.total == pytest.approx(148.5e-3 + 0.76e-3 * 27.7 - 14.255e-3)


def test_split_model_with_total_currents_is_rejected(tmp_path: Path) -> None:
    lookup = copy.deepcopy(SCALAR_LOOKUP)
    lookup["aps_hf_wfi_rs_measure_model"] = SPLIT_MODEL

    with pytest.raises(ValueError, match="measure model is split per component"):
        power.SensorConstants.from_yaml(_write(tmp_path, lookup))


def test_split_currents_with_a_total_model_is_rejected(tmp_path: Path) -> None:
    lookup = _split_currents(SCALAR_LOOKUP, *SPLIT_SECTIONS)

    with pytest.raises(ValueError, match="currents are split per component"):
        power.SensorConstants.from_yaml(_write(tmp_path, lookup))


@pytest.mark.parametrize("section", SPLIT_SECTIONS)
def test_splitting_one_current_section_is_rejected(tmp_path: Path, section: str) -> None:
    lookup = _split_currents(SCALAR_LOOKUP, section)

    with pytest.raises(ValueError, match="Every current must agree on being split"):
        power.SensorConstants.from_yaml(_write(tmp_path, lookup))


def test_a_model_split_for_only_some_profiles_is_rejected(tmp_path: Path) -> None:
    lookup = _split_currents(SCALAR_LOOKUP, *SPLIT_SECTIONS)
    lookup["aps_hf_wfi_rs_measure_model"] = copy.deepcopy(SPLIT_MODEL)
    lookup["aps_hf_wfi_rs_measure_model"][2] = {"intercept": 148.5e-3, "slope_per_mhz": 0.76e-3}

    with pytest.raises(ValueError, match="must carry the same components"):
        power.SensorConstants.from_yaml(_write(tmp_path, lookup))


_PAIR = "must have exactly 'intercept' and 'slope_per_mhz'"
_SHAPE = "must be a coefficient pair or a mapping of them"


@pytest.mark.parametrize(
    ("model", "message"),
    [
        pytest.param({"intercept": 0.1485}, _PAIR, id="missing-slope"),
        pytest.param({"intercept": 0.1485, "slope": 0.00076}, _PAIR, id="misnamed-slope"),
        pytest.param({"dig": {"intercept": 0.1}}, _PAIR, id="component-missing-slope"),
        pytest.param(
            {"total": SPLIT_MODEL[1]["dig"], "dig": SPLIT_MODEL[1]["dig"]},
            "cannot mix 'total' with component keys",
            id="component-called-total",
        ),
        pytest.param(0.1485, _SHAPE, id="bare-number"),
        pytest.param({}, _SHAPE, id="empty"),
    ],
)
def test_malformed_model_entries_are_rejected(tmp_path: Path, model: t.Any, message: str) -> None:
    lookup = copy.deepcopy(SCALAR_LOOKUP)
    lookup["aps_hf_wfi_rs_measure_model"][1] = model

    with pytest.raises(ValueError, match=re.escape(message)):
        power.SensorConstants.from_yaml(_write(tmp_path, lookup))


def test_temperature_sections_override_the_base(tmp_path: Path) -> None:
    lookup = copy.deepcopy(SCALAR_LOOKUP)
    lookup["temperatures"] = {
        25: {"idle_currents": {"ARMED": 90.0e-3, "READY": 21.759e-3}},
        105: {"idle_currents": {"ARMED": 113.2e-3, "READY": 30.0e-3}},
    }
    path = _write(tmp_path, lookup)

    assert power.SensorConstants.from_yaml(path, 25).idle_currents[
        a2.IdleState.ARMED
    ].total == pytest.approx(90.0e-3)
    assert power.SensorConstants.from_yaml(path, 105).idle_currents[
        a2.IdleState.ARMED
    ].total == pytest.approx(113.2e-3)
    assert power.SensorConstants.from_yaml(path, 25).available_temperatures == (25, 105)


def test_a_temperature_the_file_lacks_is_rejected(tmp_path: Path) -> None:
    lookup = copy.deepcopy(SCALAR_LOOKUP)
    lookup["temperatures"] = {25: {"idle_currents": {"ARMED": 97.949e-3, "READY": 21.759e-3}}}

    with pytest.raises(ValueError, match=r"no .*entry for -40"):
        power.SensorConstants.from_yaml(_write(tmp_path, lookup), -40)
