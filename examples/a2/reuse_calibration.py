# Copyright (c) Acconeer AB, 2025-2026
# All rights reserved

from acconeer.exptool import a2


"""
First session - Setup session without calibration
                Sensor will calibrate during setup
"""

with a2.Client.open() as client:
    client.setup_session(a2.SessionConfig.default())

    calibration = client.calibration

    """
    client.calibrations_provided will be equal to False since calibration was not provided
    """
    print(
        f"Setup without provided calibration ==> calibration_provided = {client.calibration_provided}"
    )

    client.start_session()

    result = client.get_next()
    print("client tick:", result.tick)

    client.stop_session()


"""
Second session - Setup session with calibration
                 Sensor will reuse calibration and not calibrate during setup
"""

with a2.Client.open() as client:
    client.setup_session(a2.SessionConfig.default(), calibration=calibration)

    """
    client.calibrations_provided will be equal to True since calibration was provided
    """
    print(
        f"Setup with provided calibration ==> calibration_provided = {client.calibration_provided}"
    )

    client.start_session()

    result = client.get_next()
    print("client tick:", result.tick)

    client.stop_session()
