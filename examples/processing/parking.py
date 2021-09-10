import warnings

import numpy as np
import pyqtgraph as pg

import acconeer.exptool as et


ENVELOPE_BACKGROUND_LEVEL = 100


def main():
    args = et.utils.ExampleArgumentParser(num_sens=1).parse_args()
    et.utils.config_logging(args)

    if args.socket_addr:
        client = et.SocketClient(args.socket_addr)
    elif args.spi:
        client = et.SPIClient()
    else:
        port = args.serial_port or et.utils.autodetect_serial_port()
        client = et.UARTClient(port)

    sensor_config = get_sensor_config()
    processing_config = get_processing_config()
    sensor_config.sensor = args.sensors

    session_info = client.setup_session(sensor_config)

    pg_updater = PGUpdater(sensor_config, processing_config, session_info)
    pg_process = et.PGProcess(pg_updater)

    pg_process.start()

    client.start_session()

    interrupt_handler = et.utils.ExampleInterruptHandler()
    print("Press Ctrl-C to end session")

    processor = Processor(sensor_config, processing_config, session_info)

    while not interrupt_handler.got_signal:
        info, sweep = client.get_next()
        plot_data = processor.process(sweep, info)

        if plot_data is not None:
            try:
                pg_process.put_data(plot_data)
            except et.PGProccessDiedException:
                break

    print("Disconnecting...")
    pg_process.close()
    client.disconnect()


def get_sensor_config():
    config = et.EnvelopeServiceConfig()
    config.downsampling_factor = 2
    config.range_interval = [0.12, 0.62]
    config.running_average_factor = 0
    config.update_rate = 0.5
    config.hw_accelerated_average_samples = 20
    config.power_save_mode = et.configs.BaseServiceConfig.PowerSaveMode.OFF
    config.asynchronous_measurement = False

    return config


class Processor:
    def __init__(self, sensor_config, processing_config, session_info):
        self.session_info = session_info

        self.f = sensor_config.update_rate
        self.depths = et.utils.get_range_depths(sensor_config, session_info)

        self.update_processing_config(processing_config)

    def update_processing_config(self, processing_config):
        self.depth_leak_sample = processing_config.depth_leak_sample
        self.depth_leak_end = processing_config.depth_leak_end
        self.leak_max_amplitude = processing_config.leak_max_amplitude
        self.detector_queue_target_length = processing_config.detector_queue_target_length
        self.weight_threshold = processing_config.weight_threshold
        self.weight_ratio_limit = processing_config.weight_ratio_limit
        self.distance_difference_limit = processing_config.distance_difference_limit

        start = self.session_info["range_start_m"]
        step = self.session_info["step_length_m"]
        self.leak_sample_index = int(round((self.depth_leak_sample - start) / step))
        self.leak_end_index = int(round((self.depth_leak_end - start) / step))
        self.leak_estimate_depths = np.array(
            [
                self.depths[0] + step * self.leak_sample_index,
                self.depths[0] + step * self.leak_end_index,
            ]
        )
        self.queued_weights = []
        self.queued_distances = []

        history_length = int(round(self.f * processing_config.history_length_s)) + 1
        self.detection_history = np.zeros(history_length) * float("nan")
        self.detection_history_t = np.linspace(-(history_length - 1) / self.f, 0, history_length)

    def process(self, data, data_info=None):
        if data_info is None:
            warnings.warn(
                "To leave out data_info or set to None is deprecated",
                DeprecationWarning,
                stacklevel=2,
            )

        sweep = data
        valid_leak_setup = (
            0 <= self.leak_sample_index
            and self.leak_sample_index < self.leak_end_index
            and self.leak_sample_index < len(sweep)
        )
        if valid_leak_setup:
            leak_amplitude = min(self.leak_max_amplitude, sweep[self.leak_sample_index])
            a_leak = max(leak_amplitude - ENVELOPE_BACKGROUND_LEVEL, 0)
            leak_step = a_leak / (self.leak_end_index - self.leak_sample_index)
            leak_start = self.leak_end_index * leak_step + ENVELOPE_BACKGROUND_LEVEL

            bg_near = np.linspace(leak_start, ENVELOPE_BACKGROUND_LEVEL, self.leak_end_index + 1)
            bg_far_len = len(sweep) - (self.leak_end_index + 1)
            if bg_far_len > 0:
                bg_far = np.ones(bg_far_len) * ENVELOPE_BACKGROUND_LEVEL
                background = np.append(bg_near, bg_far)
            else:
                background = bg_near[: len(sweep)]
        else:
            leak_amplitude = float("nan")
            background = np.ones(len(sweep)) * ENVELOPE_BACKGROUND_LEVEL

        leak_estimate = np.array([leak_amplitude, ENVELOPE_BACKGROUND_LEVEL])
        samples_above_bg = np.fmax(sweep - background, 0)
        weight = (
            np.fmin(samples_above_bg / ENVELOPE_BACKGROUND_LEVEL, 1)
            * samples_above_bg
            * self.depths
        )

        weight_sum = np.sum(weight)

        sweep_weight = weight_sum / len(weight)
        sweep_distance = np.sum(weight * self.depths) / weight_sum

        # Pops the oldest item in the detector queue if the queue is full
        if len(self.queued_weights) == self.detector_queue_target_length:
            self.queued_weights = self.queued_weights[1:]
            self.queued_distances = self.queued_distances[1:]

        self.queued_weights.append(sweep_weight)
        self.queued_distances.append(sweep_distance)

        weight_min = min(self.queued_weights)
        weight_max = max(self.queued_weights)
        distance_min = min(self.queued_distances)
        distance_max = max(self.queued_distances)

        # The final criterion evaluation for parking detection
        detection = (
            len(self.queued_weights) == self.detector_queue_target_length
            and weight_min >= self.weight_threshold
            and weight_max / weight_min <= self.weight_ratio_limit
            and distance_max - distance_min <= self.distance_difference_limit
        )

        self.detection_history = np.roll(self.detection_history, -1)
        self.detection_history[-1] = detection

        # Calculates limits_center used to visualize the detection criterion
        limits_center = (np.sqrt(weight_min * weight_max), (distance_min + distance_max) / 2)

        out_data = {
            "sweep": sweep,
            "leak_estimate": leak_estimate,
            "leak_estimate_depths": self.leak_estimate_depths,
            "background": background,
            "weight": weight,
            "queued_weights": np.array(self.queued_weights),
            "queued_distances": np.array(self.queued_distances),
            "limits_center": limits_center,
            "detection_history": self.detection_history,
            "detection_history_t": self.detection_history_t,
        }

        return out_data


