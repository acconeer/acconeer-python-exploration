# Copyright (c) Acconeer AB, 2023-2024
# All rights reserved

"""
This example will demonstrate how one can post process already recorded SparseIQ data
with distance or presence (the other algorithms are similar).

Note that some algorithms requires the data to have been recorded with specific settings.
This means that all recorded data cannot be processed by all algorithms.

Usage:

    python path/to/post_process_sparse_iq.py <path/to/h5 file> --processing distance
"""

import argparse
import pathlib

from acconeer.exptool import a121
from acconeer.exptool.a121.algo import distance, presence


def presence_processing(record: a121.H5Record) -> None:
    # User-defined post-processing parameters.
    # See these Presence resources for more information:
    #
    # Presence processor example:
    #   https://github.com/acconeer/acconeer-python-exploration/blob/master/examples/a121/algo/presence/processor.py
    # Presence doc page:
    #   https://docs.acconeer.com/en/latest/exploration_tool/algo/a121/detectors/presence_detection.html
    processor_config = presence.ProcessorConfig(intra_enable=True)

    # Get needed metadata of recorded data from the H5Record
    # If your record contains "extended" data, an error will be raised here.
    record_sensor_config = record.session_config.sensor_config
    metadata = record.metadata

    # Each algorithm has requirements on the data it processes. validate checks these requirements
    processor_config.validate(record_sensor_config)

    # Create a processor with metadata from recording and the user-defined processing parameters
    processor = presence.Processor(
        sensor_config=record_sensor_config,
        metadata=metadata,
        processor_config=processor_config,
    )

    # Post-process all recorded results and print the intra presence score
    for idx, result in enumerate(record.results):
        processor_result = processor.process(result)
        print(f"{idx: >5}: {processor_result.intra_presence_score}")


def distance_processing(record: a121.H5Record) -> None:
    # User-defined post-processing parameters.
    # See these Distance resources for more information:
    #
    # Distance processor example:
    #   https://github.com/acconeer/acconeer-python-exploration/blob/master/examples/a121/algo/distance/processor.py
    # Distance doc page:
    #   https://docs.acconeer.com/en/latest/exploration_tool/algo/a121/detectors/distance_detection.html
    processor_config = distance.ProcessorConfig(
        processor_mode=distance.ProcessorMode.DISTANCE_ESTIMATION,
        threshold_method=distance.ThresholdMethod.CFAR,
        measurement_type=distance.MeasurementType.FAR_RANGE,
        reflector_shape=distance.ReflectorShape.GENERIC,
        threshold_sensitivity=0.5,
        fixed_threshold_value=100.0,
        fixed_strength_threshold_value=0.0,
    )

    # Get needed metadata of recorded data from the H5Record.
    # If your record contains "extended" data, an error will be raised here.
    record_sensor_config = record.session_config.sensor_config
    metadata = record.metadata

    # Each algorithm has requirements on the data it processes. validate checks these requirements
    processor_config.validate(record_sensor_config)

    # Create a processor with metadata from recording and the user-defined processing parameters
    all_subsweep_indexes = list(range(record_sensor_config.num_subsweeps))
    processor = distance.Processor(
        sensor_config=record_sensor_config,
        metadata=metadata,
        processor_config=processor_config,
        subsweep_indexes=all_subsweep_indexes,
    )

    # Post-process all recorded results and print the estimated distances
    for idx, result in enumerate(record.results):
        processor_result = processor.process(result)
        print(f"{idx: >5}: {processor_result.estimated_distances}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("file", type=pathlib.Path, help="Path to the recorded .h5 file")
    parser.add_argument(
        "--processing",
        type=str,
        choices=["distance", "presence"],
        help="The post-processing to use",
    )

    args = parser.parse_args()

    with a121.open_record(args.file) as record:
        if args.processing == "distance":
            distance_processing(record)
        elif args.processing == "presence":
            presence_processing(record)
        else:
            print(f"No post-processing available for algorithm {args.processing!r}")


if __name__ == "__main__":
    main()
