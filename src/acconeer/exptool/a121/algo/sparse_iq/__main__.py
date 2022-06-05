import acconeer.exptool as et
from acconeer.exptool import a121

from . import Processor, ProcessorConfig


parser = a121.ExampleArgumentParser()
parser.add_argument("--sensor", type=int, default=1)
args = parser.parse_args()
et.utils.config_logging(args)  # type: ignore[attr-defined]

client = a121.Client(**a121.get_client_args(args))
client.connect()

sensor_config = a121.SensorConfig()
session_config = a121.SessionConfig({args.sensor: sensor_config})

metadata = client.setup_session(session_config)
assert isinstance(metadata, a121.Metadata)

processor_config = ProcessorConfig()

processor = Processor(
    sensor_config=sensor_config,
    metadata=metadata,
    processor_config=processor_config,
)

client.start_session()

interrupt_handler = et.utils.ExampleInterruptHandler()  # type: ignore[attr-defined]
print("Press Ctrl-C to end session")

while not interrupt_handler.got_signal:
    result = client.get_next()
    assert isinstance(result, a121.Result)

    processor_result = processor.process(result)

    ...

print("Disconnecting...")
client.disconnect()