class ProcessingConfiguration(et.configbase.ProcessingConfig):

    VERSION = 2

    depth_leak_sample = et.configbase.FloatParameter(
        label="Leak sample position",
        default_value=0.15,
        limits=(0.05, 0.25),
        unit="m",
        logscale=False,
        decimals=3,
        updateable=True,
        order=0,
        help="Distance from the sensor for the leak sample position",
    )

    depth_leak_end = et.configbase.FloatParameter(
        label="Leak end position",
        default_value=0.30,
        limits=(0.10, 0.50),
        unit="m",
        logscale=False,
        decimals=3,
        updateable=True,
        order=1,
        help="Worst case distance from the sensor for the end of leak reflections",
    )

    leak_max_amplitude = et.configbase.FloatParameter(
        label="Max leak amplitude",
        default_value=2000,
        limits=(100, 10000),
        logscale=True,
        decimals=0,
        updateable=True,
        order=2,
        help=(
            "The largest expected amplitude at the leak sample position when there is "
            "no object above the sensor"
        ),
    )

    detector_queue_target_length = et.configbase.IntParameter(
        label="Detector queue length",
        default_value=3,
        limits=(1, 10),
        updateable=True,
        order=3,
        help=(
            "Car detection criterion parameter: "
            "The number of sweep value pairs (weight, distance) in the detector queue"
        ),
    )

    weight_threshold = et.configbase.FloatParameter(
        label="Weight threshold",
        default_value=5,
        limits=(0.5, 500),
        logscale=True,
        decimals=1,
        updateable=True,
        order=4,
        help=(
            "Car detection criterion parameter: "
            "Minimal value of the weights in the detector queue"
        ),
    )

    weight_ratio_limit = et.configbase.FloatParameter(
        label="Weight ratio limit",
        default_value=3,
        limits=(1, 10),
        logscale=True,
        decimals=2,
        updateable=True,
        order=5,
        help=(
            "Car detection criterion parameter: "
            "Maximal ratio between the maximal and the minimal weights in the detector queue"
        ),
    )

    distance_difference_limit = et.configbase.FloatParameter(
        label="Distance limit",
        default_value=0.1,
        limits=(0.01, 0.5),
        logscale=True,
        decimals=3,
        updateable=True,
        order=6,
        help=(
            "Car detection criterion parameter: "
            "Maximal difference between the maximal and minimal distances in the detector queue"
        ),
    )

    history_length_s = et.configbase.FloatParameter(
        label="History length",
        unit="s",
        default_value=300,
        limits=(1, 3600),
        logscale=True,
        decimals=0,
        updateable=True,
        order=100,
        help='The time interval that is shown in the "Detection history" plot',
    )

    def check(self):
        alerts = []

        if self.depth_leak_sample >= self.depth_leak_end:
            alerts.append(
                et.configbase.Error("depth_leak_sample", "Must be less than the leak end position")
            )

        return alerts

    def check_sensor_config(self, sensor_config):
        alerts = {
            "processing": [],
            "sensor": [],
        }
        if sensor_config.update_rate is None:
            alerts["sensor"].append(et.configbase.Error("update_rate", "Must be set"))

        if not sensor_config.noise_level_normalization:
            alerts["sensor"].append(
                et.configbase.Error("noise_level_normalization", "Must be set")
            )

        if (
            self.depth_leak_sample < sensor_config.range_start
            or self.depth_leak_sample > sensor_config.range_end
        ):
            alerts["sensor"].append(
                et.configbase.Error(
                    "range_interval", "Leak sample position outside the range interval"
                )
            )

        return alerts


