import json
import time
import traceback
import warnings

from PyQt5.QtCore import QThread

from acconeer.exptool import modes
from acconeer.exptool.recording import Recorder


warnings.filterwarnings("ignore")


class DataProcessing:
    hist_len = 500

    def prepare_processing(self, parent, params, session_info):
        self.parent = parent
        self.gui_handle = self.parent.parent
        self.sensor_config = params["sensor_config"]
        self.processing_config = params["service_params"]
        self.multi_sensor = params["multi_sensor"]

        hist_len = params["sweep_buffer"]
        if hist_len is not None and hist_len < 1:
            hist_len = None

        self.ml_settings = params["ml_settings"]

        if isinstance(self.processing_config, dict):  # Legacy
            self.processing_config["processing_handle"] = self
            record_processing_config = None
        else:
            record_processing_config = self.processing_config

        self.session_info = session_info

        self.recorder = Recorder(
            sensor_config=self.sensor_config,
            session_info=session_info,
            module_key=params["module_info"].key,
            processing_config=record_processing_config,
            rss_version=params.get("rss_version", None),
            max_len=hist_len,
        )

        self.init_vars()

    def abort_processing(self):
        self.abort = True

    def init_vars(self):
        self.abort = False
        self.first_run = True

    def update_feature_extraction(self, param, value=None):
        if isinstance(value, dict):
            settings = value
        else:
            settings = {param: value}
        try:
            self.external.update_ml_settings(frame_settings=settings)
        except Exception:
            traceback.print_exc()

    def send_feature_trigger(self):
        try:
            self.external.update_ml_settings(trigger=True)
        except Exception:
            traceback.print_exc()

    def update_feature_list(self, feature_list):
        try:
            self.external.update_ml_settings(feature_list=feature_list)
        except Exception:
            traceback.print_exc()

    def process(self, unsqueezed_data, info, do_record=True):
        if self.multi_sensor:
            in_data = unsqueezed_data
            in_info = info
        else:
            assert unsqueezed_data.shape[0] == 1
            in_data = unsqueezed_data[0]
            in_info = info[0]

        if self.first_run:
            ext = self.gui_handle.external
            processing_config = self.processing_config
            if self.ml_settings is not None:
                ext = self.gui_handle.ml_external
                processing_config = self.ml_settings
            self.external = ext(self.sensor_config, processing_config, self.session_info)
            self.first_run = False

        out_data = self.external.process(in_data, in_info)
        if out_data is not None:
            self.draw_canvas(out_data)
            if isinstance(out_data, dict) and out_data.get("send_process_data") is not None:
                self.parent.emit("process_data", "", out_data["send_process_data"])

        if do_record:
            self.recorder.sample(info, unsqueezed_data)

        return out_data, self.recorder.record

    def process_saved_data(self, record, parent):
        self.parent = parent
        self.init_vars()

        sensor_config_dict = json.loads(record.sensor_config_dump)
        rate = sensor_config_dict.get("update_rate", None)
        if rate is None and record.mode == modes.Mode.SPARSE:
            sweep_rate = sensor_config_dict.get("sweep_rate", None)
            if sweep_rate is None:
                sweep_rate = record.session_info.get("sweep_rate", None)
            if sweep_rate is not None:
                rate = sweep_rate / sensor_config_dict.get("sweeps_per_frame", 16)

        selected_sensors = self.sensor_config.sensor
        stored_sensors = sensor_config_dict["sensor"]

        sensor_list = []
        matching_sensors = []
        for sensor_idx in stored_sensors:
            if sensor_idx in selected_sensors:
                sensor_list.append(stored_sensors.index(sensor_idx))
                matching_sensors.append(sensor_idx)

        if not len(sensor_list) or len(matching_sensors) != len(selected_sensors):
            error = "Data is not available for all selected sensors {}.\n".format(selected_sensors)
            error += "I have data for sensors {} ".format(stored_sensors)
            self.parent.emit("set_sensors", "", stored_sensors)
            self.parent.emit("sensor_selection_error", error)
            return

        self.sensor_config.sensor = matching_sensors

        for subinfo, subdata in record:
            if self.abort:
                break

            if parent.parent.get_gui_state("ml_tab") != "feature_extract":
                if rate is not None:
                    time.sleep(1.0 / rate)
            else:
                QThread.msleep(3)

            subdata = subdata[sensor_list]
            self.process(subdata, subinfo, do_record=False)
            self.parent.emit("sweep_info", "", subinfo)

    def draw_canvas(self, plot_data):
        self.parent.emit("update_external_plots", "", plot_data)
