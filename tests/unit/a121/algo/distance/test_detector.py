# Copyright (c) Acconeer AB, 2022
# All rights reserved

from acconeer.exptool import a121
from acconeer.exptool.a121.algo import distance


def test_update_processor_mode():

    processor_spec = distance.ProcessorSpec(
        processor_config=distance.ProcessorConfig(
            processor_mode=distance.ProcessorMode.DISTANCE_ESTIMATION
        ),
        group_index=1,
        sensor_id=1,
        subsweep_indexes=[0],
    )
    processor_specs = [processor_spec, processor_spec]

    update_processor_specs = distance.Detector._update_processor_mode(
        processor_specs=processor_specs,
        processor_mode=distance.ProcessorMode.RECORDED_THRESHOLD_CALIBRATION,
    )

    for org_spec, updated_spec in zip(processor_specs, update_processor_specs):
        assert (
            org_spec.processor_config.processor_mode == distance.ProcessorMode.DISTANCE_ESTIMATION
        )
        assert (
            updated_spec.processor_config.processor_mode
            == distance.ProcessorMode.RECORDED_THRESHOLD_CALIBRATION
        )


def test_m_to_points():
    breakpoints_m = [0.5, 1.0, 1.5]
    step_length = 4

    actual_points = distance.Detector._m_to_points(
        breakpoints_m=breakpoints_m, step_length=step_length
    )

    assert actual_points[0] == 200
    assert actual_points[1] == 400
    assert actual_points[2] == 600


def test_select_prf():
    breakpoint = 600
    profile = a121.Profile.PROFILE_3

    actual_PRF = distance.Detector._select_prf(breakpoint=breakpoint, profile=profile)

    assert actual_PRF == a121.PRF.PRF_13_0_MHz


def test_limit_step_length():
    profile = a121.Profile.PROFILE_3
    user_limit = 2

    actual_step_length = distance.Detector._limit_step_length(
        profile=profile, user_limit=user_limit
    )
    assert actual_step_length == 2

    actual_step_length_no_user_limit = distance.Detector._limit_step_length(
        profile=profile, user_limit=None
    )
    assert actual_step_length_no_user_limit == 12
