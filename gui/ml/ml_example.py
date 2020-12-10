import datetime
import os
import sys
import traceback
from argparse import ArgumentParser


# If you run stand_alone.py from ..gui/ml
sys.path.append(os.path.realpath(os.path.join(os.path.dirname(__file__), "../../")))
print(os.path.realpath(os.path.join(os.path.dirname(__file__), "../../")))
# If you run stand_alone from another folder
path_to_exploration_tool = "/home/pi/acconeer-exploration-tool"

sys.path.append(os.path.realpath(path_to_exploration_tool))

try:
    import gui.ml.keras_processing as kp
    import gui.ml.ml_helper as ml_helper
except ImportError:
    traceback.print_exc()
    print("Please make sure you have specified the Exploration Tool folder!")
    exit(0)


def main():
    parser = ArgumentParser()
    ml_helper.add_args(parser)
    args = parser.parse_args()

    ml = kp.MachineLearning()

    if args.load_model_file:
        model_data, message = ml_helper.load_model(args.load_model_file)
        print(message)
        if not model_data.loaded:
            exit(0)
    else:
        if args.model_layers_file:
            # Generate with GUI
            model_layers = ml_helper.load_from_yaml(args.model_layers_file)
            ml.set_model_layers(model_layers)
        else:
            print("You must either load a model file or a model layers file!")
            exit(0)

    # Generate with GUI
    session_files = ml_helper.get_files(args.train_files)

    res = ml.load_train_data(session_files)

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
        fname = fname = "model_data_{date:%Y_%m_%d_%H%M}".format(date=datetime.datetime.now())
    ml.save_model(fname)

    if args.confmatrix:
        predictions = ml.predict()
        y_test = ml.get_model_data().y_labels
        ml.confusion_matrix(y_test, predictions, print_to_cmd=True)


if __name__ == "__main__":
    main()
