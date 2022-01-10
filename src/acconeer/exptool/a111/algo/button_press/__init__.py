import numpy as np
import pyqtgraph as pg

from PyQt5 import QtCore

import acconeer.exptool as et


OUTPUT_MAX_SIGNAL = 20000
OUTPUT_MAX_REL_DEV = 0.5
HISTORY_LENGTH_S = 10
DETECTION_SHOW_S = 2


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

    processor = ButtonPressProcessor(sensor_config, processing_config, session_info)

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
    config = et.configs.EnvelopeServiceConfig()
    config.profile = et.configs.EnvelopeServiceConfig.Profile.PROFILE_1
    config.range_interval = [0.04, 0.05]
    config.running_average_factor = 0.01
    config.maximize_signal_attenuation = True
    config.update_rate = 60
    config.gain = 0.2
    config.repetition_mode = et.configs.EnvelopeServiceConfig.RepetitionMode.SENSOR_DRIVEN
    return config


class ProcessingConfiguration(et.configbase.ProcessingConfig):
    VERSION = 2

    signal_tc_s = et.configbase.FloatParameter(
        label="Signal time constant",
        unit="s",
        default_value=5.0,
        limits=(0.01, 10),
        logscale=True,
        updateable=True,
        order=20,
        help="Time constant of the low pass filter for the signal.",
    )

    rel_dev_tc_s = et.configbase.FloatParameter(
        label="Relative deviation time constant",
        unit="s",
        default_value=0.2,
        limits=(0.01, 2),
        logscale=True,
        updateable=True,
        order=30,
        help="Time constant of the low pass filter for the relative deviation.",
    )

    threshold = et.configbase.FloatParameter(
        label="Detection threshold",
        default_value=0.2,
        decimals=3,
        limits=(0.001, 0.5),
        updateable=True,
        logscale=True,
        order=10,
        help='Level at which the detector output is considered as a "button press". '
        "Note that this might need adjustment depending "
        "on different board models in order to detect movement.",
    )

    buttonpress_length_s = et.configbase.FloatParameter(
        label="Button press length",
        unit="s",
        default_value=2.0,
        limits=(0.01, 5),
        logscale=False,
        updateable=True,
        order=40,
        help="The time after a detected button press when no further detection should occur.",
    )

    def check_sensor_config(self, sensor_config):
        alerts = {
            "processing": [],
            "sensor": [],
        }

        alerts["processing"].append(
            et.configbase.Info(
                "threshold", "Threshold level should be adjusted depending on board model."
            )
        )

        return alerts


get_processing_config = ProcessingConfiguration


