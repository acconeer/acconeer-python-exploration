import acconeer.exptool as et
from acconeer.exptool import a121

from . import DistanceDetector, DistanceDetectorConfig


parser = a121.ExampleArgumentParser()
parser.add_argument("--sensor", type=int, default=1)
args = parser.parse_args()
et.utils.config_logging(args)  # type: ignore[attr-defined]

client = a121.Client(**a121.get_client_args(args))
client.connect()

detector_config = DistanceDetectorConfig()

detector = DistanceDetector(
    client=client,
    sensor_id=args.sensor,
    detector_config=detector_config,
)

detector.calibrate()
detector.start()

interrupt_handler = et.utils.ExampleInterruptHandler()  # type: ignore[attr-defined]
print("Press Ctrl-C to end session")

while not interrupt_handler.got_signal:
    detector_result = detector.get_next()

    print(detector_result, "\n")

print("Disconnecting...")
detector.stop()
client.disconnect()
