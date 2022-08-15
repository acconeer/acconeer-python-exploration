# Copyright (c) Acconeer AB, 2022
# All rights reserved

import acconeer.exptool as et
from acconeer.exptool import a121


args = a121.ExampleArgumentParser().parse_args()
et.utils.config_logging(args)

client = a121.Client(**a121.get_client_args(args))
client.connect()

session_config = a121.SessionConfig(
    [
        {
            1: a121.SensorConfig(
                sweeps_per_frame=10,
            )
        },
        {
            1: a121.SensorConfig(
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

    print(f"\nExtended result {i + 1}:")
    print(extended_result)

client.stop_session()
client.disconnect()
