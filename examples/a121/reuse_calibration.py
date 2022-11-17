# Copyright (c) Acconeer AB, 2022
# All rights reserved

import acconeer.exptool as et
from acconeer.exptool import a121


args = a121.ExampleArgumentParser().parse_args()
et.utils.config_logging(args)

"""
First session - Setup session without calibration
                Sensor will calibrate during setup
"""

client = a121.Client(**a121.get_client_args(args))
client.connect()

sensor_config = a121.SensorConfig()
client.setup_session(sensor_config)

calibrations = client.calibrations

"""
client.calibrations_provided will be equal to {1: False} since calibration was not provided
"""
print(f"Setup without provided calibration {client.calibrations_provided}")

client.disconnect()

"""
Second session - Setup session with calibration
                 Sensor will reuse calibration and not calibrate during setup
"""

client = a121.Client(**a121.get_client_args(args))
client.connect()

sensor_config = a121.SensorConfig()
client.setup_session(sensor_config, calibrations)

"""
client.calibrations_provided will be equal to {1: True} since calibration was provided
"""
print(f"Setup with provided calibration {client.calibrations_provided}")

client.disconnect()
