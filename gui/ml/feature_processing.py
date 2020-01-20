import copy
import os
import sys

import numpy as np
import pyqtgraph as pg
from matplotlib.colors import LinearSegmentedColormap

from PyQt5 import QtCore

from acconeer.exptool import imock, utils
from acconeer.exptool.modes import Mode

import gui.ml.feature_definitions as feature_def


imock.add_mock_packages(imock.GRAPHICS_LIBS)


try:
    sys.path.append(os.path.realpath(os.path.join(os.path.dirname(__file__), "../../")))
    from examples.processing import presence_detection_sparse
    SPARSE_AUTO_DETECTION = True
except ImportError:
    print("Could not import presence detector!\n")
    SPARSE_AUTO_DETECTION = False


class FeatureProcessing:
    def __init__(self, sensor_config, feature_list=None, store_features=False):
        self.rolling = False
        self.frame_size = 25
        self.sweep_counter = -1
        self.motion_score = None
        self.motion_pass = 2
        self.motion_pass_counter = 0
        self.auto_threshold = 1.5
        self.motion_detected = False
        self.frame_list = []
        self.sweep_number = 0
        self.frame_pad = 0
        self.auto_offset = 10
        self.auto_offset += self.frame_pad
        self.markers = []
        self.label = ""
        self.dead_time_reset = 10
        self.dead_time = 0
        self.triggered = False
        self.trigger_feature_based = False
        self.win_data = None
        self.collection_mode = "auto"
        self.motion_processors = None
        self.store_features = store_features
        self.feature_lookup = feature_def.get_features()
        self.feature_callbacks = {}
        self.setup(sensor_config, feature_list)

    def setup(self, sensor_config, feature_list=None):
        self.feature_list = feature_list
        self.sensor_map, self.sensor_array = self.get_sensor_map(sensor_config)
        self.init_feature_cb()

    def flush_data(self):
        self.frame_list = []
        self.markers = []
        self.sweep_counter = -1
        self.motion_score = None
        self.motion_detected = False
        self.sweep_number = 0
        self.label = ""
        self.triggered = False
        self.feature_error = []
        self.motion_processors = None
        self.motion_score = None
        self.motion_score_normalized = None
        self.calibration = None

    def set_feature_list(self, feature_list):
        self.feature_list = feature_list
        self.feature_callbacks = {}
        try:
            self.init_feature_cb()
        except Exception as e:
            print(e)
            pass

        self.flush_data()

    def set_frame_settings(self, params):
        if not isinstance(params, dict):
            print("Frame settings needs to be a dict!")
            return
        if params.get("frame_size") is not None:
            self.frame_size = max(params["frame_size"], 1)
            self.sweep_counter = -1
        if params.get("frame_pad") is not None:
            self.frame_pad = params["frame_pad"]
            self.sweep_counter = -1
        if params.get("rolling") is not None:
            self.rolling = params["rolling"]
            self.sweep_counter = -1
        if params.get("collection_mode") is not None:
            self.collection_mode = params["collection_mode"]
            self.sweep_counter = -1
            if self.collection_mode == "auto_feature_based":
                self.collection_mode = "continuous"
                self.trigger_feature_based = True
                self.rolling = True
            else:
                self.trigger_feature_based = False
                self.motion_score_normalized = None
        if params.get("frame_label") is not None:
            self.label = params["frame_label"]
        if params.get("triggered") is not None:
            self.triggered = params["triggered"]
        if params.get("auto_threshold") is not None:
            self.auto_threshold = params["auto_threshold"]
        if params.get("dead_time") is not None:
            self.dead_time_reset = params["dead_time"]
            self.dead_time = self.dead_time_reset
        if params.get("auto_offset") is not None:
            self.auto_offset = params["auto_offset"]
        if params.get("calibration") is not None:
            if 0.0 in params["calibration"]:
                print(np.where(params["calibration"] == 0.0))
                print("Discarding calibration data, detected 0 elements!")
                self.calibration = None
            else:
                self.calibration = params["calibration"]

        if self.collection_mode == "auto" or self.collection_mode == "single":
            self.rolling = False

    def init_feature_cb(self):
        if self.feature_list is None:
            return
        for feat in self.feature_list:
            if "cb" in feat:
                if callable(feat["cb"]):
                    self.feature_callbacks[feat] = feat["cb"]()
                else:
                    self.feature_callbacks[feat] = feat["cb"].__init__()
            else:
                self.feature_callbacks[feat["key"]] = self.feature_lookup[feat["key"]]["class"]()

    def prepare_data_container(self, data):
        mode = data["sensor_config"].mode
        n_sweeps = self.frame_size + 2 * self.frame_pad

        if mode == Mode.SPARSE:
            num_sensors, point_repeats, data_len = data["iq_data"].shape
        else:
            num_sensors, data_len = data["iq_data"].shape

        self.win_data = {
            'env_data': np.zeros((num_sensors, data_len, n_sweeps))
        }

        if mode == Mode.SPARSE:
            self.win_data['sparse_data'] = np.zeros(
                (num_sensors, point_repeats, data_len, n_sweeps)
            )
        else:
            self.win_data['iq_data'] = np.zeros((num_sensors, data_len, n_sweeps))

    def add_sweep(self, data, win_idx=0):
        mode = data["sensor_config"].mode
        if mode == Mode.SPARSE:
            self.win_data['sparse_data'][:, :, :, win_idx] = data['iq_data'][:, :, :]
        else:
            self.win_data['iq_data'][:, :, win_idx] = data['iq_data'][:, :]

        self.win_data['env_data'][:, :, win_idx] = data['env_ampl'][:, :]

    def roll_data(self, data):
        mode = data["sensor_config"].mode
        if mode == Mode.SPARSE:
            self.win_data['sparse_data'] = np.roll(self.win_data['sparse_data'], 1, axis=3)
        else:
            self.win_data['iq_data'] = np.roll(self.win_data['iq_data'], 1, axis=2)

        self.win_data['env_data'] = np.roll(self.win_data['env_data'], 1, axis=2)

    def reset_data(self, data, win_idx=None):
        for data in self.win_data:
            if win_idx is None:
                self.win_data[data] *= 0
            else:
                if data == "sparse_data":
                    self.win_data[data][:, :, :, win_idx] = 0
                else:
                    self.win_data[data][:, :, win_idx] = 0

    def feature_extraction(self, data):
        n_sweeps = self.frame_size + 2 * self.frame_pad
        offset = min(self.frame_size, self.auto_offset)
        self.check_data(data)

        if self.sweep_counter == -1:
            self.prepare_data_container(data)
            self.sweep_counter = 0

        if self.collection_mode == "auto" and not self.motion_detected:
            if self.dead_time:
                self.dead_time -= 1
            else:
                if self.auto_motion_detect(data):
                    self.motion_detected = True
                    self.markers.append(self.sweep_number)
                    self.dead_time = self.dead_time_reset

        if self.collection_mode == "auto":
            self.roll_data(data)
            self.add_sweep(data)
            if not self.motion_detected:
                if self.sweep_counter == offset:
                    self.reset_data(data, win_idx=offset)

        if self.collection_mode != "auto":
            if self.sweep_counter == self.frame_pad + 1:
                self.markers.append(self.sweep_number)

        if self.collection_mode == "continuous":
            self.roll_data(data)
            self.add_sweep(data)
            if self.rolling and self.sweep_counter > self.frame_pad + 1:
                self.markers.append(self.sweep_number)

        if self.collection_mode == "single":
            self.roll_data(data)
            self.add_sweep(data)
            if not self.triggered:
                if self.sweep_counter == self.frame_pad:
                    self.reset_data(data, win_idx=self.frame_pad)

        self.sweep_counter += 1

        win_params = {
            "options": None,
            "dist_vec": data["x_mm"],
            "sensor_config": data["sensor_config"],
            "session_info": data.get("session_info", None),
        }

        feature_map = self.generate_feature_map(win_params)

        fmap = None
        if len(feature_map):
            try:
                fmap = np.vstack(feature_map)
            except Exception as e:
                print("Unable to stack features to frame: {}".format(e))

        if self.calibration is not None:
            if self.calibration.shape != fmap.shape:
                print("Calibration data not matching featuer shape!!!")
                print("Calibration: {}".format(self.calibration.shape))
                print("Feature map: {}".format(feature_map.shape))
                self.calibration = None
            else:
                fmap /= self.calibration

        current_frame = {
            "label": self.label,
            "frame_nr": len(self.markers),
            "feature_map": fmap,
            "frame_marker": self.sweep_number - self.frame_size - self.frame_pad,
            "frame_complete": False,
            "sweep_counter": self.sweep_counter,
            "sweep_number": self.sweep_number,
            "calibration": self.calibration,
        }

        trigger_feature_based = not self.trigger_feature_based
        if self.trigger_feature_based and fmap is not None:
            if self.sweep_number > self.frame_size:
                trigger_feature_based = self.auto_motion_detect(fmap, feature_based=True)

        if self.sweep_counter >= n_sweeps:
            if trigger_feature_based:
                current_frame["frame_complete"] = True
            else:
                current_frame["feature_map"] = None
                self.markers.pop(-1)
            if not self.rolling:
                self.sweep_counter = 0
                self.motion_detected = False
                self.reset_data(data)
            else:
                self.sweep_counter = n_sweeps
            if self.collection_mode == "single":
                self.triggered = False
        else:
            current_frame["frame_complete"] = False
            if self.collection_mode == "auto":
                if not self.motion_detected:
                    current_frame["feature_map"] = None
                    if self.sweep_counter > offset:
                        self.sweep_counter = offset
            if self.collection_mode == "single":
                if not self.triggered:
                    current_frame["feature_map"] = None
                    if self.sweep_counter > self.frame_pad:
                        self.sweep_counter = self.frame_pad

        self.sweep_number += 1

        if current_frame["feature_map"] is not None and current_frame["frame_complete"]:
            if self.store_features:
                self.frame_list.append(copy.deepcopy(current_frame))

        if not self.store_features:
            self.sweep_number = max(self.sweep_number, 2 * self.frame_size)

        frame_data = {
            "current_frame": current_frame,
            "frame_markers": self.markers,
            "frame_info": {
                "frame_pad": self.frame_pad,
                "frame_size": self.frame_size,
            },
            "feature_list": self.feature_list,
            "frame_list": self.frame_list,
            "motion_score": self.motion_score_normalized,
            "model_dimension": self.feature_list[0]["model_dimension"],
        }

        return frame_data

    def feature_extraction_window(self, data, record, start, label=""):
        self.frame_pad = data["ml_frame_data"]["frame_info"]["frame_pad"]
        self.frame_size = data["ml_frame_data"]["frame_info"]["frame_size"]
        self.calibration = data["ml_frame_data"]["current_frame"].get("calibration")
        n_sweeps = self.frame_size + 2 * self.frame_pad
        self.set_feature_list(data["ml_frame_data"]["feature_list"])
        frame_start = start - self.frame_pad
        frame_stop = frame_start + self.frame_size + 2 * self.frame_pad
        sensor_config = data["sensor_config"]
        mode = sensor_config.mode
        self.check_data(data)
        self.prepare_data_container(data)

        win_params = {
            "options": None,
            "dist_vec": data["x_mm"],
            "sensor_config": data["sensor_config"],
            "session_info": data.get("session_info", None),
        }

        for marker in range(frame_start, frame_stop):
            data_step = {
                "sensor_config": data["sensor_config"],
                "iq_data": record.data[marker],
            }
            if mode == Mode.SPARSE:
                data_step["env_ampl"] = np.abs(record.data[marker].mean(axis=1))
            else:
                data_step["env_ampl"] = np.abs(record.data[marker])
            if data_step["env_ampl"].shape != self.win_data["env_data"].shape[0:2]:
                data_step["iq_data"] = data_step["iq_data"][self.sensor_array]
                data_step["env_ampl"] = data_step["env_ampl"][self.sensor_array]
            self.roll_data(data)
            self.add_sweep(data_step)

            feature_map = self.generate_feature_map(win_params)

        fmap = None
        if len(feature_map):
            try:
                fmap = np.vstack(feature_map)
            except Exception as e:
                print("Unable to stack features to frame: {}".format(e))

        if self.calibration is not None:
            if self.calibration.shape != fmap.shape:
                print("Calibration data not matching featuer shape!!!")
                print("Calibration: {}".format(self.calibration.shape))
                print("Feature map: {}".format(feature_map.shape))
                self.calibration = None
            else:
                fmap /= self.calibration

        current_frame = {
            "label": label,
            "frame_nr": data["ml_frame_data"]["current_frame"]["frame_nr"],
            "feature_map": fmap,
            "frame_marker": start,
            "frame_complete": True,
            "sweep_counter": n_sweeps,
            "sweep_number": frame_stop,
            "calibration": self.calibration,
        }

        data["ml_frame_data"]["current_frame"] = current_frame

        return data

    def generate_feature_map(self, win_params):
        feature_map = []
        for feat in self.feature_list:
            cb = self.feature_callbacks[feat["key"]]

            output = feat["output"]
            sensors = feat["sensors"]
            name = feat["name"]

            win_params["options"] = feat["options"]

            for s in sensors:
                idx = self.sensor_map[str(s)]
                if idx is None:
                    continue
                win_params["sensor_idx"] = idx

                feat_data = cb.extract_feature(self.win_data, win_params)

                if output is not None:
                    if feat_data is None:
                        if name not in self.feature_error:
                            self.feature_error.append(name)
                    else:
                        for out in output:
                            if output[out]:
                                try:
                                    feature_map.append(feat_data[out])
                                except Exception:
                                    pass

        return feature_map

    def check_data(self, data):
        if data.get("x_mm") is None:
            data["x_mm"] = utils.get_range_depths(data["sensor_config"], data["session_info"])
            data["x_mm"] *= 1000

        if data.get("env_ampl") is None:
            sweep = data["iq_data"]
            if data["sensor_config"].mode == Mode.SPARSE:
                data['env_ampl'] = sweep.mean(axis=1)
            else:
                data['env_ampl'] = np.abs(sweep)

    def indexer(self, i):
        self.m += 1
        return self.m

    def auto_motion_detect(self, data, feature_based=False):
        detected = False

        if feature_based:
            wing = self.auto_offset
            if len(data.shape) == 2:
                if wing >= (self.frame_size / 2):
                    self.motion_score_normalized = "Reduce offset!"
                    detected = True
                else:
                    center = np.sum(data[:, wing:-wing]) / (self.frame_size - 2 * wing)
                    left = np.sum(data[:, 0:wing]) / wing
                    right = np.sum(data[:, -(wing + 1):-1]) / wing
                    if right == 0 or left == 0:
                        self.motion_score_normalized = 0
                        return detected
                    if left / right > 0.9 and left / right < 1.1:
                        self.motion_score_normalized = 2 * center / (left + right)
                        if self.motion_score_normalized > self.auto_threshold:
                            detected = True
            else:
                self.motion_score_normalized = "Not implemented"
                detected = True
            return detected

        num_sensors = data["iq_data"].shape[0]
        sensor_config = data["sensor_config"]
        mode = sensor_config.mode

        if mode == Mode.SPARSE and not SPARSE_AUTO_DETECTION:
            if self.sweep_counter <= 10:
                print("Warning: Auto movement detection with spares not available.")

        if mode == Mode.SPARSE and SPARSE_AUTO_DETECTION:
            if self.motion_processors is None:
                self.motion_config = presence_detection_sparse.get_processing_config()
                self.motion_config.inter_frame_fast_cutoff = 100
                self.motion_config.inter_frame_slow_cutoff = 0.9
                self.motion_config.inter_frame_deviation_time_const = 0.05
                self.motion_config.intra_frame_weight = 0.8
                self.motion_config.intra_frame_time_const = 0.03
                self.motion_config.detection_threshold = 0
                self.motion_config.output_time_const = 0.01
                self.motion_class = presence_detection_sparse.PresenceDetectionSparseProcessor
                motion_processors_list = []
                for i in range(num_sensors):
                    motion_processors_list.append(
                        self.motion_class(
                            sensor_config,
                            self.motion_config,
                            data["session_info"]
                        )
                    )
                self.motion_processors = motion_processors_list
            else:
                motion_score = 0
                for i in range(num_sensors):
                    score = self.motion_processors[i].process(data["iq_data"][i, :, :])
                    score = score["depthwise_presence"]
                    max_score = np.nanmax(score)
                    if max_score > motion_score:
                        motion_score = max_score
                self.motion_score_normalized = motion_score
                if self.motion_score_normalized > self.auto_threshold:
                    detected = True
                    motion_processors_list = []
                    for i in range(num_sensors):
                        motion_processors_list.append(
                            self.motion_class(
                                sensor_config,
                                self.motion_config,
                                data["session_info"]
                            )
                        )
                    self.motion_processors = motion_processors_list
                    return detected
        else:
            if self.motion_score is None:
                self.motion_score_normalized = 0
                self.motion_score = np.full(num_sensors, np.inf)

            for i in range(num_sensors):
                motion_score = np.max(np.abs(data["env_ampl"][i, :]))

                if motion_score < self.motion_score[i]:
                    if self.motion_score[i] == np.inf:
                        self.motion_score[i] = motion_score

                self.motion_score_normalized = max(
                    self.motion_score_normalized,
                    motion_score / self.motion_score[i]
                )

                if self.motion_score_normalized > self.auto_threshold:
                    self.motion_pass_counter += 1
                    if self.motion_pass_counter >= self.motion_pass:
                        self.motion_pass_counter = 0
                        self.motion_score = None
                        detected = True
                        return detected
                else:
                    # Try to remove small scale variations
                    self.motion_score[i] = 0.9 * self.motion_score[i] + 0.1 * motion_score

        return detected

    def get_sensor_map(self, sensor_config):
        sensors = sensor_config.sensor
        num_sensors = len(sensors)

        sensor_map = {"1": None, "2": None, "3": None, "4": None}
        sensor_array = []
        for idx, s in enumerate(sensors):
            sensor_map[str(s)] = idx
            sensor_array.append(s)
        if num_sensors == 1:
            for s in range(1, 5):
                sensor_map[str(s)] = 0

        sensor_array = np.asarray(sensor_array)

        return sensor_map, sensor_array


