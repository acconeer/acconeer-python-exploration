import numpy as np
import pyqtgraph as pg
from PyQt5 import QtCore

from acconeer.exptool.clients import SocketClient, SPIClient, UARTClient
from acconeer.exptool import configs
from acconeer.exptool import example_utils
from acconeer.exptool.pg_process import PGProcess, PGProccessDiedException
from acconeer.exptool.structs import configbase


OUTPUT_MAX_SIGNAL = 20000
OUTPUT_MAX_REL_DEV = 0.5
HISTORY_LENGTH_S = 10
DETECTION_SHOW_S = 2


def main():
    args = example_utils.ExampleArgumentParser(num_sens=1).parse_args()
    example_utils.config_logging(args)

    if args.socket_addr:
        client = SocketClient(args.socket_addr)
    elif args.spi:
        client = SPIClient()
    else:
        port = args.serial_port or example_utils.autodetect_serial_port()
        client = UARTClient(port)

    sensor_config = get_sensor_config()
    processing_config = get_processing_config()
    sensor_config.sensor = args.sensors

    session_info = client.setup_session(sensor_config)

    pg_updater = PGUpdater(sensor_config, processing_config, session_info)
    pg_process = PGProcess(pg_updater)
    pg_process.start()

    client.start_streaming()

    interrupt_handler = example_utils.ExampleInterruptHandler()
    print("Press Ctrl-C to end session")

    processor = ButtonPressProcessor(sensor_config, processing_config, session_info)

    while not interrupt_handler.got_signal:
        info, sweep = client.get_next()
        plot_data = processor.process(sweep)

        if plot_data is not None:
            try:
                pg_process.put_data(plot_data)
            except PGProccessDiedException:
                break

    print("Disconnecting...")
    pg_process.close()
    client.disconnect()


def get_sensor_config():
    config = configs.EnvelopeServiceConfig()
    config.session_profile = configs.EnvelopeServiceConfig.DIRECT_LEAKAGE
    config.range_interval = [0.04, 0.05]
    config.running_average_factor = 0.01
    config.sweep_rate = 60
    config.gain = 0.2
    return config


class ProcessingConfiguration(configbase.ProcessingConfig):
    VERSION = 2

    signal_tc_s = configbase.FloatParameter(
            label="Signal time constant",
            unit="s",
            default_value=5.0,
            limits=(0.01, 10),
            logscale=True,
            updateable=True,
            order=10,
            help="Time constant of the low pass filter for the signal.",
            )

    rel_dev_tc_s = configbase.FloatParameter(
            label="Relative deviation time constant",
            unit="s",
            default_value=0.2,
            limits=(0.01, 2),
            logscale=True,
            updateable=True,
            order=20,
            help=" Time constant of the low pass filter for the relative deviation.",
            )

    threshold = configbase.FloatParameter(
            label="Detection threshold",
            default_value=0.04,
            decimals=3,
            limits=(0.001, 0.5),
            updateable=True,
            logscale=True,
            order=30,
            help="Level at which the detector output is considered as a \"button press\".",
            )

    buttonpress_length_s = configbase.FloatParameter(
            label="Button press length",
            unit="s",
            default_value=2.0,
            limits=(0.01, 5),
            logscale=False,
            updateable=True,
            order=40,
            help=(
                 "The time after a detected button press when no further detection"
                 " should occur."
            ),
            )


get_processing_config = ProcessingConfiguration


