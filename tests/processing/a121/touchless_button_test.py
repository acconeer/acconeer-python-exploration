# Copyright (c) Acconeer AB, 2022-2023
# All rights reserved


from acconeer.exptool import a121
from acconeer.exptool.a121._core import utils
from acconeer.exptool.a121.algo import touchless_button


def touchless_button_default(record: a121.H5Record) -> touchless_button.Processor:
    return touchless_button.Processor(
        sensor_config=record.session_config.sensor_config,
        processor_config=touchless_button.ProcessorConfig(),
        metadata=utils.unextend(record.extended_metadata),
    )


def touchless_button_both_ranges(record: a121.H5Record) -> touchless_button.Processor:
    processor_config = touchless_button.ProcessorConfig()
    processor_config.measurement_type = touchless_button.MeasurementType.CLOSE_AND_FAR_RANGE
    return touchless_button.Processor(
        sensor_config=record.session_config.sensor_config,
        processor_config=processor_config,
        metadata=utils.unextend(record.extended_metadata),
    )


def touchless_button_sensitivity(record: a121.H5Record) -> touchless_button.Processor:
    processor_config = touchless_button.ProcessorConfig()
    processor_config.measurement_type = touchless_button.MeasurementType.CLOSE_AND_FAR_RANGE
    processor_config.sensitivity_close = 2.2
    processor_config.sensitivity_far = 2.3
    return touchless_button.Processor(
        sensor_config=record.session_config.sensor_config,
        processor_config=processor_config,
        metadata=utils.unextend(record.extended_metadata),
    )


def touchless_button_patience(record: a121.H5Record) -> touchless_button.Processor:
    processor_config = touchless_button.ProcessorConfig()
    processor_config.measurement_type = touchless_button.MeasurementType.CLOSE_AND_FAR_RANGE
    processor_config.patience_close = 6
    processor_config.patience_far = 6
    return touchless_button.Processor(
        sensor_config=record.session_config.sensor_config,
        processor_config=processor_config,
        metadata=utils.unextend(record.extended_metadata),
    )


def touchless_button_calibration(record: a121.H5Record) -> touchless_button.Processor:
    processor_config = touchless_button.ProcessorConfig()
    processor_config.measurement_type = touchless_button.MeasurementType.CLOSE_AND_FAR_RANGE
    processor_config.calibration_interval_s = 23
    return touchless_button.Processor(
        sensor_config=record.session_config.sensor_config,
        processor_config=processor_config,
        metadata=utils.unextend(record.extended_metadata),
    )
