import numpy as np
from numpy import cos, pi, sqrt, square
from scipy.special import binom
import pyqtgraph as pg
from PyQt5 import QtCore

from acconeer_utils.clients import SocketClient, SPIClient, UARTClient
from acconeer_utils.clients import configs
from acconeer_utils import example_utils
from acconeer_utils.pg_process import PGProcess, PGProccessDiedException
from acconeer_utils.structs import configbase


OUTPUT_MAX = 10
HISTORY_LENGTH_S = 5


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

    processor = PresenceDetectionSparseProcessor(sensor_config, processing_config, session_info)

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
    config = configs.SparseServiceConfig()
    config.range_interval = [0.3, 1.3]
    config.sweep_rate = 80
    config.gain = 0.6
    config.number_of_subsweeps = 32
    return config


class ProcessingConfiguration(configbase.ProcessingConfig):
    VERSION = 2

    threshold = configbase.FloatParameter(
            label="Detection threshold",
            default_value=2,
            limits=(0, OUTPUT_MAX),
            updateable=True,
            order=0,
            help="Level at which the detector output is considered as \"present\".",
            )

    fast_cutoff = configbase.FloatParameter(
            label="Fast cutoff freq.",
            unit="Hz",
            default_value=20.0,
            limits=(1, 100),
            logscale=True,
            updateable=True,
            order=10,
            help=(
                "Cutoff frequency of the low pass filter for the fast filtered subsweep mean."
                " No filtering is applied if the cutoff is set over half the sweep frequency"
                " (Nyquist limit)."
            ),
            )

    slow_cutoff = configbase.FloatParameter(
            label="Slow cutoff freq.",
            unit="Hz",
            default_value=0.2,
            limits=(0.01, 1),
            logscale=True,
            updateable=True,
            order=20,
            help="Cutoff frequency of the low pass filter for the slow filtered subsweep mean.",
            )

    deviation_tc = configbase.FloatParameter(
            label="Deviation time const.",
            unit="s",
            default_value=0.5,
            limits=(0, 3),
            updateable=True,
            order=30,
            help="Time constant of the low pass filter for the deviation between fast and slow."
            )

    output_tc = configbase.FloatParameter(
            label="Output time const.",
            unit="s",
            default_value=0.5,
            limits=(0, 3),
            updateable=True,
            order=40,
            help="Time constant of the low pass filter for the detector output."
            )

    show_sweep = configbase.BoolParameter(
            label="Show sweep",
            default_value=True,
            updateable=True,
            order=100,
            help=(
                "Show the plot of the sweep data and the fast and slow filtered version of the"
                " subsweep mean."
            ),
            )

    show_noise = configbase.BoolParameter(
            label="Show noise",
            default_value=False,
            updateable=True,
            order=110,
            help="Show the noise estimation plot.",
            pidget_location="advanced",
            )

    show_depthwise_output = configbase.BoolParameter(
            label="Show depthwise presence",
            default_value=True,
            updateable=True,
            order=120,
            help="Show the depthwise presence output plot.",
            )


get_processing_config = ProcessingConfiguration


