import numpy as np
import time

import warnings
warnings.filterwarnings("ignore")


class DataProcessing:
    hist_len = 500

    def prepare_processing(self, parent, params):
        self.sensor_config = params["sensor_config"]
        self.mode = self.sensor_config.mode
        self.service_type = params["service_type"]
        self.create_cl = params["create_clutter"]
        self.use_cl = params["use_clutter"]
        self.cl_file = params["clutter_file"]
        self.sweeps = parent.parent.sweep_count
        self.rate = 1/params["sensor_config"].sweep_rate
        self.hist_len = params["sweep_buffer"]
        self.service_params = params["service_params"]

        if self.service_params is not None:
            self.service_params["processing_handle"] = self

        if self.sweeps < 0:
            self.sweeps = self.hist_len

        if self.create_cl:
            self.sweeps = params["service_params"]["sweeps_requested"]

        self.parent = parent
        self.hist_len_index = 0

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

        self.cl = np.zeros((0, 1))
        self.cl_iq = np.zeros((0, 1), dtype="complex")

    def set_clutter_flag(self, enable):
        self.use_cl = enable

        try:
            self.service_params["use_clutter"] = enable
            self.external.update_processing_config(self.service_params)
        except Exception:
            pass

    def load_clutter_data(self, cl_length, cl_file=None):
        load_success = True
        error = None

        if cl_file:
            try:
                cl_data = np.load(cl_file, allow_pickle=True)
            except Exception as e:
                error = "Cannot load clutter ({})\n\n{}".format(cl_file, e)
                load_success = False
        else:
            load_success = False

        if load_success:
            try:
                cl = cl_data.item()["cl_env"]
                cl_iq = cl_data.item()["cl_iq"]
                thrshld = cl_data.item()["cl_env_std"]
                cl_config = cl_data.item()["config"]
                if not np.isclose(cl_config.gain, self.sensor_config.gain):
                    load_success = False
                    error = "Wrong gain:\n Clutter is {} and scan is {}".format(
                        cl_config.gain, self.sensor_config.gain)
                if not np.isclose(cl_config.range_interval,
                                  self.sensor_config.range_interval).any():
                    error = "Wrong range:\n Clutter is {} and scan is {}".format(
                        cl_config.range_interval, self.sensor_config.range_interval)
                if cl_config.mode != self.sensor_config.mode:
                    error = "Wrong modes:\n Clutter is {} and scan is {}".format(
                        cl_config.mode, self.sensor_config.mode)
                if error:
                    load_success = False
            except Exception as e:
                error = "Error loading clutter:\n {}".format(self.parent.format_error(e))
                load_success = False

        if not load_success:
            cl = np.zeros(cl_length)
            thrshld = cl
            cl_iq = cl
            self.use_cl = False
            if error:
                try:
                    error += "\nFile: {:s}\n".format(cl_file)
                except Exception:
                    pass
                self.parent.emit("clutter_error", error)

        return (cl, cl_iq, thrshld)

    def process(self, sweep_data, info):
        if self.first_run:
            self.external = self.parent.parent.external(self.sensor_config, self.service_params)
            self.first_run = False
            self.service_widget = self.parent.parent.service_widget
            plot_data = self.external.process(sweep_data)
        else:
            plot_data = self.external.process(sweep_data)
            if plot_data is not None:
                self.draw_canvas(self.sweep, plot_data, "update_external_plots")
                self.sweep += 1
                if isinstance(plot_data, dict) and plot_data.get("send_process_data") is not None:
                    self.parent.emit("process_data", "", plot_data["send_process_data"])

                if self.create_cl and self.sweep == self.sweeps - 1:
                    self.process_clutter_data(plot_data["clutter_raw"])

        self.record_data(sweep_data, info)

        return plot_data, self.record, self.sweep

    def process_clutter_data(self, cl_data):
        cl = np.zeros((3, len(cl_data[0])))
        cl[0] = np.mean(np.abs(cl_data), axis=0)
        cl[2] = np.mean(cl_data, axis=0)

        for i in range(len(cl_data[0])):
            cl[1, i] = np.std(cl_data[:, i])

        cl_data = {
            "cl_env": cl[0],
            "cl_env_std": cl[1],
            "cl_iq": cl[2],
            "config": self.sensor_config,
        }

        self.parent.emit("clutter_data", "", cl_data)

    def record_data(self, sweep_data, info):
        plot_data = {
            "service_type": self.service_type,
            "sweep_data": sweep_data,
            "sensor_config": self.sensor_config,
            "cl_file": self.cl_file,
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
        self.create_cl = False

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
                time.sleep(self.rate)

                if nr_sensors == 1:
                    self.process(data_step["sweep_data"], info)
                else:
                    self.process(data_step["sweep_data"][sensor_list, :], info)

                self.parent.emit("sweep_info", "", info)

            if not info_available:
                self.info[0]["sequence_number"] += 1

    def draw_canvas(self, sweep_index, plot_data, cmd="update_plots",
                    skip_frames=False):
        if not skip_frames:
            self.update_plots(plot_data, cmd=cmd)
            return

        if self.skip <= 1:
            if sweep_index == 0:
                self.time = time.time()
            self.update_plots(plot_data, cmd=cmd)
            rate = time.time() - self.time
            self.time = time.time()
            self.skip = rate / self.rate
            if self.skip > 1:
                self.skip = np.ceil(self.skip)
        else:
            self.skip -= 1
            if self.skip <= 1:
                self.time = time.time()

    def update_plots(self, plot_data, cmd="update_plots"):
        self.parent.emit(cmd, "", plot_data)
