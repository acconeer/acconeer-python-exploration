# Copyright (c) Acconeer AB, 2022-2023
# All rights reserved

from acconeer.exptool import a121


# Client creation
client = a121.Client.open(ip_address="192.168.0.1")

# Session setup, just like the other examples.
config = a121.SessionConfig()
client.setup_session(config)


# Here we specify the file name for the H5Recorder.
# The H5Recorder is an object that saves frames directly to a H5-file.
filename = "data.h5"

# Here we create and attach a H5Recorder to the Client.
# The H5Recorder will sample all frames retrieved in the client.
# Once the "with"-block have been exited, the H5Recorder will
# wrap up and close the file.
with a121.H5Recorder(filename, client):
    client.start_session()

    n = 10
    for i in range(n):
        # Client will send its Results to the H5Recorder.
        client.get_next()
        print(f"Result {i + 1}/{n} was sampled")

    client.stop_session()

client.close()

with a121.open_record(filename) as record:
    print(record)
