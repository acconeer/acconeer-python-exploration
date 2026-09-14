# Copyright (c) Acconeer AB, 2026
# All rights reserved
import inspect
import re
import typing as t

import attrs
import pytest
from hypothesis import HealthCheck, assume, event, given, settings
from hypothesis import strategies as st

from acconeer.exptool import a121
from acconeer.exptool.a121._core.entities.configs.subsweep_config import SPARSE_IQ_PPC
from acconeer.exptool.a121._core.utils import is_divisor_of, is_multiple_of


@pytest.mark.parametrize(
    ("config_class", "expected_num_fields"),
    [(a121.SessionConfig, 3), (a121.SensorConfig, 20), (a121.SubsweepConfig, 11)],
)
def test_session_config_num_fields(config_class: type, expected_num_fields: int) -> None:
    msg = (
        f"{config_class.__qualname__} was expected to have exactly {expected_num_fields} fields. "
        + "Update generators and expected number of fields in this test!"
    )

    if attrs.has(config_class):
        field_names = [f.name for f in attrs.fields(config_class)]
    else:
        # SensorConfig/SessionConfig aren't attrs classes, so their constructor's
        # parameters are the closest equivalent to a field list.
        field_names = [
            name for name in inspect.signature(config_class.__init__).parameters if name != "self"
        ]

    assert len(field_names) == expected_num_fields, msg


# Rates near 0 Hz or huge (order 1e10+) Hz both overflow the Exploration
# Server's internal tick conversion (a firmware bug outside this SDK's
# control) instead of being cleanly rejected: a period is converted to
# ticks at a ~24 MHz internal clock, and that product overflows an
# unsigned int for rates below ~0.006 Hz. 0.1 Hz keeps well clear of
# that with margin, and 1e5 Hz is already two orders of magnitude above
# any rate a real sensor accepts, so neither cuts into the range that
# exercises the server's own (cleanly rejected) maximum-rate check.
st_set_rate = st.floats(min_value=1e-1, max_value=1e5, allow_infinity=False)

# Precomputed once, rather than drawn-and-filtered, since divisors/multiples of
# SPARSE_IQ_PPC are a small fraction of any integer range and would otherwise trip
# Hypothesis' filter_too_much health check.
_VALID_STEP_LENGTHS = [
    step_length
    for step_length in range(1, 3 * SPARSE_IQ_PPC + 1)
    if is_divisor_of(SPARSE_IQ_PPC, step_length) or is_multiple_of(SPARSE_IQ_PPC, step_length)
]


@st.composite
def valid_subsweep_config_generator(draw: st.DrawFn) -> a121.SubsweepConfig:
    # Kept small: num_points/step_length/start_point all feed into the measured end
    # point, which every PRF (down to ~3.1 m for PRF_19_5_MHz) caps. Wide ranges here
    # make most draws fail that check, tanking generation speed.
    start_point = draw(st.integers(min_value=-400, max_value=200))
    num_points = draw(st.integers(min_value=1, max_value=200))
    step_length = draw(st.sampled_from(_VALID_STEP_LENGTHS))
    profile = draw(st.from_type(a121.Profile))
    prf = draw(st.from_type(a121.PRF))
    hwaas = draw(st.integers(min_value=1, max_value=a121.SubsweepConfig.MAX_HWAAS))
    receiver_gain = draw(st.integers(min_value=0, max_value=23))
    enable_tx = draw(st.booleans())
    enable_loopback = draw(st.booleans())
    phase_enhancement = draw(st.booleans())
    iq_imbalance_compensation = draw(st.booleans())

    try:
        ssc = a121.SubsweepConfig(
            start_point=start_point,
            num_points=num_points,
            step_length=step_length,
            profile=profile,
            prf=prf,
            hwaas=hwaas,
            receiver_gain=receiver_gain,
            enable_tx=enable_tx,
            enable_loopback=enable_loopback,
            phase_enhancement=phase_enhancement,
            iq_imbalance_compensation=iq_imbalance_compensation,
        )
        ssc.validate()
    except (ValueError, a121.ValidationError):
        assume(False)
    else:
        return ssc