class DataProcessor:
    hist_len = 100

    def __init__(self, sensor_config, ml_settings, session_info):
        self.session_info = session_info
        self.sensor_config = sensor_config
        self.mode = self.sensor_config.mode
        self.start_x = self.sensor_config.range_interval[0]
        self.stop_x = self.sensor_config.range_interval[1]
        self.sweep = 0
        self.frame_settings = ml_settings["frame_settings"]
        self.enable_plotting = True

        self.evaluate = False
        self.prediction_hist = None
        if ml_settings["evaluate"]:
            self.evaluate = ml_settings["evaluate_func"]

        self.rate = 1 / self.sensor_config.update_rate

        self.num_sensors = sensor_config.sensor

        self.image_buffer = 100

        self.feature_process = FeatureProcessing(self.sensor_config, store_features=True)
        self.feature_process.set_feature_list(ml_settings["feature_list"])
        self.feature_process.set_frame_settings(self.frame_settings)

    def update_ml_settings(self, ml_settings=None, frame_settings=None, trigger=None,
                           feature_list=None):
        if frame_settings is not None:
            self.feature_process.set_frame_settings(frame_settings)

        if trigger is not None:
            self.feature_process.send_trigger()

        if feature_list:
            try:
                self.feature_process.set_feature_list(feature_list)
            except Exception as e:
                print("Failed to update feature list ", e)

    def process(self, sweep):
        mode = self.sensor_config.mode

        if self.sweep == 0:
            self.x_mm = utils.get_range_depths(self.sensor_config, self.session_info) * 1000
            if mode == Mode.SPARSE:
                self.num_sensors, point_repeats, self.data_len = sweep.shape
                self.hist_env = np.zeros((self.num_sensors, self.data_len, self.image_buffer))
            else:
                self.data_len = sweep.size
                self.num_sensors = 1
                if len(sweep.shape) > 1:
                    self.num_sensors, self.data_len = sweep.shape
                self.hist_env = np.zeros(
                    (self.num_sensors, self.data_len, self.image_buffer)
                )

        iq = sweep.copy()

        env = None
        if mode == Mode.SPARSE:
            env = sweep.mean(axis=1)
        else:
            env = np.abs(iq)

        for s in range(self.num_sensors):
            self.hist_env[s, :, :] = np.roll(self.hist_env[s, :, :], 1, axis=1)
            self.hist_env[s, :, 0] = env[s, :]

        plot_data = {
            "iq_data": iq,
            "env_ampl": env,
            "hist_env": self.hist_env,
            "sensor_config": self.sensor_config,
            "x_mm": self.x_mm,
            "sweep": self.sweep,
            "num_sensors": self.num_sensors,
            "ml_plotting": True,
            "ml_frame_data": None,
            "prediction": None,
            "prediction_hist": None,
            "session_info": self.session_info,
        }

        plot_data["ml_frame_data"] = self.feature_process.feature_extraction(plot_data)

        feature_map = plot_data["ml_frame_data"]["current_frame"]["feature_map"]
        complete = plot_data["ml_frame_data"]["current_frame"]["frame_complete"]
        if complete and self.evaluate and feature_map is not None:
            plot_data["prediction"] = self.evaluate(feature_map)
            prediction_label = plot_data["prediction"]["prediction"]
            plot_data["ml_frame_data"]["frame_list"][-1]["label"] = prediction_label

            if self.prediction_hist is None:
                self.prediction_hist = np.zeros((plot_data["prediction"]["number_labels"],
                                                 self.hist_len))
            predictions = plot_data["prediction"]["label_predictions"]
            self.prediction_hist = np.roll(self.prediction_hist, 1, axis=1)
            for key in predictions:
                pred, idx = predictions[key]
                self.prediction_hist[idx, 0] = pred
            plot_data["prediction_hist"] = self.prediction_hist

        self.sweep += 1

        return plot_data


