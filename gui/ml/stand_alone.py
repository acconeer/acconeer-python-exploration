import os
import sys

from acconeer.exptool import imock, utils
from acconeer.exptool.clients import SocketClient, SPIClient, UARTClient


imock.add_mock_packages(imock.GRAPHICS_LIBS)

# If you run stand_alone.py from ..gui/ml
sys.path.append(os.path.realpath(os.path.join(os.path.dirname(__file__), "../../")))

# If you run stand_alone from another folder
path_to_exploration_tool = "/home/pi/acconeer-exploration-tool"

sys.path.append(os.path.realpath(path_to_exploration_tool))

try:
    import gui.ml.keras_processing as kp
    import gui.ml.feature_processing as feature_proc
except Exception:
    print("Failed to import deeplearning libraries, please specify acconeer-exploration-folder!")
    exit(1)


def main():
    parser = utils.ExampleArgumentParser()
    add_args(parser)
    args = parser.parse_args()

    if args.model_file_name:
        filename = args.model_file_name
    else:
        print("Not implemented!")
        sys.exit(1)

    keras_proc = kp.MachineLearning()
    model_data = keras_proc.load_model(filename)

    print(model_data["message"].replace("<br>", "\n"))

    if not model_data["loaded"]:
        return False

    config = model_data["sensor_config"]
    feature_list = model_data["feature_list"]
    frame_settings = model_data["frame_settings"]

    print("\nFeature detection settings:")
    for setting in frame_settings:
        if "label" in setting:
            continue
        print("{}: {}".format(setting, frame_settings[setting]))

    feature_process = feature_proc.FeatureProcessing(config)
    feature_process.set_feature_list(feature_list)
    feature_process.set_frame_settings(frame_settings)

    utils.config_logging(args)

    if args.socket_addr:
        client = SocketClient(args.socket_addr)
    elif args.spi:
        client = SPIClient()
    else:
        port = args.serial_port or utils.autodetect_serial_port()
        client = UARTClient(port)

    session_info = client.setup_session(config)

    interrupt_handler = utils.ExampleInterruptHandler()
    print("\nPress Ctrl-C to end session")

    client.start_session()

    while not interrupt_handler.got_signal:
        info, sweep = client.get_next()

        data = {
            "sweep_data": sweep,
            "sensor_config": config,
            "session_info": session_info,
        }

        ml_frame_data = feature_process.feature_extraction(data)
        feature_map = ml_frame_data["current_frame"]["feature_map"]
        complete = ml_frame_data["current_frame"]["frame_complete"]

        if complete and feature_map is not None:
            predict = keras_proc.predict(feature_map)[0]
            label = predict["prediction"]
            confidence = predict["confidence"]
            print("Prediction: {:10s} ({:6.2f}%)\r".format(label, confidence * 100), end="")

    print("Disconnecting...")
    client.disconnect()


def add_args(parser):
    parser.add_argument("--load-model", dest="model_file_name",
                        help="Load model", default=None)


if __name__ == "__main__":
    main()