class ButtonPressProcessor:
    # lp(f): low pass (filtered)
    # cut: cutoff frequency [Hz]
    # tc: time constant [s]
    # sf: smoothing factor [dimensionless]

    def __init__(self, sensor_config, processing_config, session_info):
        assert sensor_config.update_rate is not None

        self.f = sensor_config.update_rate

        self.signal_history = np.zeros(int(round(self.f * HISTORY_LENGTH_S)))
        self.signal_lp_history = np.zeros(int(round(self.f * HISTORY_LENGTH_S)))
        self.rel_dev_history = np.zeros(int(round(self.f * HISTORY_LENGTH_S)))
        self.rel_dev_lp_history = np.zeros(int(round(self.f * HISTORY_LENGTH_S)))
        self.detection_history = []
        self.signal_lp = 0.0
        self.rel_dev_lp = 0
        self.sweep_index = 0
        self.last_detection_sweep = 0

        self.update_processing_config(processing_config)

    def update_processing_config(self, processing_config):
        self.threshold = processing_config.threshold

        self.sf_signal = np.exp(-1.0 / (processing_config.signal_tc_s * self.f))
        self.sf_rel_dev = np.exp(-1.0 / (processing_config.rel_dev_tc_s * self.f))
        self.buttonpress_length_sweeps = processing_config.buttonpress_length_s * self.f

    def process(self, data, data_info):
        sweep = data

        # Sum the full sweep to a single number
        signal = np.mean(sweep)

        # Exponential filtering of the signal
        sf = min(self.sf_signal, 1.0 - 1.0 / (1.0 + self.sweep_index))
        self.signal_lp = sf * self.signal_lp + (1.0 - sf) * signal

        # The relative difference
        rel_dev = np.square((signal - self.signal_lp) / self.signal_lp)

        # Exponential filtering of the difference
        sf = min(self.sf_rel_dev, 1.0 - 1.0 / (1.0 + self.sweep_index))
        self.rel_dev_lp = sf * self.rel_dev_lp + (1.0 - sf) * rel_dev

        # Check detection
        detection = False
        sweeps_since_last_detect = self.sweep_index - self.last_detection_sweep
        detection_long_enough_ago = sweeps_since_last_detect > self.buttonpress_length_sweeps
        over_threshold = self.rel_dev_lp > self.threshold
        if over_threshold and detection_long_enough_ago:
            self.last_detection_sweep = self.sweep_index
            detection = True

        # Save all signal in history arrays.
        self.signal_history = np.roll(self.signal_history, -1)
        self.signal_history[-1] = signal

        self.signal_lp_history = np.roll(self.signal_lp_history, -1)
        self.signal_lp_history[-1] = self.signal_lp

        self.rel_dev_history = np.roll(self.rel_dev_history, -1)
        self.rel_dev_history[-1] = rel_dev

        self.rel_dev_lp_history = np.roll(self.rel_dev_lp_history, -1)
        self.rel_dev_lp_history[-1] = self.rel_dev_lp

        if detection:
            self.detection_history.append(self.sweep_index)

        while (
            len(self.detection_history) > 0
            and self.sweep_index - self.detection_history[0] > HISTORY_LENGTH_S * self.f
        ):
            self.detection_history.remove(self.detection_history[0])

        out_data = {
            "signal_history": self.signal_history,
            "signal_lp_history": self.signal_lp_history,
            "rel_dev_history": self.rel_dev_history,
            "rel_dev_lp_history": self.rel_dev_lp_history,
            "detection_history": (np.array(self.detection_history) - self.sweep_index) / self.f,
            "detection": detection,
            "sweep_index": self.sweep_index,
            "threshold": self.threshold,
        }

        self.sweep_index += 1

        return out_data


