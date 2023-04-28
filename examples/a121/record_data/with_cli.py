# Copyright (c) Acconeer AB, 2022-2023
# All rights reserved

import acconeer.exptool as et
from acconeer.exptool import a121


parser = a121.ExampleArgumentParser()
parser.add_argument("--output-file", required=True)
parser.add_argument("--num-frames", required=True, type=int)
args = parser.parse_args()
et.utils.config_logging(args)

client = a121.Client.open(**a121.get_client_args(args))

# Session setup, just like the other examples.
config = a121.SessionConfig()
client.setup_session(config)

# Here we create and attach a H5Recorder to the Client.
# The H5Recorder will sample all frames retrieved in the client.
# Once the "with"-block have been exited, the H5Recorder will
# wrap up and close the file.
with a121.H5Recorder(args.output_file, client):
    client.start_session()

    for i in range(args.num_frames):
        # Client will send its Results to the H5Recorder.
        client.get_next()
        print(f"Result {i + 1}/{args.num_frames} was sampled")

    client.stop_session()

client.close()
