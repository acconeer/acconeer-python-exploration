import sys

from acconeer_utils.clients import SocketClient, SPIClient, UARTClient
from acconeer_utils import example_utils

import keras_processing as kp
import feature_processing as feature_proc


def main():
    parser = example_utils.ExampleArgumentParser(num_sens=2)
    add_args(parser)
    args = parser.parse_args()

    if args.model_file_name:
        filename = args.model_file_name
    else:
        print("Not implemented!")
        sys.exit(1)

    keras_proc = kp.MachineLearning()
    model_data = keras_proc.load_model(filename)

    print(model_data["message"])

    if not model_data["loaded"]:
        return False

    config = model_data["sensor_config"]
    feature_list = model_data["feature_list"]
    frame_settings = model_data["frame_settings"]

    feature_process = feature_proc.FeatureProcessing(config)
    feature_process.set_feature_list(feature_list)
    feature_process.set_frame_settings(frame_settings)

    example_utils.config_logging(args)

    if args.socket_addr:
        client = SocketClient(args.socket_addr)
    elif args.spi:
        client = SPIClient()
    else:
        port = args.serial_port or example_utils.autodetect_serial_port()
        client = UARTClient(port)

    session_info = client.setup_session(config)

    interrupt_handler = example_utils.ExampleInterruptHandler()
    print("Press Ctrl-C to end session")

    client.start_streaming()

    while not interrupt_handler.got_signal:
        info, sweep = client.get_next()

        data = {
            "iq_data": sweep,
            "sensor_config": config,
            "session_info": session_info,
        }

        ml_frame_data = feature_process.feature_extraction(data)
        feature_map = ml_frame_data["current_frame"]["feature_map"]
        complete = ml_frame_data["current_frame"]["frame_complete"]

        if complete and feature_map is not None:
            predict = keras_proc.predict(feature_map)[0]
            prediction_label = predict["prediction"]
            print(prediction_label)

    print("Disconnecting...")
    client.disconnect()


def add_args(parser):
    parser.add_argument("--load-train-set", dest="train_data",
                        help="Load training data", default="")
    parser.add_argument("--evaluate", dest="evaluate",
                        help="Sensor", default="")
    parser.add_argument("--save-best", dest="save_best",
                        help="Save model", default=None)
    parser.add_argument("--save-model", dest="model_save_name",
                        help="Save model", default=None)
    parser.add_argument("--load-model", dest="model_file_name",
                        help="Load model", default=None)
    parser.add_argument("-load-eval-set", dest="eval_data",
                        help="Sensor", action="store_true")


if __name__ == "__main__":
    main()