class PGUpdater:
    def __init__(self, sensor_config, processing_config, session_info):
        self.sensor_config = sensor_config
        self.processing_config = processing_config

        assert sensor_config.update_rate is not None

        self.setup_is_done = False

    def setup(self, win):
        win.setWindowTitle("Acconeer Button Press Example")

        self.limit_lines = []
        dashed_pen = pg.mkPen("k", width=2.5, style=QtCore.Qt.DashLine)

        self.sign_hist_plot = win.addPlot(title="Signal history")
        self.sign_hist_plot.setMenuEnabled(False)
        self.sign_hist_plot.setMouseEnabled(x=False, y=False)
        self.sign_hist_plot.hideButtons()
        self.sign_hist_plot.addLegend()
        self.sign_hist_plot.showGrid(x=True, y=True)
        self.sign_hist_plot.setLabel("bottom", "Time (s)")
        self.sign_hist_plot.setXRange(-HISTORY_LENGTH_S, 0)
        self.sign_hist_plot.setYRange(0, OUTPUT_MAX_SIGNAL)
        self.sign_hist_curve = self.sign_hist_plot.plot(
            pen=et.utils.pg_pen_cycler(0),
            name="Envelope signal",
        )
        self.sign_lp_hist_curve = self.sign_hist_plot.plot(
            pen=et.utils.pg_pen_cycler(1),
            name="Filtered envelope signal",
        )

        win.nextRow()

        self.rel_dev_hist_plot = win.addPlot(title="Relative deviation history")
        self.rel_dev_hist_plot.setMenuEnabled(False)
        self.rel_dev_hist_plot.setMouseEnabled(x=False, y=False)
        self.rel_dev_hist_plot.hideButtons()
        self.rel_dev_hist_plot.showGrid(x=True, y=True)
        self.rel_dev_hist_plot.setLabel("bottom", "Time (s)")
        self.rel_dev_hist_plot.setXRange(-HISTORY_LENGTH_S, 0)
        self.rel_dev_hist_plot.setYRange(0, OUTPUT_MAX_REL_DEV)
        self.rel_dev_lp_hist_curve = self.rel_dev_hist_plot.plot(
            pen=et.utils.pg_pen_cycler(0),
            name="Relative deviation",
        )

        self.detection_dots = self.rel_dev_hist_plot.plot(
            pen=None,
            symbol="o",
            symbolSize=20,
            symbolBrush=et.utils.color_cycler(1),
            name="Detections",
        )

        limit_line = pg.InfiniteLine(angle=0, pen=dashed_pen)
        self.rel_dev_hist_plot.addItem(limit_line)

        self.limit_lines.append(limit_line)

        self.detection_html_format = (
            '<div style="text-align: center">'
            '<span style="color: #FFFFFF;font-size:16pt;">'
            "{}</span></div>"
        )
        detection_html = self.detection_html_format.format("Button press detected!")

        self.detection_text_item = pg.TextItem(
            html=detection_html,
            fill=pg.mkColor(255, 140, 0),
            anchor=(0.5, 0),
        )

        self.detection_text_item.setPos(-HISTORY_LENGTH_S / 2, 0.95 * OUTPUT_MAX_REL_DEV)
        self.rel_dev_hist_plot.addItem(self.detection_text_item)
        self.detection_text_item.hide()

        self.smooth_max_signal = et.utils.SmoothMax(
            self.sensor_config.update_rate,
            hysteresis=0.6,
            tau_decay=3,
        )

        self.smooth_max_rel_dev = et.utils.SmoothMax(
            self.sensor_config.update_rate,
            hysteresis=0.6,
            tau_decay=3,
        )

        self.setup_is_done = True
        self.update_processing_config()

    def update_processing_config(self, processing_config=None):
        if processing_config is None:
            processing_config = self.processing_config
        else:
            self.processing_config = processing_config

        if not self.setup_is_done:
            return

        self.sign_hist_plot.setVisible(True)
        self.rel_dev_hist_plot.setVisible(True)

        for line in self.limit_lines:
            line.setPos(processing_config.threshold)

    def update(self, data):
        signal_hist_ys = data["signal_history"]
        signal_lp_hist_ys = data["signal_lp_history"]
        rel_dev_lp_hist_ys = data["rel_dev_lp_history"]
        t_detections = data["detection_history"]

        hist_xs = np.linspace(-HISTORY_LENGTH_S, 0, len(signal_hist_ys))

        self.sign_hist_curve.setData(hist_xs, signal_hist_ys)
        self.sign_lp_hist_curve.setData(hist_xs, signal_lp_hist_ys)
        self.rel_dev_lp_hist_curve.setData(hist_xs, rel_dev_lp_hist_ys)
        self.detection_dots.setData(t_detections, data["threshold"] * np.ones(len(t_detections)))

        m = np.max(signal_hist_ys) if signal_hist_ys.size > 0 else 1
        self.sign_hist_plot.setYRange(0, self.smooth_max_signal.update(m))

        m = np.max(rel_dev_lp_hist_ys) if rel_dev_lp_hist_ys.size > 0 else 1e-3
        m = max(2 * data["threshold"], m)
        ymax = self.smooth_max_rel_dev.update(m)
        self.rel_dev_hist_plot.setYRange(0, ymax)
        self.detection_text_item.setPos(-HISTORY_LENGTH_S / 2, 0.95 * ymax)

        show_detection_text = t_detections.size > 0 and (-t_detections[-1]) < DETECTION_SHOW_S
        self.detection_text_item.setVisible(bool(show_detection_text))


if __name__ == "__main__":
    main()