@st.composite
def valid_sensor_config_generator(draw: st.DrawFn) -> a121.SensorConfig:
    subsweeps = draw(st.lists(valid_subsweep_config_generator(), min_size=1, max_size=6))
    # SensorConfig.validate() requires non-increasing PRF across subsweeps. Reordering
    # (rather than drawing already-sorted PRFs) keeps each subsweep's PRF independently
    # and uniformly distributed while still satisfying the constraint by construction —
    # relying on the random order to already be sorted would reject ~99% of 6-subsweep
    # draws.
    subsweeps = sorted(subsweeps, key=lambda ss: ss.prf.frequency, reverse=True)

    double_buffering = draw(st.booleans())
    # Bound sweeps_per_frame by the required-buffer-usage check (sum(num_points) *
    # sweeps_per_frame vs. the sensor buffer) so most draws are valid instead of
    # relying on rejecting oversized ones.
    buffer_size_available = 2047 if double_buffering else 4095
    total_num_points = sum(ss.num_points for ss in subsweeps)
    max_sweeps_per_frame = max(1, buffer_size_available // total_num_points)
    sweeps_per_frame = draw(st.integers(min_value=0, max_value=max_sweeps_per_frame))

    sweep_rate = draw(st_set_rate | st.none())
    frame_rate = draw(st_set_rate | st.none())
    continuous_sweep_mode = draw(st.booleans())
    inter_frame_idle_state = draw(st.from_type(a121.IdleState))
    inter_sweep_idle_state = draw(st.from_type(a121.IdleState))

    try:
        sc = a121.SensorConfig(
            subsweeps=subsweeps,
            sweeps_per_frame=sweeps_per_frame,
            sweep_rate=sweep_rate,
            frame_rate=frame_rate,
            continuous_sweep_mode=continuous_sweep_mode,
            double_buffering=double_buffering,
            inter_frame_idle_state=inter_frame_idle_state,
            inter_sweep_idle_state=inter_sweep_idle_state,
        )
        sc.validate()
    except (ValueError, a121.ValidationError):
        assume(False)
    else:
        return sc


@st.composite
def valid_session_config_generator(draw: st.DrawFn) -> a121.SessionConfig:
    st_group = st.dictionaries(
        keys=st.integers(min_value=1, max_value=8),
        values=valid_sensor_config_generator(),
        min_size=1,
        max_size=3,
    )
    groups = draw(st.lists(st_group, min_size=1, max_size=3))
    sensor_configs = [sensor_config for group in groups for sensor_config in group.values()]

    update_rate: float | None
    if all(sc.frame_rate is None for sc in sensor_configs):
        update_rate = draw(st_set_rate)
    else:
        update_rate = draw(st.none())

    try:
        sc = a121.SessionConfig(groups, update_rate=update_rate)
        sc.validate()
    except (ValueError, a121.ValidationError):
        assume(False)
    else:
        return sc


@settings(
    # many examples are thrown away because of validation
    suppress_health_check=[HealthCheck.filter_too_much],
)
@given(valid_session_config=valid_session_config_generator())
def test_validation_is_aligned_with_exploration_server(
    valid_session_config: a121.SessionConfig,
    fuzzing_a121_exploration_server: t.Any,
    fuzzing_a121_worker_tcp_port: int,
) -> None:
    try:
        with a121.Client.open(ip_address="localhost", tcp_port=fuzzing_a121_worker_tcp_port) as c:
            c.setup_session(valid_session_config)
    except a121.ServerError as se:
        if re.match(
            r".*(The maximum (frame|sweep) rate is \d+(?:\.\d+)?\s?(?:Hz)?"
            r"|Invalid (frame|sweep)_rate).*",
            str(se),
        ):
            # we let these discrepancies slip as we do not
            # want to duplicate the expected-rate calculations
            event("Maximum sweep/frame rate")
        elif re.match(r".*Config, invalid sensor_id.*", str(se)):
            # Which sensor_ids are valid is a property of the connected
            # hardware, not of the config, so the SDK can't replicate this
            # check without knowing what's physically attached.
            event("Invalid sensor_id")
        else:
            ae = AssertionError("A valid SessionConfig resulted in ES error")
            ae.add_note(f"ES error message: {se}")
            ae.add_note(f"ET: {valid_session_config}")
            raise ae
