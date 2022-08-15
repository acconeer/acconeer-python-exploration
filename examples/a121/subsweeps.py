# Copyright (c) Acconeer AB, 2022
# All rights reserved

import acconeer.exptool as et
from acconeer.exptool import a121


args = a121.ExampleArgumentParser().parse_args()
et.utils.config_logging(args)

client = a121.Client(**a121.get_client_args(args))
client.connect()

sensor_config = a121.SensorConfig(
    subsweeps=[
        a121.SubsweepConfig(
            start_point=25,
            step_length=2,
            num_points=30,
            profile=a121.Profile.PROFILE_1,
            hwaas=10,
        ),
        a121.SubsweepConfig(
            start_point=75,
            step_length=4,
            num_points=25,
            profile=a121.Profile.PROFILE_3,
            hwaas=20,
        ),
    ],
    sweeps_per_frame=10,
)

client.setup_session(sensor_config)
client.start_session()

for i in range(3):
    result = client.get_next()

    print(f"\nResult {i + 1} subframes:")
    print(result.subframes)

client.stop_session()
client.disconnect()
