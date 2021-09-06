import numpy as np
import pyqtgraph as pg

from PyQt5 import QtCore

import acconeer.exptool as et


A_WEEK_MINUTES = 10080.0
HISTORY_LENGTH_S = 10
SENSITIVITY_MAX = 10.0
MAX_ALLOWED_NOISE = 20
LP_AVERAGE_CONST_MAX = 0.9
LP_AVERAGE_CONST_INIT = 0.7

DOUBLE_PRESS_RATIO = 1.3  # Ratio between lp_constants for the trigger and cool down filters
THRESHOLD_RATIO = 2.0  # Ratio between trigger and cool down thresholds.

# Constants for calculating the number of intervals actually returned
SPARSE_RESOLUTION = 0.06
EPSILON = 0.00001

INIT_Y_RANGE = 500000


def main():
    args = et.utils.ExampleArgumentParser().parse_args()
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

    session_info = client.setup_session(sensor_config)

    pg_updater = PGUpdater(sensor_config, processing_config, session_info)
    pg_process = et.PGProcess(pg_updater)
    pg_process.start()

    client.start_session()

    interrupt_handler = et.utils.ExampleInterruptHandler()
    print("Press Ctrl-C to end session")

    processor = ButtonPressProcessor(sensor_config, processing_config, session_info)

    while not interrupt_handler.got_signal:
        data_info, data = client.get_next()
        plot_data = processor.process(data, data_info)

        if plot_data is not None:
            try:
                pg_process.put_data(plot_data)
            except et.PGProccessDiedException:
                break

    print("Disconnecting...")
    pg_process.close()
    client.disconnect()


def get_sensor_config():
    sensor_config = et.configs.SparseServiceConfig()
    sensor_config.range_interval = [0.04, 0.08]
    sensor_config.sweeps_per_frame = 64
    sensor_config.update_rate = 80
    sensor_config.hw_accelerated_average_samples = 32
    sensor_config.sampling_mode = sensor_config.SamplingMode.A
    sensor_config.profile = sensor_config.Profile.PROFILE_1
    sensor_config.gain = 0.0
    sensor_config.maximize_signal_attenuation = False
    sensor_config.downsampling_factor = 1
    sensor_config.tx_disable = False
    sensor_config.power_save_mode = sensor_config.PowerSaveMode.SLEEP
    sensor_config.repetition_mode = sensor_config.RepetitionMode.HOST_DRIVEN
    return sensor_config


class ProcessingConfiguration(et.configbase.ProcessingConfig):

    recalibration_period = et.configbase.FloatParameter(
        label="Time between recalibrations (minutes)",
        default_value=10.0,
        limits=(0.1, A_WEEK_MINUTES),
        logscale=True,
        updateable=True,
        order=10,
        help="How often the algorithm recalibrates itself",
    )

    sensitivity = et.configbase.FloatParameter(
        label="Detection sensitivity",
        default_value=9.0,
        limits=(0.0, SENSITIVITY_MAX),
        logscale=False,
        updateable=True,
        order=20,
        help="Sensitivity for how easily we detect a button press. "
        "Increasing the value increases the risk of false detects.",
    )

    double_press_speed = et.configbase.FloatParameter(
        label="Double press sensitivity",
        default_value=0.7,
        limits=(0.4, 0.99),
        logscale=False,
        updateable=True,
        order=30,
        help="Sensitivity for double presses. Lower values means more likely to double press.",
    )

    def sparse_round_down(self, num):
        """
        Downwards rounding to nearest multiple of 0.06 (sparse resolution in cm)
        """
        return SPARSE_RESOLUTION * round((num - EPSILON) / SPARSE_RESOLUTION)

    def sparse_round_up(self, num):
        """
        Upwards rounding to nearest multiple of 0.06 (sparse resolution in cm)
        """
        return SPARSE_RESOLUTION * round((num + EPSILON) / SPARSE_RESOLUTION)

    def check_sensor_config(self, sensor_config):

        alerts = {
            "processing": [],
            "sensor": [],
        }

        (rounded_bottom, rounded_top) = (
            self.sparse_round_down(sensor_config.range_interval[0]),
            self.sparse_round_up(sensor_config.range_interval[1]),
        )

        interval_length = int(round((rounded_top - rounded_bottom) / SPARSE_RESOLUTION)) + 1

        if rounded_bottom == 0.0:
            alerts["sensor"].append(
                et.configbase.Warning(
                    "range_interval",
                    "0.0 m point in range, increase range start for better performance",
                )
            )

        if interval_length == 2:
            alerts["sensor"].append(
                et.configbase.Warning(
                    "range_interval",
                    "The range may contain two points, a single point is recommended",
                )
            )
        elif interval_length > 2:
            alerts["sensor"].append(
                et.configbase.Error(
                    "range_interval", "The range contains too many points. Decrease range."
                )
            )

        if self.recalibration_period == A_WEEK_MINUTES:
            alerts["processing"].append(
                et.configbase.Info("recalibration_period", "Recalibration Off")
            )

        return alerts