class PresenceDetectionSparseProcessor:
    # lp(f): low pass (filtered)
    # cut: cutoff frequency [Hz]
    # tc: time constant [s]
    # sf: smoothing factor [dimensionless]

    def __init__(self, sensor_config, processing_config, session_info):
        self.num_subsweeps = sensor_config.number_of_subsweeps
        self.f = sensor_config.sweep_rate

        # Fixed parameters
        self.noise_est_diff_order = 3
        self.depth_filter_length = 3
        noise_tc = 1.0

        self.noise_sf = self.tc_to_sf(noise_tc, self.f)

        nd = self.noise_est_diff_order
        self.noise_norm_factor = np.sqrt(np.sum(np.square(binom(nd, np.arange(nd + 1)))))

        self.fast_lp_mean_subsweep = None
        self.slow_lp_mean_subsweep = None
        self.lp_dev = None
        self.lp_output = 0
        self.lp_noise = None

        self.output_history = np.zeros(int(round(self.f * HISTORY_LENGTH_S)))
        self.sweep_index = 0

        self.update_processing_config(processing_config)

    def update_processing_config(self, processing_config):
        self.threshold = processing_config.threshold

        fast_cutoff = processing_config.fast_cutoff
        slow_cutoff = processing_config.slow_cutoff
        dev_tc = processing_config.deviation_tc
        output_tc = processing_config.output_tc

        self.fast_sf = self.cutoff_to_sf(fast_cutoff, self.f)
        self.slow_sf = self.cutoff_to_sf(slow_cutoff, self.f)
        self.dev_sf = self.tc_to_sf(dev_tc, self.f)
        self.output_sf = self.tc_to_sf(output_tc, self.f)

    def cutoff_to_sf(self, fc, fs):  # cutoff frequency to smoothing factor conversion
        if fc > 0.5 * fs:
            return 0.0

        cos_w = cos(2.0 * pi * (fc / fs))
        return 2.0 - cos_w - sqrt(square(cos_w) - 4.0 * cos_w + 3.0)

    def tc_to_sf(self, tc, fs):  # time constant to smoothing factor conversion
        if tc <= 0.0:
            return 0.0

        return np.exp(-1.0 / (tc * fs))

    def dynamic_sf(self, static_sf):
        return min(static_sf, 1.0 - 1.0 / (1.0 + self.sweep_index))

    def abs_dev(self, a, axis=None, ddof=0, subtract_mean=True):
        if subtract_mean:
            a = a - a.mean(axis=axis, keepdims=True)

        if axis is None:
            n = a.size
        else:
            n = a.shape[axis]

        assert ddof >= 0
        assert n > ddof

        return np.mean(np.abs(a), axis=axis) * sqrt(n / (n - ddof))

    def depth_filter(self, a):
        b = np.ones(self.depth_filter_length) / self.depth_filter_length

        if a.size >= b.size:
            return np.correlate(a, b, mode="same")
        else:
            pad_width = int(np.ceil((b.size - a.size) / 2))
            a = np.pad(a, pad_width)
            return np.correlate(a, b, mode="same")[pad_width: -pad_width]

    def process(self, sweep):
        mean_subsweep = sweep.mean(axis=0)

        if self.sweep_index == 0:
            self.fast_lp_mean_subsweep = np.zeros_like(mean_subsweep)
            self.slow_lp_mean_subsweep = np.zeros_like(mean_subsweep)
            self.lp_dev = np.zeros_like(mean_subsweep)
            self.lp_noise = np.zeros_like(mean_subsweep)

        sf = self.dynamic_sf(self.fast_sf)
        self.fast_lp_mean_subsweep = sf * self.fast_lp_mean_subsweep + (1.0 - sf) * mean_subsweep

        sf = self.dynamic_sf(self.slow_sf)
        self.slow_lp_mean_subsweep = sf * self.slow_lp_mean_subsweep + (1.0 - sf) * mean_subsweep

        dev = np.abs(self.fast_lp_mean_subsweep - self.slow_lp_mean_subsweep)
        sf = self.dynamic_sf(self.dev_sf)
        self.lp_dev = sf * self.lp_dev + (1.0 - sf) * dev

        nd = self.noise_est_diff_order
        noise = self.abs_dev(np.diff(sweep, n=nd, axis=0), axis=0, subtract_mean=False)
        noise /= self.noise_norm_factor
        sf = self.dynamic_sf(self.noise_sf)
        self.lp_noise = sf * self.lp_noise + (1.0 - sf) * noise

        norm_lp_dev = np.divide(
                self.lp_dev,
                self.lp_noise,
                out=np.zeros_like(self.lp_dev),
                where=(self.lp_noise > 1.0),
                )

        norm_lp_dev *= np.sqrt(self.num_subsweeps)

        depth_filt_norm_lp_dev = self.depth_filter(norm_lp_dev)

        output = np.max(depth_filt_norm_lp_dev)
        sf = self.output_sf  # no dynamic filter for the output
        self.lp_output = sf * self.lp_output + (1.0 - sf) * output

        present = self.lp_output > self.threshold

        self.output_history = np.roll(self.output_history, -1)
        self.output_history[-1] = self.lp_output

        out_data = {
            "sweep": sweep,
            "fast": self.fast_lp_mean_subsweep,
            "slow": self.slow_lp_mean_subsweep,
            "noise": self.lp_noise,
            "movement": depth_filt_norm_lp_dev,
            "movement_index": np.argmax(depth_filt_norm_lp_dev),
            "movement_history": self.output_history,
            "present": present,
        }

        self.sweep_index += 1

        return out_data


