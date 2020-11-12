import os
import traceback

import numpy as np
import yaml

from acconeer.exptool import recording


class KerasBase():
    def __init__(self):
        pass

    def init_model(self):
        print("Not Implemented")

    def set_optimizer(self, optimizer, loss="categorical_crossentropy"):
        print("Not Implemented")

    def train(self, train_params):
        print("Not Implemented")

    def set_learning_rate(self, rate):
        print("Not Implemented")

    def convert_to_categorical(self, labels, label_nr):
        print("Not Implemented")

    def eval(self, x, y):
        print("Not Implemented")

    def predict(self, x="internal"):
        print("Not Implemented")

    def load_model(self, file):
        print("Not Implemented")

    def save_model(self, file):
        print("Not Implemented")

    def clear_session(self):
        print("Not Implemented")

    def clear_model(self, reinit=False):
        print("Not Implemented")

    def get_current_session(self, graph=None):
        print("Not Implemented")

    def get_current_graph(self):
        print("Not Implemented")

    def set_current_session(self, session):
        print("Not Implemented")

    def count_variables(self):
        print("Not Implemented")


def get_file_list(files):
    try:
        if "yaml" in files.lower():
            file_list = files
        elif "npy" in files.lower():
            file_list = [files]
        else:
            file_list = get_files(files, match="npy")
    except Exception:
        traceback.print_exc()
        return None

    return file_list


def get_files(directory, match=None, exclude=None):
    list_of_files = []
    for (dirpath, dirnames, filenames) in os.walk(directory):
        for filename in filenames:
            append = False
            if match is not None and match in filename:
                append = True
            if exclude is not None and exclude in filename:
                append = False
            if match is None and exclude is None:
                append = True

            if ".npy" not in filename:
                append = False

            if append:
                list_of_files.append(os.sep.join([dirpath, filename]))

    if not len(list_of_files):
        print("No files found!")
    else:
        print("Found {} files!".format(len(list_of_files)))

    return list_of_files


def load_from_yaml(filename):
    try:
        with open(filename, 'r') as f_handle:
            data = yaml.load(f_handle, Loader=yaml.FullLoader)
    except Exception as e:
        print("Failed to load data\n", e)
    return data


def save_session_data(fname, data):
    if not fname:
        return

    sweep_data = data["sweep_data"]
    frame_data = data["frame_data"]

    packed_record = recording.pack(sweep_data)

    # Remove sensor_config object for saving
    frame_data.pop("sensor_config", None)

    data = {
        "sweep_data": packed_record,
        "frame_data": frame_data,
        "feature_list": data["feature_list"],
        "frame_settings": data["frame_settings"],
        "sensor_config": sweep_data.sensor_config_dump,
    }

    try:
        np.save(fname, data, allow_pickle=True)
    except Exception:
        traceback.print_exc()
        return False


def load_session_data(fname):
    if fname:
        try:
            load_data = np.load(fname, allow_pickle=True)
        except Exception:
            print("Failed to load file:\n", fname)
            traceback.print_exc()
            return False
    else:
        return False

    try:
        data = {}
        data["sweep_data"] = recording.unpack(load_data.item()["sweep_data"])
        data["frame_data"] = load_data.item()["frame_data"]
        data["feature_list"] = load_data.item()["feature_list"]
        data["frame_settings"] = load_data.item()["frame_settings"]
        # Fetch label of first feature frame
        data["label"] = data["frame_data"]["ml_frame_data"]["frame_list"][0]["label"]

        sweep_data_len = len(data["sweep_data"].data.data)
        number_of_feature_frames = len(data["frame_data"]["ml_frame_data"]["frame_list"])
        print("\n", fname)
        print("Found data with {} sweeps and {} feature frames.".format(
            sweep_data_len, number_of_feature_frames)
        )
    except Exception:
        print("Failed to parse data from file:\n", fname)
        traceback.print_exc()
        return False

    return data


def generate_calibration(filename=None):
    if filename is not None:
        try:
            data = np.load(filename, allow_pickle=True)
            frame_list = data.item()["frame_data"]["ml_frame_data"]["frame_list"]
            nr_frames = len(frame_list)
            calibration = np.zeros_like(frame_list[0]["feature_map"])
            for frame in frame_list:
                calibration += (frame["feature_map"] / nr_frames)
            return calibration
        except Exception:
            traceback.print_exc()
            print("Failed to load calibration file")
            return None
    else:
        print("No calibration file specified!")
        return None


def convert_time_series(feature_map, frame_info):
    frame_size = frame_info.get('frame_size')

    if feature_map is None:
        return None

    time_series = frame_info.get('time_series', 1)
    if time_series < 2:
        print("Cannot convert time series. Time series < 2!")
        return feature_map

    if len(feature_map.shape) == 1:
        print("Cannot convert time series. Feature map x dimension < 2!")
        return feature_map

    y, x = feature_map.shape

    if x != frame_size + time_series - 1:
        print("Cannot convert time series. Frame length {}, but should be {}".format(
            x, frame_size + time_series - 1)
        )
        return feature_map

    out_data = np.zeros((time_series, y, frame_size))
    for i in range(time_series):
        out_data[i, :, :] = feature_map[:, i:i+frame_size]

    return out_data


def add_args(parser):
    parser.add_argument(
        "-lm",
        "--load-model",
        dest="load_model_file",
        help="Load model",
        default=None,
    )
    parser.add_argument(
        "-sb",
        "--save-best-to",
        dest="save_best",
        help="Save best iteration to this folder",
        default=None,
    )
    parser.add_argument(
        "-sl",
        "--save-model-to",
        dest="save_model",
        help="Save last iteration to this file",
        default=None,
    )
    parser.add_argument(
        "-ll",
        "--load-model-layers",
        dest="model_layers_file",
        help="Load model layers",
        default=None,
    )
    parser.add_argument(
        "-t",
        "--trainfiles",
        dest="train_files",
        help="Load training files (yaml)",
        default=None,
        required=True,
    )
    parser.add_argument(
        "-e",
        "--training-epochs",
        dest="epochs",
        help="Number of epochs to train",
        default=20,
        type=int,
    )
    parser.add_argument(
        "--confusion-matrix",
        dest="confmatrix",
        help="Don't generate confusion matrix on training data",
        action="store_false",
    )