get_processing_config = ProcessingConfiguration


class ButtonPressProcessor:
    def __init__(self, sensor_config, processing_config, session_info):

        self.f = sensor_config.update_rate
        self.signal_history = np.zeros(int(round(self.f * HISTORY_LENGTH_S)))
        self.average_history = np.zeros(int(round(self.f * HISTORY_LENGTH_S)))
        self.trig_history = np.zeros(int(round(self.f * HISTORY_LENGTH_S)))
        self.cool_down_history = np.zeros(int(round(self.f * HISTORY_LENGTH_S)))

        self.detection_history = []
        self.frame_count = 0
        self.sweeps_per_frame = sensor_config.sweeps_per_frame

        self.calibration_limit = max(
            1, int(round(sensor_config.update_rate))
        )  # So we always wait one second. This could be more sophisticated.
        self.noise_level_target = MAX_ALLOWED_NOISE

        self.calibrated = 0  # Repeated sending of calibrated signal to exptool plot thread

        self.chilled = True
        self.initialized = False

        # Low pass trig
        self.lp_trig = 0.0

        # Low pass cool down
        self.lp_cool_down = 0.0

        # Low pass average
        self.lp_average_const = LP_AVERAGE_CONST_INIT
        self.lp_average = 0.0

        self.update_processing_config(processing_config)

    def update_processing_config(self, processing_config):
        self.sensitivity = processing_config.sensitivity
        self.double_press_speed = processing_config.double_press_speed
        if processing_config.recalibration_period == A_WEEK_MINUTES:
            self.recalibration_frame_period = -1  # Effectively turning it off
        else:
            self.recalibration_frame_period = int(
                round(processing_config.recalibration_period * 60 * self.f)
            )

        self.set_sensitivity()
        self.set_double_press_speed()

    def set_double_press_speed(self):
        self.lp_trig_const = self.double_press_speed / DOUBLE_PRESS_RATIO
        self.lp_cool_down_const = self.double_press_speed

    def set_sensitivity(self):
        """
        Function to map the idea of "sensitivity between 0-10" to an actual threshold.
        """
        inv_sensitivity = (
            SENSITIVITY_MAX - self.sensitivity
        )  # since intuitively high sensitivity -> more likely to detect
        sens = 2 ** (1.1 * inv_sensitivity) * 600  # Yielding a nice exponential curve between 0-10
        self.threshold_trig = int(sens)
        self.threshold_cool_down = int(self.threshold_trig / THRESHOLD_RATIO)

    def lp_cool_down_filter(self, data):
        ret = int(
            self.lp_cool_down_const * self.lp_cool_down + (1.0 - self.lp_cool_down_const) * data
        )
        self.lp_cool_down = ret
        return ret

    def lp_trig_filter(self, data):
        ret = int(self.lp_trig_const * self.lp_trig + (1.0 - self.lp_trig_const) * data)
        self.lp_trig = ret
        return ret

    def lp_average_filter(self, data):
        ret = int(self.lp_average_const * self.lp_average + (1.0 - self.lp_average_const) * data)
        self.lp_average = ret
        return ret

    def calibrate(self):
        # Update the lp_average constant based on the noise levels.
        max_diff = max(
            abs(
                self.average_history[-self.calibration_limit :]
                - self.signal_history[-self.calibration_limit :]
            )
        )

        lp_new = (self.lp_average_const * self.noise_level_target) / max_diff
        if lp_new < LP_AVERAGE_CONST_MAX:
            self.lp_average_const = lp_new

    def detect(self, trig_val, cool_down_val):

        trig = False

        if self.chilled:
            if trig_val > self.threshold_trig:
                trig = True
                self.chilled = False
        else:
            if cool_down_val < self.threshold_cool_down:
                self.chilled = True
        return trig

    def process(self, frame, data_info):

        if not self.initialized:
            self.lp_average = int(np.mean(frame))
            self.initialized = True

        if self.frame_count % self.recalibration_frame_period == self.calibration_limit:
            self.calibrate()
            self.calibrated = 5

        signal = np.mean(frame, axis=(0, 1))

        lp_average = self.lp_average_filter(signal)  # Low pass to smooth the signal

        diff = int(abs(lp_average - signal))

        if diff < self.noise_level_target:
            diff = 0  # Get back to "detect" state asap

        diff_sq = (
            diff * diff
        )  # Squaring yields a bit simpler behaviour with regards to thresholds.

        trig_val = self.lp_trig_filter(diff_sq)
        cool_down_val = self.lp_cool_down_filter(diff_sq)

        # Triggering checks if it is considered a button press.
        # Cool down checks if we can trigger again.
        detection = self.detect(trig_val, cool_down_val)

        if self.frame_count <= self.calibration_limit:
            detection = False

        self.signal_history = np.roll(self.signal_history, -1)
        self.signal_history[-1] = signal

        self.average_history = np.roll(self.average_history, -1)
        self.average_history[-1] = lp_average

        self.trig_history = np.roll(self.trig_history, -1)
        self.trig_history[-1] = trig_val

        self.cool_down_history = np.roll(self.cool_down_history, -1)
        self.cool_down_history[-1] = cool_down_val

        if detection:
            self.detection_history.append(self.frame_count)

        if self.calibrated > 0:
            calibrated = True
            self.calibrated -= 1
        else:
            calibrated = False

        out_data = {
            "signal_history": self.signal_history,
            "average_history": self.average_history,
            "trig_history": self.trig_history,
            "cool_down_history": self.cool_down_history,
            "threshold": self.threshold_trig,
            "detection_history": (np.array(self.detection_history) - self.frame_count) / self.f,
            "detection": detection,
            "calibrated": calibrated,
        }

        self.frame_count += 1

        return out_data


