import os
import sys

import numpy as np

from acconeer.exptool.modes import Mode

import feature_processing as feat_p
import keras_processing as keras_p


try:
    sys.path.append(os.path.realpath(os.path.join(os.path.dirname(__file__), "../../")))
    from examples.processing import presence_detection_sparse
    SPARSE_AUTO_DETECTION = True
except ImportError:
    print("Could not import presence detector!\n")
    SPARSE_AUTO_DETECTION = False


class Trigger():
    def __init__(self):
        self.motion_detector = None
        self.mode = None

        self.flush()

    def flush(self):
        # Allow dead time
        self.trigger_series = False
        self.trigger_last = False
        self.trigger_dead_time = 0
        self.trigger_cool_down = 0

        # Store mode specific variables
        self.trigger_variables = {}

    def get_trigger_modes(self):
        trigger_modes = {
            "presence_sparse": {
                "name": "Presence sparse",
                "options": None,
                "cb": self.trigger_presence_sparse,
            },
            "threshold": {
                "name": "Amplitude threshold",
                "options": None,
                "cb": self.trigger_treshold,
            },
            "auto_feature_based": {
                "name": "Feature Center-based",
                "options": None,
                "cb": self.trigger_feature_center,
            },
            "support_model": {
                "name": "Support Model",
                "options": None,
                "cb": self.trigger_support_model,
            },
        }
        return trigger_modes

    def set_trigger_mode(self, trigger_options):
        trigger_modes = self.get_trigger_modes()
        mode = trigger_options["mode"]

        if mode != self.mode:
            self.flush()

        trigger = trigger_modes.get(mode, None)
        if trigger is not None:
            self.trigger_detector = trigger.get("cb", None)
            self.mode = mode
        else:
            self.mode = None
            self.trigger_detector = None

        if self.trigger_detector is not None:
            self.trigger_dead_time = trigger_options.get("dead_time", 0)
            self.trigger_series = trigger_options.get("trigger_series", False)

    def get_trigger(self, data, feature_map, trigger_options):
        if self.trigger_detector is None:
            return True, None, "No detector specified"

        if self.trigger_cool_down:
            updated_dead_time = trigger_options.get("dead_time", 0)
            self.trigger_cool_down = min(self.trigger_cool_down - 1, updated_dead_time)
            return False, None, "Cool down {}".format(self.trigger_cool_down)

        trigger, score, message = self.trigger_detector(data, feature_map, trigger_options)

        # If "Trigger series", enter dead time after first False
        if self.trigger_series:
            if not trigger and self.last_trigger:
                self.trigger_cool_down = self.trigger_dead_time
        else:
            if trigger:
                self.trigger_cool_down = self.trigger_dead_time

        self.last_trigger = trigger

        return trigger, score, message

    def trigger_feature_center(self, data, feature_map, trigger_options):
        detected = False
        threshold = trigger_options["auto_threshold"]
        score = 0
        message = ""
        margin = .1

        wing = trigger_options["auto_offset"]
        if len(feature_map.shape) == 2:
            frame_size = feature_map.shape[1]
            if wing >= (frame_size / 2):
                message = "Reduce offset!"
                detected = True
                return detected, score, message
            else:
                center = np.sum(feature_map[:, wing:-wing]) / (frame_size - 2 * wing)
                left = np.sum(feature_map[:, 0:wing]) / wing
                right = np.sum(feature_map[:, -(wing + 1):-1]) / wing

                if right == 0 or left == 0:
                    pass
                elif (left / right > 1.0 - margin) and (left / right < 1.0 + margin):
                    score = 2 * center / (left + right)
                    if score > threshold:
                        detected = True
                    if center > 2 * threshold * left:
                        detected = True
                    elif center > 2 * threshold * right:
                        detected = True
                if left > 1.1 * center or right > 1.1 * center:
                    detected = False

                message = "L:{:.2f}, C:{:.2f}, R:{:.2f}".format(left, center, right)
        else:
            message = "Not implemented"
            detected = True

        return detected, score, message

    def trigger_feature_side(self, data, feature_map, trigger_options):
        detected = False
        threshold = trigger_options["auto_threshold"]
        score = 0
        message = ""
        margin = .1

        wing = trigger_options["auto_offset"]

        wing = trigger_options["auto_offset"]
        if len(feature_map.shape) == 2:
            frame_size = feature_map.shape[1]
            if wing >= (frame_size / 2):
                message = "Reduce offset!"
                detected = True
                return detected, score, message
            else:
                center = np.sum(feature_map[:, wing:-wing]) / (frame_size - 2 * wing)
                left = np.sum(feature_map[:, 0:wing]) / wing
                right = np.sum(feature_map[:, -(wing + 1):-1]) / wing
                side = right
                off1 = center
                off2 = left
                if right == 0 or left == 0:
                    pass
                if off1 / off2 < 1.0 + margin:
                    score = 2 * side / (off1 + off2)
                    if score > threshold:
                        detected = True
                if side > (2 * threshold * center):
                    detected = True
                if off1 > 1.1 * side or off2 > 1.1 * side:
                    detected = False
                if side < 7:
                    detected = False
                if center > 10:
                    detected = False
                if detected:
                    print(side, off1, off2)
                message = "L:{:.2f}, C:{:.2f}, R:{:.2f}".format(left, center, right)
        else:
            message = "Not implemented"
            detected = True

        return detected, score, message

    def trigger_presence_sparse(self, data, feature_map, trigger_options):
        detected = False
        threshold = trigger_options["auto_threshold"]
        score = 0
        message = ""
        num_sensors = data["sweep_data"].shape[0]
        sensor_config = data["sensor_config"]
        mode = sensor_config.mode

        if mode == Mode.SPARSE and not SPARSE_AUTO_DETECTION:
            if self.sweep_counter <= 10:
                print("Warning: Auto movement detection with spares not available.")

        if mode == Mode.SPARSE and SPARSE_AUTO_DETECTION:
            if not self.trigger_variables.get("motion_processors_initialized", False):
                self.motion_config = presence_detection_sparse.get_processing_config()
                self.motion_config.inter_frame_fast_cutoff = 100
                self.motion_config.inter_frame_slow_cutoff = 0.9
                self.motion_config.inter_frame_deviation_time_const = 0.05
                self.motion_config.intra_frame_weight = 0.8
                self.motion_config.intra_frame_time_const = 0.03
                self.motion_config.detection_threshold = 0
                self.motion_config.output_time_const = 0.01
                self.motion_class = presence_detection_sparse.Processor
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
                self.trigger_variables["motion_processors_initialized"] = True
            else:
                score = 0
                for i in range(num_sensors):
                    motion_score = self.motion_processors[i].process(data["sweep_data"][i, :, :])
                    motion_score = motion_score["depthwise_presence"]
                    max_score = np.nanmax(motion_score)
                    if max_score > score:
                        score = max_score
                        message = "Triggered on sensor {}".format(i + 1)
                if score > threshold:
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

        return detected, score, message

    def trigger_treshold(self, data, feature_map, trigger_options):
        detected = False
        threshold = trigger_options["auto_threshold"]
        message = ""
        num_sensors = data["sweep_data"].shape[0]

        if not self.trigger_variables.get("initialized", False):
            self.motion_score_normalized = 0
            self.motion_score = np.full(num_sensors, np.inf)
            self.trigger_variables["initialized"] = True
            self.motion_pass_counter = 0
            self.motion_pass = 2

        for i in range(num_sensors):
            motion_score = np.max(np.abs(data["env_ampl"][i, :]))

            if motion_score < self.motion_score[i]:
                if self.motion_score[i] == np.inf:
                    self.motion_score[i] = motion_score

            self.motion_score_normalized = max(
                self.motion_score_normalized,
                motion_score / self.motion_score[i]
            )

            if self.motion_score_normalized > threshold:
                self.motion_pass_counter += 1
                if self.motion_pass_counter >= self.motion_pass:
                    self.motion_pass_counter = 0
                    self.motion_score = None
                    detected = True
                    break
            else:
                # Try to remove small scale variations
                self.motion_score[i] = 0.9 * self.motion_score[i] + 0.1 * motion_score

        return detected, self.motion_score_normalized, message

    def trigger_support_model(self, data, feature_map, trigger_options):
        threshold = trigger_options["auto_threshold"]

        if not self.trigger_variables.get("initialized", False):
            if not hasattr(self, "keras_process"):
                self.kp = keras_p.MachineLearning()
            else:
                self.kp.clear_model()
            trigger_model, t_message = self.kp.load_model("model_trigger.npy")

            if not trigger_model["loaded"]:
                print(t_message)
                return True, None, t_message
            else:
                print("model loaded")

            config = trigger_model["sensor_config"]
            feature_list = trigger_model["feature_list"]
            frame_settings = trigger_model["frame_settings"]
            if frame_settings["collection_mode"] == "support_model":
                print("Not supported, changing to continuous")
                frame_settings["collection_mode"] = "continuous"
                frame_settings["rolling"] = True

            self.trigger_process = feat_p.FeatureProcessing(config)
            self.trigger_process.set_feature_list(feature_list)
            self.trigger_process.set_frame_settings(frame_settings)

            self.trigger_variables["initialized"] = True

        ml_frame_data = self.trigger_process.feature_extraction(data)
        feature_map = ml_frame_data["current_frame"]["feature_map"]
        complete = ml_frame_data["current_frame"]["frame_complete"]

        score = 0
        detected = False
        if complete and feature_map is not None:
            self.kp.clear_session()
            trigger = self.kp.predict(feature_map)[0]
            self.kp.clear_session()
            score = trigger["label_predictions"]["centered"][0]
            if score > threshold:
                detected = True

        return detected, score, ""