class ButtonPressProcessor:
    # lp(f): low pass (filtered)
    # cut: cutoff frequency [Hz]
    # tc: time constant [s]
    # sf: smoothing factor [dimensionless]

    def __init__(self, sensor_config, processing_config, session_info):
        self.f = sensor_config.sweep_rate

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
        self.buttonpress_length_sweeps = processing_config.buttonpress_length_s*self.f

    def process(self, sweep):
        # Sum the full sweep to a single number
        signal = np.mean(sweep)

        # Exponential filtering of the signal
        sf = min(self.sf_signal, 1.0 - 1.0 / (1.0 + self.sweep_index))
        self.signal_lp = sf * self.signal_lp + (1.0 - sf) * signal

        # The relative difference
        rel_dev = np.square((signal - self.signal_lp)/self.signal_lp)

        # Exponential filtering of the difference
        sf = min(self.sf_rel_dev, 1.0 - 1.0 / (1.0 + self.sweep_index))
        self.rel_dev_lp = sf * self.rel_dev_lp + (1.0 - sf) * rel_dev

        # Check detection
        detection = False
        sweeps_since_last_detect = (self.sweep_index - self.last_detection_sweep)
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

        while len(self.detection_history) > 0 and \
                (self.sweep_index - self.detection_history[0]) > HISTORY_LENGTH_S*self.f:
            self.detection_history.remove(self.detection_history[0])

        out_data = {
            "signal_history": self.signal_history,
            "signal_lp_history": self.signal_lp_history,
            "rel_dev_history": self.rel_dev_history,
            "rel_dev_lp_history": self.rel_dev_lp_history,
            "detection_history": (np.array(self.detection_history) - self.sweep_index)/self.f,
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

        self.setup_is_done = False

        self.sweep_index_of_latest_detection = 0
        self.sweeps_detection_show = DETECTION_SHOW_S * sensor_config.sweep_rate

    def setup(self, win):
        win.setWindowTitle("Acconeer Button Press Example")

        self.limit_lines = []
        dashed_pen = pg.mkPen("k", width=2.5, style=QtCore.Qt.DashLine)

        self.sign_hist_plot = win.addPlot(title="Signal history")
        self.sign_hist_plot.addLegend()
        self.sign_hist_plot.showGrid(x=True, y=True)
        self.sign_hist_plot.setLabel("bottom", "Time (s)")
        self.sign_hist_plot.setXRange(-HISTORY_LENGTH_S, 0)
        self.sign_hist_plot.setYRange(0, OUTPUT_MAX_SIGNAL)
        self.sign_hist_curve = self.sign_hist_plot.plot(
                pen=example_utils.pg_pen_cycler(0),
                name="Envelope signal",
                )
        self.sign_lp_hist_curve = self.sign_hist_plot.plot(
                pen=example_utils.pg_pen_cycler(1),
                name="Filtered envelope signal",
                )

        win.nextRow()

        self.rel_dev_hist_plot = win.addPlot(title="Relative deviation history")
        self.rel_dev_hist_plot.showGrid(x=True, y=True)
        self.rel_dev_hist_plot.setLabel("bottom", "Time (s)")
        self.rel_dev_hist_plot.setXRange(-HISTORY_LENGTH_S, 0)
        self.rel_dev_hist_plot.setYRange(0, OUTPUT_MAX_REL_DEV)
        self.rel_dev_lp_hist_curve = self.rel_dev_hist_plot.plot(
                pen=example_utils.pg_pen_cycler(0),
                name="Relative deviation",
                )

        self.detection_dots = self.rel_dev_hist_plot.plot(
                pen=None,
                symbol='o',
                symbolSize=20,
                symbolBrush=example_utils.color_cycler(1),
                name="Detections",
                )
        self.rel_dev_hist_plot.addItem(self.detection_dots)

        limit_line = pg.InfiniteLine(angle=0, pen=dashed_pen)
        self.rel_dev_hist_plot.addItem(limit_line)

        self.limit_lines.append(limit_line)

        self.detection_html_format = '<div style="text-align: center">' \
                                     '<span style="color: #FFFFFF;font-size:16pt;">' \
                                     '{}</span></div>'
        detection_html = self.detection_html_format.format("Button press detected!")

        self.detection_text_item = pg.TextItem(
                html=detection_html,
                fill=pg.mkColor(255, 140, 0),
                anchor=(0.5, 0),
                )

        self.detection_text_item.setPos(-HISTORY_LENGTH_S/2, 0.95 * OUTPUT_MAX_REL_DEV)
        self.rel_dev_hist_plot.addItem(self.detection_text_item)
        self.detection_text_item.hide()

        self.smooth_max_signal = example_utils.SmoothMax(
                self.sensor_config.sweep_rate,
                hysteresis=0.6,
                tau_decay=3,
                )

        self.smooth_max_rel_dev = example_utils.SmoothMax(
                self.sensor_config.sweep_rate,
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
        self.detection_dots.setData(t_detections, data["threshold"]*np.ones(len(t_detections)))

        m = np.amax(signal_hist_ys) if signal_hist_ys.size > 0 else 1
        self.sign_hist_plot.setYRange(0, self.smooth_max_signal.update(m))

        m = np.amax(rel_dev_lp_hist_ys) if rel_dev_lp_hist_ys.size > 0 else 1e-3
        m = max(2 * data["threshold"], m)
        ymax = self.smooth_max_rel_dev.update(m)
        self.rel_dev_hist_plot.setYRange(0, ymax)
        self.detection_text_item.setPos(-HISTORY_LENGTH_S / 2, 0.95 * ymax)

        if data["detection"]:
            self.detection_text_item.show()
            self.sweep_index_of_latest_detection = data["sweep_index"]

        sweeps_since_last_detection = data["sweep_index"] - self.sweep_index_of_latest_detection
        if sweeps_since_last_detection > self.sweeps_detection_show:
            self.detection_text_item.hide()


if __name__ == "__main__":
    main()