class PGUpdater:
    def __init__(self, sensor_config=None, processing_config=None, predictions=False,
                 info_text=True):

        self.env_plot_max_y = 0
        self.hist_plot_max_y = 0
        self.sensor_config = sensor_config
        self.processing_config = processing_config
        self.first = True
        self.show_predictions = predictions
        self.print_info_text = info_text

    def setup(self, win):
        win.setWindowTitle("Feature plotting")
        self.feat_plot_image = win.addPlot(row=0, col=0)
        self.feat_plot = pg.ImageItem()
        self.feat_plot.setAutoDownsample(True)
        self.feat_plot_image.addItem(self.feat_plot)
        self.feat_plot_image.setLabel("left", "Features")
        self.feat_plot_image.setLabel("bottom", "Sweeps")

        lut = utils.pg_mpl_cmap("viridis")
        self.feat_plot.setLookupTable(lut)

        self.feat_plot_image.setXRange(0, 40)
        self.feat_plot_image.setYRange(0, 1)

        self.border_right = pg.InfiniteLine(
            pos=0,
            angle=90,
            pen=pg.mkPen(width=2, style=QtCore.Qt.DotLine)
        )
        self.border_left = pg.InfiniteLine(
            pos=0,
            angle=90,
            pen=pg.mkPen(width=2, style=QtCore.Qt.DotLine)
        )
        self.border_rolling = pg.InfiniteLine(pos=0, angle=90, pen=pg.mkPen(width=2))

        self.detected_text = pg.TextItem(color="r", anchor=(0, 1))
        self.feature_nr_text = pg.TextItem(color="r", anchor=(0, 2))

        self.feat_plot_image.addItem(self.detected_text)
        self.feat_plot_image.addItem(self.feature_nr_text)
        self.feat_plot_image.addItem(self.border_left)
        self.feat_plot_image.addItem(self.border_right)
        self.feat_plot_image.addItem(self.border_rolling)

        self.border_left.hide()
        self.border_right.hide()
        self.border_rolling.hide()

        r = 1
        if self.show_predictions:
            r = 2
        self.history_plot_window = win.addLayout(row=r, col=0)

        self.envelope_plots = []
        self.peak_vlines = []
        self.clutter_plots = []
        self.hist_plot_images = []
        self.hist_plots = []
        self.hist_plot_peaks = []

        lut = utils.pg_mpl_cmap("viridis")

        for s in range(4):
            legend_text = "Sensor {}".format(s+1)
            hist_title = "History {}".format(legend_text)
            self.hist_plot_images.append(
                self.history_plot_window.addPlot(row=0, col=s, title=hist_title)
            )
            self.hist_plot_images[s].setLabel("bottom", "Time (s)")
            self.hist_plots.append(pg.ImageItem())
            self.hist_plots[s].setAutoDownsample(True)
            self.hist_plots[s].setLookupTable(lut)
            self.hist_plot_images[s].addItem(self.hist_plots[s])

        if self.show_predictions:
            self.predictions_plot_window = win.addPlot(row=1, col=0, title="Prediction results")
            self.predictions_plot_window.showGrid(x=True, y=True)
            self.predictions_plot_window.addLegend(offset=(-10, 10))
            self.predictions_plot_window.setYRange(0, 1)
            self.predictions_plot_window.setLabel("left", "Probability")
            self.predictions_plot_window.setLabel("bottom", "Iteration")

            self.prediction_plots = []

    def generate_predciction_plots(self, labels, num):
        for label in labels:
            label_num = labels[label][1]
            if label_num < len(self.prediction_plots):
                continue
            else:
                pen = utils.pg_pen_cycler(label_num)
                self.prediction_plots.append(
                    self.predictions_plot_window.plot(pen=pen, name=label)
                )

    def reset_data(self, sensor_config=None, processing_config=None):
        self.first = True
        if sensor_config is not None:
            self.sensor_config = sensor_config
        if processing_config is not None:
            self.processing_config = processing_config

    def update(self, data):
        feat_map = None
        if data["ml_frame_data"] is not None:
            frame_data = data["ml_frame_data"]
            feat_map = frame_data["current_frame"]["feature_map"]
            frame_size = frame_data["frame_info"]["frame_size"]
            frame_pad = frame_data["frame_info"]["frame_pad"]
            frame_complete = frame_data["current_frame"]["frame_complete"]
            model_dimension = data["ml_frame_data"]["model_dimension"]
        else:
            return

        sensors = []
        if self.sensor_config is not None:
            sensors = self.sensor_config.sensor

        mode = data["sensor_config"].mode

        if self.first:
            self.first = False
            self.env_plot_max_y = 0
            s_buff = frame_size + 2 * frame_pad
            self.feat_plot.resetTransform()
            if model_dimension > 1:
                self.feat_plot.translate(-frame_pad, 0)
            self.feat_plot_image.setXRange(-frame_pad, s_buff - frame_pad)

            self.border_left.setValue(0)
            self.border_right.setValue(frame_size)

            self.border_left.show()
            self.border_right.show()

            nr_sensors = len(sensors)
            self.hist_plot_max_y = np.zeros(nr_sensors)

            lut = utils.pg_mpl_cmap("viridis")
            if mode == Mode.SPARSE:
                cmap_cols = ["steelblue", "lightblue", "#f0f0f0", "moccasin", "darkorange"]
                cmap = LinearSegmentedColormap.from_list("mycmap", cmap_cols)
                cmap._init()
                lut = (cmap._lut * 255).view(np.ndarray)

            for i in range(4):
                if (i + 1) in sensors:
                    self.hist_plot_images[i].show()
                    self.set_axis(data, self.hist_plot_images[i])
                    self.hist_plots[i].setLookupTable(lut)
                    if (i + 1) == sensors[0]:
                        self.hist_plot_images[i].setLabel("left", "Distance (mm)")
                else:
                    self.hist_plot_images[i].hide()

        for idx, sensor in enumerate(sensors):

            if mode == Mode.SPARSE:
                data_history_adj = data["hist_env"][idx, :, :].T - 2**15
                sign = np.sign(data_history_adj)
                data_history_adj = np.abs(data_history_adj)
                data_history_adj /= data_history_adj.max()
                data_history_adj = np.power(data_history_adj, 1/2.2)  # gamma correction
                data_history_adj *= sign
                self.hist_plots[sensor-1].updateImage(data_history_adj, levels=(-1.05, 1.05))
            else:
                max_val = np.max(data["env_ampl"][idx])

                ymax_level = min(1.5 * np.max(np.max(data["hist_env"][idx, :, :])),
                                 self.hist_plot_max_y[idx])

                if max_val > self.hist_plot_max_y[idx]:
                    self.hist_plot_max_y[idx] = 1.2 * max_val

                self.hist_plots[sensor-1].updateImage(
                    data["hist_env"][idx, :, :].T,
                    levels=(0, ymax_level)
                )

        if self.show_predictions and data.get("prediction") is not None:
            self.predictions_plot_window.show()
            prediction_text = "{} ({:.2f}%)".format(
                data["prediction"]["prediction"],
                data["prediction"]["confidence"] * 100,
            )
            self.predictions_plot_window.setTitle(prediction_text)
            predictions = data["prediction"]["label_predictions"]
            pred_num = data["prediction"]["number_labels"]
            pred_history = data["prediction_hist"]
            if len(self.prediction_plots) < pred_num:
                self.generate_predciction_plots(predictions, pred_num)

            if pred_history is not None:
                for idx in range(pred_num):
                    self.prediction_plots[idx].setData(pred_history[idx, :])

        detected = True
        if feat_map is None:
            detected = False

        if detected and not len(feat_map):
            detected = False

        if self.print_info_text:
            feature_nr = frame_data["current_frame"]["frame_nr"]
            self.feature_nr_text.setText("Feature: {}".format(feature_nr))
            if not detected:
                motion_score = frame_data.pop("motion_score", None)
                text = "Waiting..."
                if motion_score is not None:
                    if isinstance(motion_score, float):
                        motion_score = "{:.1f}".format(motion_score)
                    text = "Waiting.. (Motion score: {})".format(motion_score)
                self.detected_text.setText(text)
                return
            else:
                self.detected_text.setText("Collecting..")

        if not frame_complete:
            self.border_rolling.show()
            self.border_rolling.setValue(
                frame_data["current_frame"]["sweep_counter"] - frame_pad
            )
        else:
            self.border_rolling.hide()

        if feat_map is None:
            return

        self.feat_plot_image.setYRange(0, feat_map.shape[0])

        map_max = 1.2 * np.max(feat_map)
        ymax_level = max(map_max, self.env_plot_max_y)

        g = 1/2.2
        feat_map = 254/(ymax_level + 1.0e-9)**g * feat_map**g

        feat_map[feat_map > 254] = 254

        self.feat_plot.updateImage(feat_map.T, levels=(0, 256))

        if map_max > self.env_plot_max_y:
            self.env_plot_max_y = map_max

    def set_axis(self, data, plot):
        xstart = data["x_mm"][0]
        xend = data["x_mm"][-1]
        num_sensors, xdim, s_buff = data["hist_env"].shape

        yax = plot.getAxis("left")
        y = np.round(np.arange(0, xdim+xdim/9, xdim/9))
        labels = np.round(np.arange(xstart, xend+(xend-xstart)/9,
                          (xend-xstart)/9))
        ticks = [list(zip(y, labels))]
        yax.setTicks(ticks)
        plot.setYRange(0, xdim)

        t_buff = s_buff / data["sensor_config"].update_rate
        tax = plot.getAxis("bottom")
        t = np.round(np.arange(0, s_buff + 1, s_buff / min(10 / num_sensors, s_buff)))
        labels = np.round(t / s_buff * t_buff, decimals=3)
        ticks = [list(zip(t, labels))]
        tax.setTicks(ticks)