get_processing_config = ProcessingConfiguration


class PGUpdater:
    def __init__(self, sensor_config, processing_config, session_info):
        self.sensor_config = sensor_config
        self.processing_config = processing_config

        self.depths = et.utils.get_range_depths(sensor_config, session_info)

    def update_processing_config(self, processing_config=None):
        if processing_config is None:
            processing_config = self.processing_config
        else:
            self.processing_config = processing_config

        hist_s = processing_config.history_length_s
        self.hist_plot.setXRange(-hist_s, 0.06 * hist_s)

        self.limit_line.setPos(processing_config.weight_threshold)
        self.update_detection_limits()

    def setup(self, win):
        win.setWindowTitle("Acconeer Parking Detector")

        # Sweep Plot
        self.sweep_plot = win.addPlot(title="Sweep")
        self.sweep_plot.setMenuEnabled(False)
        self.sweep_plot.setMouseEnabled(x=False, y=False)
        self.sweep_plot.hideButtons()
        self.sweep_plot.showGrid(x=True, y=True)
        self.sweep_plot.addLegend(offset=(-10, 10))
        self.sweep_plot.setLabel("bottom", "Distance (cm)")
        self.sweep_plot.setLabel("left", "Amplitude")
        self.sweep_plot.setYRange(0, 2000)
        self.sweep_plot.setXRange(100.0 * self.depths[0], 100.0 * self.depths[-1])

        self.sweep_curve = self.sweep_plot.plot(
            pen=et.utils.pg_pen_cycler(0),
            name="Envelope sweep",
        )

        self.sweep_background = self.sweep_plot.plot(
            pen=et.utils.pg_pen_cycler(2),
            name="Background estimate",
        )

        self.leak_estimate = self.sweep_plot.plot(
            pen=None,
            symbol="o",
            symbolSize=8,
            symbolPen="k",
            symbolBrush=et.utils.color_cycler(1),
            name="Leak estimate",
        )

        # To show the legend correctly before the first update
        self.leak_estimate.setData([], [])

        self.smooth_max_sweep = et.utils.SmoothMax(
            self.sensor_config.update_rate,
            hysteresis=0.6,
            tau_decay=5,
        )

        win.nextRow()

        # Reflector weight Plot
        self.weight_plot = win.addPlot(title="Reflection observables")
        self.weight_plot.setMenuEnabled(False)
        self.weight_plot.setMouseEnabled(x=False, y=False)
        self.weight_plot.hideButtons()
        self.weight_plot.showGrid(x=True, y=True)
        self.weight_plot.addLegend(offset=(-10, 10))
        self.weight_plot.setLabel("bottom", "Distance (cm)")
        self.weight_plot.setLabel("left", "Weight")
        self.weight_plot.setYRange(0, 500)
        self.weight_plot.setXRange(100.0 * self.depths[0], 100.0 * self.depths[-1])

        self.detection_html_format = (
            '<div style="text-align: center">'
            '<span style="color: #FFFFFF;font-size:16pt;">'
            "{}</span></div>"
        )
        detection_html = self.detection_html_format.format("Parked car detected!")

        self.detection_text_item = pg.TextItem(
            html=detection_html,
            fill=pg.mkColor(255, 140, 0),
            anchor=(0.5, 0),
        )

        self.weight_plot.addItem(self.detection_text_item)
        self.detection_text_item.hide()

        self.weight_curve = self.weight_plot.plot(
            pen=et.utils.pg_pen_cycler(0),
            name="Reflector weight",
        )

        self.limits_center = None
        self.detection_limits = self.weight_plot.plot(
            pen=et.utils.pg_pen_cycler(3),
            name="Detection limits",
        )
        self.limit_line = pg.InfiniteLine(angle=0, pen=et.utils.pg_pen_cycler(3, "--"))
        self.weight_plot.addItem(self.limit_line)

        self.trailing_sweeps = self.weight_plot.plot(
            pen=None,
            symbol="o",
            symbolSize=8,
            symbolPen="k",
            symbolBrush=et.utils.color_cycler(2),
            name="Queued sweep",
        )

        self.current_sweep = self.weight_plot.plot(
            pen=None,
            symbol="o",
            symbolSize=8,
            symbolPen="k",
            symbolBrush=et.utils.color_cycler(1),
            name="Last sweep",
        )

        # To show the legends correctly before the first update
        self.trailing_sweeps.setData([], [])
        self.current_sweep.setData([], [])

        self.smooth_max_weight = et.utils.SmoothMax(
            self.sensor_config.update_rate,
            hysteresis=0.6,
            tau_decay=5,
        )

        win.nextRow()

        # Detection history Plot
        self.hist_plot = win.addPlot(title="Detection history")
        self.hist_plot.setMenuEnabled(False)
        self.hist_plot.setMouseEnabled(x=False, y=False)
        self.hist_plot.hideButtons()
        self.hist_plot.showGrid(x=True, y=False)
        self.hist_plot.hideAxis("left")
        self.hist_plot.setLabel("bottom", "Time (s)")
        self.hist_plot.setYRange(-0.5, 1.5)
        self.true_text_item = pg.TextItem("True", color=pg.mkColor(0, 0, 0), anchor=(0, 0.5))
        self.true_text_item.setPos(0.01 * self.processing_config.history_length_s, 1)
        self.false_text_item = pg.TextItem("False", color=pg.mkColor(0, 0, 0), anchor=(0, 0.5))
        self.false_text_item.setPos(0.01 * self.processing_config.history_length_s, 0)
        self.hist_plot.addItem(self.true_text_item)
        self.hist_plot.addItem(self.false_text_item)

        self.hist_dots = self.hist_plot.plot(
            pen=None,
            symbol="o",
            symbolSize=5,
            symbolPen="k",
            symbolBrush=et.utils.color_cycler(0),
        )

        win.layout.setRowStretchFactor(0, 8)
        win.layout.setRowStretchFactor(1, 9)

        self.update_processing_config()

    def update_detection_limits(self):
        if self.limits_center is not None:
            pc = self.processing_config
            criterion_weight_min = self.limits_center[0] / np.sqrt(pc.weight_ratio_limit)
            if criterion_weight_min < pc.weight_threshold:
                criterion_weight_min = pc.weight_threshold
            criterion_weight_max = criterion_weight_min * pc.weight_ratio_limit

            criterion_distance_min = self.limits_center[1] - pc.distance_difference_limit / 2
            criterion_distance_max = criterion_distance_min + pc.distance_difference_limit

            weight_limits = [
                criterion_weight_max,
                criterion_weight_max,
                criterion_weight_min,
                criterion_weight_min,
            ]
            distance_limits = [
                criterion_distance_max,
                criterion_distance_min,
                criterion_distance_min,
                criterion_distance_max,
            ]

            weight_limits.append(weight_limits[0])
            distance_limits.append(distance_limits[0])

            weight_limits = np.array(weight_limits)
            distance_limits = np.array(distance_limits)

            self.detection_limits.setData(100.0 * distance_limits, weight_limits)

    def update(self, data):
        self.sweep_curve.setData(100.0 * self.depths, data["sweep"])
        self.leak_estimate.setData(100.0 * data["leak_estimate_depths"], data["leak_estimate"])
        self.sweep_background.setData(100.0 * self.depths, data["background"])
        self.weight_curve.setData(100.0 * self.depths, data["weight"])
        self.limits_center = data["limits_center"]
        self.update_detection_limits()
        self.trailing_sweeps.setData(
            100.0 * data["queued_distances"][:-1], data["queued_weights"][:-1]
        )
        self.current_sweep.setData(
            100.0 * data["queued_distances"][-1:], data["queued_weights"][-1:]
        )
        self.hist_dots.setData(data["detection_history_t"], data["detection_history"])

        ymax = self.smooth_max_sweep.update(np.nanmax(data["sweep"]))
        self.sweep_plot.setYRange(0, ymax)

        ymax = self.smooth_max_weight.update(
            np.nanmax(np.append(data["weight"], data["queued_weights"]))
        )
        self.weight_plot.setYRange(0, ymax)
        xmid = (self.depths[0] + self.depths[-1]) / 2
        self.detection_text_item.setPos(100.0 * xmid, 0.95 * ymax)
        self.detection_text_item.setVisible(bool(data["detection_history"][-1]))


if __name__ == "__main__":
    main()
