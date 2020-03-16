import datetime
import os
import sys
from argparse import ArgumentParser

import yaml


# If you run stand_alone.py from ..gui/ml
sys.path.append(os.path.realpath(os.path.join(os.path.dirname(__file__), "../../")))

# If you run stand_alone from another folder
path_to_exploration_tool = "/home/pi/acconeer-exploration-tool"

sys.path.append(os.path.realpath(path_to_exploration_tool))

try:
    import keras_processing as kp
except ImportError:
    print("Please make sure you have specified the Exploration Tool folder!")
    exit(0)


def main():
    parser = ArgumentParser()
    add_args(parser)
    args = parser.parse_args()

    ml = kp.MachineLearning()

    if args.load_model_file:
        model_data, message = ml.load_model(args.load_model_file)
        print(message)
        if not model_data.loaded:
            exit(0)
    else:
        if args.model_layers_file:
            # Generate with GUI
            model_layers = load_from_yaml(args.model_layers_file)
            ml.set_model_layers(model_layers)
        else:
            print("You must either load a model file or a model layers file!")
            exit(0)

    # Generate with GUI
    train_files = load_from_yaml(args.train_files)  # Generate with GUI

    res = ml.load_train_data(train_files)

    print("\nModel loaded: {}".format(res["info"]["success"]))
    print(res["info"]["message"])
    if res["info"]["success"]:
        ml.model.summary()
    else:
        exit(0)

    if args.save_best:
        save_best_info = {
            "folder": args.save_best,
            "feature_list": ml.model_data.feature_list,
            "frame_settings": ml.model_data.frame_settings,
            "sensor_config": ml.model_data.sensor_config,
        }
    else:
        save_best_info = None

    train_params = {
        "epochs": args.epochs,
        "batch_size": 128,
        "eval_data": 0.2,
        "save_best": save_best_info,
        "dropout": None,
        "learning_rate": 0.01,
        "optimizer": "Adagrad",
        "plot_cb": None,
    }

    ml.train(train_params)

    if args.save_model is not None:
        fname = args.save_model
    else:
        fname = fname = 'model_data_{date:%Y_%m_%d_%H%M}'.format(date=datetime.datetime.now())
    ml.save_model(fname)

    if args.confmatrix:
        predictions = ml.predict()
        y_test = ml.get_model_data().y_labels
        ml.confusion_matrix(y_test, predictions, print_to_cmd=True)


def load_from_yaml(filename):
    try:
        with open(filename, 'r') as f_handle:
            data = yaml.load(f_handle, Loader=yaml.FullLoader)
    except Exception as e:
        print("Failed to load data\n", e)
    return data


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
        "--no-confusion-matrix",
        dest="confmatrix",
        help="Don't generate confusion matrix on training data",
        action="store_false",
    )


if __name__ == "__main__":
    main()