class PGUpdater:
    def __init__(self, sensor_config, processing_config, session_info):
        self.sensor_config = sensor_config
        self.processing_config = processing_config

        self.setup_is_done = False

    def setup(self, win):
        win.setWindowTitle("Acconeer presence detection example")

        self.limit_lines = []
        dashed_pen = pg.mkPen("k", width=2.5, style=QtCore.Qt.DashLine)

        self.data_plot = win.addPlot(title="Sweep (blue), fast (orange), and slow (green)")
        self.data_plot.showGrid(x=True, y=True)
        self.data_plot.setLabel("bottom", "Depth (m)")
        self.data_plot.setYRange(-2**15, 2**15)
        self.sweep_scatter = pg.ScatterPlotItem(
                size=10,
                brush=example_utils.pg_brush_cycler(0),
                )
        self.fast_scatter = pg.ScatterPlotItem(
                size=10,
                brush=example_utils.pg_brush_cycler(1),
                )
        self.slow_scatter = pg.ScatterPlotItem(
                size=10,
                brush=example_utils.pg_brush_cycler(2),
                )
        self.data_plot.addItem(self.sweep_scatter)
        self.data_plot.addItem(self.fast_scatter)
        self.data_plot.addItem(self.slow_scatter)

        win.nextRow()

        self.noise_plot = win.addPlot(title="Noise")
        self.noise_plot.showGrid(x=True, y=True)
        self.noise_plot.setLabel("bottom", "Depth (m)")
        self.noise_curve = self.noise_plot.plot(pen=example_utils.pg_pen_cycler())
        self.noise_smooth_max = example_utils.SmoothMax(self.sensor_config.sweep_rate)

        win.nextRow()

        self.move_plot = win.addPlot(title="Depthwise presence")
        self.move_plot.showGrid(x=True, y=True)
        self.move_plot.setLabel("bottom", "Depth (m)")
        self.move_curve = self.move_plot.plot(pen=example_utils.pg_pen_cycler())
        self.move_smooth_max = example_utils.SmoothMax(
                self.sensor_config.sweep_rate,
                tau_decay=1.0,
                )

        self.move_depth_line = pg.InfiniteLine(pen=dashed_pen)
        self.move_depth_line.hide()
        self.move_plot.addItem(self.move_depth_line)
        limit_line = pg.InfiniteLine(angle=0, pen=dashed_pen)
        self.move_plot.addItem(limit_line)
        self.limit_lines.append(limit_line)

        win.nextRow()

        self.move_hist_plot = win.addPlot(title="Presence history")
        self.move_hist_plot.showGrid(x=True, y=True)
        self.move_hist_plot.setLabel("bottom", "Time (s)")
        self.move_hist_plot.setXRange(-HISTORY_LENGTH_S, 0)
        self.move_hist_plot.setYRange(0, OUTPUT_MAX)
        self.move_hist_curve = self.move_hist_plot.plot(pen=example_utils.pg_pen_cycler())
        limit_line = pg.InfiniteLine(angle=0, pen=dashed_pen)
        self.move_hist_plot.addItem(limit_line)
        self.limit_lines.append(limit_line)

        self.present_html_format = '<div style="text-align: center">' \
                                   '<span style="color: #FFFFFF;font-size:16pt;">' \
                                   '{}</span></div>'
        present_html = self.present_html_format.format("Presence detected!")
        not_present_html = '<div style="text-align: center">' \
                           '<span style="color: #FFFFFF;font-size:16pt;">' \
                           '{}</span></div>'.format("No presence detected")
        self.present_text_item = pg.TextItem(
            html=present_html,
            fill=pg.mkColor(255, 140, 0),
            anchor=(0.5, 0),
            )
        self.not_present_text_item = pg.TextItem(
            html=not_present_html,
            fill=pg.mkColor("b"),
            anchor=(0.5, 0),
            )
        self.present_text_item.setPos(-2.5, 0.95 * OUTPUT_MAX)
        self.not_present_text_item.setPos(-2.5, 0.95 * OUTPUT_MAX)
        self.move_hist_plot.addItem(self.present_text_item)
        self.move_hist_plot.addItem(self.not_present_text_item)
        self.present_text_item.hide()

        self.setup_is_done = True
        self.update_processing_config()

    def update_processing_config(self, processing_config=None):
        if processing_config is None:
            processing_config = self.processing_config
        else:
            self.processing_config = processing_config

        if not self.setup_is_done:
            return

        self.data_plot.setVisible(self.processing_config.show_sweep)
        self.noise_plot.setVisible(self.processing_config.show_noise)
        self.move_plot.setVisible(self.processing_config.show_depthwise_output)

        for line in self.limit_lines:
            line.setPos(processing_config.threshold)

    def update(self, data):
        sweep = data["sweep"]
        _, num_depths = sweep.shape
        depths = np.linspace(*self.sensor_config.range_interval, num_depths)

        self.sweep_scatter.setData(
                np.tile(depths, self.sensor_config.number_of_subsweeps),
                sweep.flatten(),
                )
        self.fast_scatter.setData(depths, data["fast"])
        self.slow_scatter.setData(depths, data["slow"])

        noise = data["noise"]
        self.noise_curve.setData(depths, noise)
        self.noise_plot.setYRange(0, self.noise_smooth_max.update(np.max(noise)))

        movement_x = depths[data["movement_index"]]

        move_ys = data["movement"]
        self.move_curve.setData(depths, move_ys)
        m = self.move_smooth_max.update(np.max(move_ys))
        m = max(m, 2 * self.processing_config.threshold)
        self.move_plot.setYRange(0, m)
        self.move_depth_line.setPos(movement_x)
        self.move_depth_line.setVisible(data["present"])

        move_hist_ys = data["movement_history"]
        move_hist_xs = np.linspace(-HISTORY_LENGTH_S, 0, len(move_hist_ys))
        self.move_hist_curve.setData(move_hist_xs, np.minimum(move_hist_ys, OUTPUT_MAX))

        if data["present"]:
            present_text = "Presence detected at {:.1f}m!".format(movement_x)
            present_html = self.present_html_format.format(present_text)
            self.present_text_item.setHtml(present_html)

            self.present_text_item.show()
            self.not_present_text_item.hide()
        else:
            self.present_text_item.hide()
            self.not_present_text_item.show()


if __name__ == "__main__":
    main()
