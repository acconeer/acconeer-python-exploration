# Copyright (c) Acconeer AB, 2024-2026
# All rights reserved

from acconeer.exptool import a2


# Client creation
client = a2.Client.open(
    # Leaving this comment as is will automatically search for an
    # EVK connected via USB. Otherwise, one of the following should be specified:
    #
    # ip_address="<ip address of host (like a RPi). E.g. 192.168.XXX.YYY>",
    # or
    # serial_port="<serial port of module. E.g. COM3 or /dev/ttyUSBx for Window/Linux>",
    # or
    # usb_device=True,
    # or
    # mock=True,
)

# Here we specify if we want to use more than one sensor or the same sensor in different groups. Hence the list.
sensor_config = a2.SensorConfig.single_subsweep(
    start_point=80,
    num_points=30,
    step_length=12,
    profile=a2.Profile.PROFILE_3,
    tx_antenna_mask=0b011,
    rx_antenna_mask=0b0111,
    hwaas_min=10,
    hwaas_max=50,
    hwaas_exponent=2,
    receiver_gain=10,
    enable_tx=True,
    sweeps_per_frame=1,
)

# Session setup, just like the other examples.
session_config = a2.SessionConfig(sensor_configs=[sensor_config], update_rate=None)
client.setup_session(session_config)

# Here we specify the file name for the H5Recorder.
# The H5Recorder is an object that saves frames directly to a H5-file.
filename = "data.h5"

# Here we create and attach a H5Recorder to the Client.
# The H5Recorder will sample all frames retrieved in the client.
# Once the "with"-block have been exited, the H5Recorder will
# wrap up and close the file.
with a2.H5Recorder(filename, client):
    client.start_session()

    n = 10
    for i in range(n):
        # Client will send its Results to the H5Recorder.
        client.get_next()
        print(f"Result {i + 1}/{n} was sampled")

    client.stop_session()

client.close()

with a2.open_record(filename) as record:
    print(record)