class PGUpdater:
    def __init__(self, sensor_config, processing_config, session_info):
        self.sensor_config = sensor_config
        self.depths = et.utils.get_range_depths(sensor_config, session_info)
        self.processing_config = processing_config

    def setup(self, win):
        win.setWindowTitle("Acconeer button press sparse example")

        dashed_pen = pg.mkPen("k", width=2.5, style=QtCore.Qt.DashLine)

        self.calibrated_text_vis_age = 0

        self.signal_hist_plot = win.addPlot(title="Signal history")
        self.signal_hist_plot.setMenuEnabled(False)
        self.signal_hist_plot.setMouseEnabled(x=False, y=False)
        self.signal_hist_plot.addLegend()
        self.signal_hist_plot.hideButtons()
        self.signal_hist_plot.showGrid(x=True, y=True)
        self.signal_hist_plot.setLabel("bottom", "Time (s)")
        self.signal_hist_plot.setXRange(-HISTORY_LENGTH_S, 0)
        self.signal_hist_plot.setYRange(0, 2 ** 15)

        self.signal_hist_curve = self.signal_hist_plot.plot(
            pen=et.utils.pg_pen_cycler(0),
            name="Signal",
        )
        self.average_hist_curve = self.signal_hist_plot.plot(
            pen=et.utils.pg_pen_cycler(1),
            name="Low pass filtered signal",
        )

        win.nextRow()

        self.proc_plot = win.addPlot(title="Processing history")
        self.proc_plot.setMenuEnabled(False)
        self.proc_plot.setMouseEnabled(x=False, y=False)
        self.proc_plot.hideButtons()
        self.proc_plot.showGrid(x=True, y=True)
        self.proc_plot.setLabel("bottom", "Trigger variable values")
        self.proc_plot.setXRange(-HISTORY_LENGTH_S, 0)
        self.proc_plot.setYRange(0, INIT_Y_RANGE)

        self.trig_hist_curve = self.proc_plot.plot(
            pen=et.utils.pg_pen_cycler(0),
            name="Trig value",
        )

        self.cool_down_hist_curve = self.proc_plot.plot(
            pen=et.utils.pg_pen_cycler(1),
            name="Cool down value",
        )

        self.detection_dots = self.proc_plot.plot(
            pen=None,
            symbol="o",
            symbolSize=20,
            symbolBrush=et.utils.color_cycler(2),
            name="Detections",
        )

        self.limit_line = pg.InfiniteLine(angle=0, pen=dashed_pen)
        self.proc_plot.addItem(self.limit_line)

        self.smooth_limits = et.utils.SmoothLimits(
            self.sensor_config.update_rate, hysteresis=0.1, tau_decay=3, tau_grow=1
        )

        self.smooth_max_proc = et.utils.SmoothMax(
            self.sensor_config.update_rate,
            hysteresis=0.6,
            tau_decay=3,
        )

        self.calibration_html_format = (
            '<div style="text-align: center">'
            '<span style="color: #FFFFFF;font-size:16pt;">'
            "{}</span></div>"
        )
        calibration_html = self.calibration_html_format.format("Calibrated!")
        self.calibration_text_item = pg.TextItem(
            html=calibration_html,
            fill=pg.mkColor(255, 140, 0),
            anchor=(0.5, 0),
        )

        self.calibration_text_item.setPos(-HISTORY_LENGTH_S / 2, 0.95 * INIT_Y_RANGE)
        self.proc_plot.addItem(self.calibration_text_item)
        self.calibration_text_item.hide()

    def update(self, data):

        signal_hist_ys = data["signal_history"]
        average_hist_ys = data["average_history"]
        cool_down_hist_ys = data["cool_down_history"]
        trig_hist_ys = data["trig_history"]
        t_detections = data["detection_history"]
        calibrated = data["calibrated"]
        hist_xs = np.linspace(-HISTORY_LENGTH_S, 0, len(signal_hist_ys))

        self.signal_hist_curve.setData(hist_xs, signal_hist_ys)
        self.average_hist_curve.setData(hist_xs, average_hist_ys)

        self.trig_hist_curve.setData(hist_xs, trig_hist_ys)
        self.cool_down_hist_curve.setData(hist_xs, cool_down_hist_ys)

        self.detection_dots.setData(t_detections, data["threshold"] * np.ones(len(t_detections)))
        self.limit_line.setPos(data["threshold"])

        limits = self.smooth_limits.update(signal_hist_ys)

        m = 2 * data["threshold"]
        ymax = self.smooth_max_proc.update(m)

        self.signal_hist_plot.setYRange(limits[0], limits[1])
        self.proc_plot.setYRange(0, ymax)

        self.calibration_text_item.setPos(-HISTORY_LENGTH_S / 2, 0.95 * ymax)

        if calibrated:
            self.calibrated_text_vis_age = len(data["signal_history"]) / 10

        if self.calibrated_text_vis_age > 0:
            self.calibration_text_item.setVisible(True)
            self.calibrated_text_vis_age -= 1
        else:
            self.calibration_text_item.setVisible(False)


if __name__ == "__main__":
    main()
