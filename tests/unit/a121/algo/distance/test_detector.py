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
