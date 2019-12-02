import time
import traceback
import warnings

from PyQt5.QtCore import QThread


warnings.filterwarnings("ignore")


class DataProcessing:
    hist_len = 500

    def prepare_processing(self, parent, params, session_info):
        self.parent = parent
        self.gui_handle = self.parent.parent
        self.sensor_config = params["sensor_config"]
        self.mode = self.sensor_config.mode
        self.service_type = params["service_type"]
        self.sweeps = self.gui_handle.sweep_count
        self.rate = 1/params["sensor_config"].sweep_rate
        self.hist_len = params["sweep_buffer"]
        self.service_params = params["service_params"]
        self.multi_sensor = params["multi_sensor"]

        self.ml_plotting = params["ml_plotting"]

        if isinstance(self.service_params, dict):
            self.service_params["processing_handle"] = self

        if self.sweeps < 0:
            self.sweeps = self.hist_len

        self.hist_len_index = 0

        self.session_info = session_info

        self.init_vars()

    def abort_processing(self):
        self.abort = True

    def init_vars(self):
        self.sweep = 0
        self.record = []
        self.n_std_avg = 0
        self.abort = False
        self.first_run = True
        self.skip = 0

    def update_feature_extraction(self, param, value=None):
        if isinstance(value, dict):
            settings = value
        else:
            settings = {param: value}
        try:
            self.external.update_processing_config(frame_settings=settings)
        except Exception:
            traceback.print_exc()

    def send_feature_trigger(self):
        try:
            self.external.update_processing_config(trigger=True)
        except Exception:
            traceback.print_exc()

    def update_feature_list(self, feature_list):
        try:
            self.external.update_processing_config(feature_list=feature_list)
        except Exception:
            traceback.print_exc()

    def process(self, sweep_data, info):
        if self.first_run:
            ext = self.gui_handle.external
            if self.ml_plotting:
                ext = self.gui_handle.ml_external
            self.external = ext(self.sensor_config, self.service_params, self.session_info)
            self.first_run = False
            plot_data = self.external.process(sweep_data)
        else:
            plot_data = self.external.process(sweep_data)
            if plot_data is not None:
                self.draw_canvas(plot_data)
                self.sweep += 1
                if isinstance(plot_data, dict) and plot_data.get("send_process_data") is not None:
                    self.parent.emit("process_data", "", plot_data["send_process_data"])

        self.record_data(sweep_data, info)

        return plot_data, self.record, self.sweep

    def record_data(self, sweep_data, info):
        plot_data = {
            "service_type": self.service_type,
            "sweep_data": sweep_data,
            "sensor_config": self.sensor_config,
            "info": info,
        }

        if self.hist_len_index >= self.hist_len:
            self.record.pop(0)
        else:
            self.hist_len_index += 1

        self.record.append(plot_data.copy())

    def process_saved_data(self, data, parent):
        self.parent = parent
        self.init_vars()
        self.sweep = 0

        try:
            self.sweeps = len(data)
        except Exception as e:
            self.parent.emit("error", "Wrong file format\n {}".format(e))
            return

        info_available = True
        is_session_format_new = True

        try:
            sequence_offset = max(data[0]["info"][0]["sequence_number"] - 1, 0)
        except Exception:
            try:
                sequence_offset = max(data[0]["info"]["sequence_number"] - 1, 0)
                is_session_format_new = False
            except Exception:
                info_available = False
                self.info = [{"sequence_number": 1}]
                print("Session info not available")

        selected_sensors = self.sensor_config.sensor
        stored_sensors = data[0]["sensor_config"].sensor
        nr_sensors = len(stored_sensors)

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

        squeezed_dim = 1
        if self.mode == "sparse":
            squeezed_dim = 2

        for i, data_step in enumerate(data):
            if info_available:
                if not is_session_format_new:
                    info = data[i]["info"]
                else:
                    info = data[i]["info"][0]
                info["sequence_number"] -= sequence_offset
            else:
                info = self.info.copy()
            if not self.abort:
                self.skip = 0

                if parent.parent.get_gui_state("ml_tab") != "feature_extract":
                    time.sleep(self.rate)

                sweep_data = data_step["sweep_data"]

                # Only send data for selected sensors
                if self.multi_sensor and nr_sensors > 1:
                    sweep_data = data_step["sweep_data"][sensor_list, :]

                # Make sure we send squeezed data to detectors not supporting multiple sensors
                if not self.multi_sensor and len(sweep_data.shape) > squeezed_dim:
                    sweep_data = data_step["sweep_data"][sensor_list[0], :]

                self.process(sweep_data, info)
                self.parent.emit("sweep_info", "", info)

            if not info_available:
                self.info[0]["sequence_number"] += 1

    def draw_canvas(self, plot_data):
        self.parent.emit("update_external_plots", "", plot_data)
        QThread.msleep(3)

        # TODO: use a queue for plot_data
