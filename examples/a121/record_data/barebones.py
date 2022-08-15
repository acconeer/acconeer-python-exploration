# Copyright (c) Acconeer AB, 2022
# All rights reserved

from acconeer.exptool import a121


# Here we create a H5Recorder.
# The H5Recorder is an object that saves frames directly to a H5-file.
filename = "data.h5"
h5_recorder = a121.H5Recorder(filename)

# Client creation
client = a121.Client(ip_address="192.168.0.1")
client.connect()

# Session setup, just like the other examples.
config = a121.SessionConfig()
client.setup_session(config)

# Here we send the H5Recorder to the Client.
# After this call, the client is responsible for the H5Recorder.
# The Client will automatically close the file when
# "stop_session" is called.
client.start_session(recorder=h5_recorder)

n = 10
for i in range(n):
    # Client will send its Results to the H5Recorder.
    client.get_next()
    print(f"Result {i + 1}/{n} was sampled")

client.stop_session()
client.disconnect()

with a121.open_record(filename) as record:
    print(record)
