# Copyright (c) Acconeer AB, 2023-2025
# All rights reserved

from __future__ import annotations

import acconeer.exptool as et
from acconeer.exptool import a121
from acconeer.exptool.a121._core.entities.configs.config_enums import PRF, IdleState, Profile
from acconeer.exptool.a121.algo.sparse_iq import AmplitudeMethod, Processor, ProcessorConfig


def main():
    args = a121.ExampleArgumentParser().parse_args()
    et.utils.config_logging(args)

    client = a121.Client.open(**a121.get_client_args(args))
    processor_config = ProcessorConfig()

    processor_config.amplitude_method = AmplitudeMethod.COHERENT  # Either COHERENT or FFTMAX
    sensor_id = 1

    sensor_config = a121.SensorConfig(
        sweeps_per_frame=8,
        sweep_rate=None,
        frame_rate=None,
        inter_frame_idle_state=IdleState.READY,
        inter_sweep_idle_state=IdleState.READY,
        continuous_sweep_mode=False,
        double_buffering=False,
        subsweeps=[
            # Generate 3 subsweep configurations
            a121.SubsweepConfig(start_point=70),
            a121.SubsweepConfig(),
            a121.SubsweepConfig(profile=Profile.PROFILE_2),
        ],
    )

    # Multiple subsweep configuration can be assigned in single group SensorConfig
    # through 'subweeps' fields shown above or in these way below
    sensor_config.subsweeps[0].num_points = 140
    sensor_config.subsweeps[1].prf = PRF.PRF_15_6_MHz

    # Create a SessionConfig with (e.g.) two groups SensorConfig
    # First group will contain multiple subsweeps, second group will contain single subsweep
    # Multiple group configurations are required when certain parameters cannot be configured in subsweep config
    session_config = a121.SessionConfig(
        [
            {
                sensor_id: sensor_config,
            },
            {
                sensor_id: a121.SensorConfig(
                    sweeps_per_frame=20,
                )
            },
        ],
        extended=True,
    )
    client.setup_session(session_config)
    client.start_session()
    processor = Processor(session_config=session_config, processor_config=processor_config)

    interrupt_handler = et.utils.ExampleInterruptHandler()
    print("Press Ctrl-C to end session")

    while not interrupt_handler.got_signal:
        results = client.get_next()
        result_sensor_configs = processor.process(results=results)
        result_first_sensor_config = result_sensor_configs[0][sensor_id]
        result_third_subsweep = result_first_sensor_config[2]
        # Sparse IQ results contain amplitudes, phases, and distance velocity
        try:
            print("Amplitudes results of 3rd subsweep from first group ")
            print(result_third_subsweep.amplitudes)

            print("Distance velocity results of 1st subsweep from second group ")
            print(result_sensor_configs[1][sensor_id][0].distance_velocity_map)
        except et.PGProccessDiedException:
            break

    print("Disconnecting...")
    client.close()


if __name__ == "__main__":
    main()
