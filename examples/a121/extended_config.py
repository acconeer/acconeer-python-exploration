# Copyright (c) Acconeer AB, 2022-2024
# All rights reserved

import acconeer.exptool as et
from acconeer.exptool import a121


args = a121.ExampleArgumentParser().parse_args()
et.utils.config_logging(args)

client = a121.Client.open(**a121.get_client_args(args))

# Assign a sensor ID from a board or module or evaluation kit (EVK)
sensor_id = 1

# Create a SessionConfig with (e.g.) two groups sensor configurations
# SessionConfig is assigned 10 sweeps per frame in the first group, and 20 sweeps per frame in the second group
# Unassigned configuration parameters will be assigned a default value
session_config = a121.SessionConfig(
    [
        {  # First group
            sensor_id: a121.SensorConfig(
                sweeps_per_frame=10,
            )
        },
        {  # Second group
            sensor_id: a121.SensorConfig(
                sweeps_per_frame=20,
            )
        },
    ],
    extended=True,
)

client.setup_session(session_config)
client.start_session()

for i in range(3):
    extended_result = client.get_next()
    # The result will contain two groups, each containing the output from one of the two SensorConfigs created above
    # Here is how to get the result from the first group
    result_first_group = extended_result[0]

    # Get result for the selected sensor ID (It corresponds to the SensorConfig in the first group)
    result_first_sensor_config = result_first_group[sensor_id]

    # Extract the 'frame' data from first sensor result
    first_frame = result_first_sensor_config.frame

    # Extract the 'tick time' from second sensor result, time information when the data was captured
    result_second_group = extended_result[1]
    result_second_sensor_config = result_second_group[sensor_id]
    second_tick_time = result_second_sensor_config.tick_time

    print(f"\nExtended result {i + 1}:")
    print(extended_result)
    print(f"\nFrame from first sensor config {i + 1}:")
    print(first_frame)
    print(f"\nTick time from second sensor config {i + 1}:")
    print(second_tick_time)

client.stop_session()
client.close()
