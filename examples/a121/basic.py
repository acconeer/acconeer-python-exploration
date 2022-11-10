# Copyright (c) Acconeer AB, 2022
# All rights reserved

from acconeer.exptool import a121


# Client is an object that is used to interact with the sensor.
client = a121.Client(
    # ip_address="<ip address of host (like a RPi). E.g. 192.168.XXX.YYY>",
    # or
    # serial_port="<serial port of module. E.g. COM3 or /dev/ttyUSBx for Window/Linux>",
    # or
    # usb_device=True,
)

# Establishes a connection to the server running on the sensor.
client.connect()

# Once the client is connected, information about the server can be accessed.
print("Server Info:")
print(client.server_info)

# In order to get radar data from the server, we need to start a session.

# To be able to start a session, we must first configure the session
sensor_config = a121.SensorConfig()
sensor_config.num_points = 6
sensor_config.sweeps_per_frame = 4
sensor_config.hwaas = 16
client.setup_session(sensor_config)

# Now we are ready to start it:
client.start_session()

n = 5
for i in range(n):
    # Data is retrieved from the sensor with "get_next".
    result = client.get_next()

    print(f"Result {i + 1}:")
    print(result)

# When we are done, we should close the connection to the server.
client.disconnect()
