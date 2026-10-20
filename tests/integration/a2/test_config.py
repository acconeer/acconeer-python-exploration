# Copyright (c) Acconeer AB, 2026
# All rights reserved
import re
import typing as t

import attrs
import pytest
from hypothesis import HealthCheck, assume, event, given, settings
from hypothesis import strategies as st

from acconeer.exptool import a2
from acconeer.exptool.a2._core.entities.configs import sensor_config, subsweep_config


@pytest.mark.parametrize(
    ("config_class", "expected_num_fields"),
    [(a2.SessionConfig, 2), (a2.SensorConfig, 7), (a2.SubsweepConfig, 12)],
)
def test_session_config_num_fields(config_class: type, expected_num_fields: int) -> None:
    msg = (
        f"{config_class.__qualname__} was expected to have exactly {expected_num_fields} fields. "
        + "Update generators and expected number of fields in this test!"
    )

    field_names = [f.name for f in attrs.fields(config_class)]  # only the name more legible
    assert len(field_names) == expected_num_fields, msg


st_set_rate = st.floats(min_value=0.0, exclude_min=True, allow_infinity=False)


@st.composite
def valid_subsweep_config_generator(draw: st.DrawFn) -> a2.SubsweepConfig:
    start_point = draw(
        st.integers(subsweep_config.MIN_START_POINT, subsweep_config.MAX_START_POINT),
    )
    num_points = draw(
        st.integers(subsweep_config.MIN_NUM_POINTS, subsweep_config.MAX_NUM_POINTS),
    )
    step_length = draw(
        st.integers(subsweep_config.MIN_STEP_LENGTH, subsweep_config.MAX_STEP_LENGTH),
    )
    tx_antenna_mask = draw(
        st.integers(subsweep_config.MIN_ANTENNA_MASK, subsweep_config.MAX_TX_ANTENNA_MASK),
    )
    rx_antenna_mask = draw(
        st.integers(subsweep_config.MIN_ANTENNA_MASK, subsweep_config.MAX_RX_ANTENNA_MASK),
    )
    hwaas_exponent = draw(
        st.integers(subsweep_config.MIN_HWAAS_EXPONENT, subsweep_config.MAX_HWAAS_EXPONENT),
    )
    receiver_gain = draw(
        st.integers(subsweep_config.MIN_RECEIVER_GAIN, subsweep_config.MAX_RECEIVER_GAIN),
    )

    hwaas_fuzzy_margin = 20  # introduce some overlap to catch eventual future errors
    hwaas_max = draw(
        st.integers(subsweep_config.MIN_HWAAS, subsweep_config.MAX_HWAAS),
    )
    hwaas_min = draw(
        st.integers(
            subsweep_config.MIN_HWAAS,
            min(hwaas_max + hwaas_fuzzy_margin, subsweep_config.MAX_HWAAS),
        ),
    )

    profile = draw(st.from_type(a2.Profile))
    prf = draw(st.from_type(a2.PRF))
    enable_tx = draw(st.booleans())

    try:
        ssc = a2.SubsweepConfig(
            start_point=start_point,
            num_points=num_points,
            step_length=step_length,
            profile=profile,
            prf=prf,
            tx_antenna_mask=tx_antenna_mask,
            rx_antenna_mask=rx_antenna_mask,
            hwaas_max=hwaas_max,
            hwaas_min=hwaas_min,
            hwaas_exponent=hwaas_exponent,
            receiver_gain=receiver_gain,
            enable_tx=enable_tx,
        )
        ssc.validate()
    except a2.ValidationError:
        assume(False)
    else:
        return ssc


@st.composite
def valid_sensor_config_generator(draw: st.DrawFn) -> a2.SensorConfig:
    subsweeps = draw(
        st.lists(
            valid_subsweep_config_generator(),
            min_size=0,
            max_size=a2.SensorConfig.MAX_NUM_SUBSWEEPS + 1,
        )
    )
    sweeps_per_frame = draw(
        st.integers(sensor_config.MIN_SWEEPS_PER_FRAME - 1, sensor_config.MAX_SWEEPS_PER_FRAME + 1)
    )
    jitter_compensation = draw(st.booleans())
    sweep_rate = draw(st_set_rate | st.none())
    frame_rate = draw(st_set_rate | st.none())
    inter_frame_idle_state = draw(st.from_type(a2.IdleState))
    inter_sweep_idle_state = draw(st.from_type(a2.IdleState))

    try:
        sc = a2.SensorConfig(
            subsweeps=subsweeps,
            sweeps_per_frame=sweeps_per_frame,
            sweep_rate=sweep_rate,
            frame_rate=frame_rate,
            inter_frame_idle_state=inter_frame_idle_state,
            inter_sweep_idle_state=inter_sweep_idle_state,
            jitter_compensation=jitter_compensation,
        )
        sc.validate()
    except ValueError:
        assume(False)
    except a2.ValidationError:
        assume(False)
    else:
        return sc


@st.composite
def valid_session_config_generator(draw: st.DrawFn) -> a2.SessionConfig:
    sensor_configs = draw(st.lists(valid_sensor_config_generator(), min_size=1, max_size=3))

    update_rate: float | None
    if all(sc.frame_rate is None for sc in sensor_configs):
        update_rate = draw(st_set_rate)
    else:
        update_rate = draw(st.none())

    try:
        sc = a2.SessionConfig(sensor_configs, update_rate)
        sc.validate()
    except ValueError:
        assume(False)
    except a2.ValidationError:
        assume(False)
    else:
        return sc


@settings(
    # many examples are thrown away because of validation
    suppress_health_check=[HealthCheck.filter_too_much, HealthCheck.too_slow],
    # every example sets up a session on the Exploration Server
    deadline=None,
)
@given(valid_session_config=valid_session_config_generator())
def test_validation_is_aligned_with_exploration_server(
    valid_session_config: a2.SessionConfig,
    fuzzing_a2_exploration_server: t.Any,
    fuzzing_a2_worker_tcp_port: int,
) -> None:
    try:
        with a2.Client.open(ip_address="localhost", tcp_port=fuzzing_a2_worker_tcp_port) as c:
            c.setup_session(valid_session_config)
    except a2.ServerError as se:
        if re.match(r".*Config: The maximum (frame|sweep) rate is \d+(?:\.\d+)?\s?Hz.*", str(se)):
            # we let these discrepancies slip as we do not
            # want to duplicate the expected-rate calculations
            event("Maximum sweep/frame rate")
        else:
            ae = AssertionError("A valid SessionConfig resulted in ES error")
            ae.add_note(f"ES error message: {se}")
            ae.add_note(f"ET: {valid_session_config}")
            raise ae
