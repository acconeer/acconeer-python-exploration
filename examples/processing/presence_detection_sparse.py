import numpy as np
from scipy.special import binom
import pyqtgraph as pg
from PyQt5 import QtCore

from acconeer_utils.clients.reg.client import RegClient, RegSPIClient
from acconeer_utils.clients.json.client import JSONClient
from acconeer_utils.clients import configs
from acconeer_utils import example_utils
from acconeer_utils.pg_process import PGProcess, PGProccessDiedException


OUTPUT_MAX = 10
HISTORY_LENGTH_S = 5


def main():
    args = example_utils.ExampleArgumentParser(num_sens=1).parse_args()
    example_utils.config_logging(args)

    if args.socket_addr:
        client = JSONClient(args.socket_addr)
    elif args.spi:
        client = RegSPIClient()
    else:
        port = args.serial_port or example_utils.autodetect_serial_port()
        client = RegClient(port)

    sensor_config = get_sensor_config()
    processing_config = get_processing_config()
    sensor_config.sensor = args.sensors

    client.setup_session(sensor_config)

    pg_updater = PGUpdater(sensor_config, processing_config)
    pg_process = PGProcess(pg_updater)
    pg_process.start()

    client.start_streaming()

    interrupt_handler = example_utils.ExampleInterruptHandler()
    print("Press Ctrl-C to end session")

    processor = PresenceDetectionSparseProcessor(sensor_config, processing_config)

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


def get_processing_config():
    return {
        "threshold": {
            "name": "Threshold",
            "value": 2,
            "limits": [0, OUTPUT_MAX],
            "type": float,
            "text": None,
        },
        "fast_cut": {
            "name": "Fast cutoff freq. [Hz]",
            "value": 50.0,
            "limits": [1, 500],
            "type": float,
            "text": None,
        },
        "slow_cut": {
            "name": "Slow cutoff freq. [Hz]",
            "value": 1.0,
            "limits": [0.1, 5.0],
            "type": float,
            "text": None,
        },
        "show_sweep": {
            "name": "Show sweep",
            "value": True,
        },
        "show_noise": {
            "name": "Show noise",
            "value": False,
        },
        "show_depthwise_output": {
            "name": "Show depthwise presence",
            "value": True,
        },
    }


class PresenceDetectionSparseProcessor:
    def __init__(self, sensor_config, processing_config):
        self.num_subsweeps = sensor_config.number_of_subsweeps
        self.threshold = processing_config["threshold"]["value"]
        f = sensor_config.sweep_rate
        dt = 1.0 / f

        self.noise_est_diff_order = 3
        self.depth_filter_length = 3

        nd = self.noise_est_diff_order
        self.noise_norm_factor = np.sqrt(np.sum(np.square(binom(nd, np.arange(nd + 1)))))

        # lp(f): low pass (filtered)
        # cut: cutoff frequency [Hz]
        # tc: time constant [s]
        # sf: smoothing factor [dimensionless]

        fast_cut = processing_config["fast_cut"]["value"]
        slow_cut = processing_config["slow_cut"]["value"]
        bandpass_tc = 0.5
        output_tc = 1.0
        noise_tc = 1.0

        self.fast_sf = self.static_sf(1.0 / fast_cut, dt)
        self.slow_sf = self.static_sf(1.0 / slow_cut, dt)
        self.bandpass_sf = self.static_sf(bandpass_tc, dt)
        self.output_sf = self.static_sf(output_tc, dt)
        self.noise_sf = self.static_sf(noise_tc, dt)

        self.fast_lp_mean_subsweep = None
        self.slow_lp_mean_subsweep = None
        self.lp_bandpass = None
        self.lp_output = 0
        self.lp_noise = None

        self.output_history = np.zeros(int(round(f * HISTORY_LENGTH_S)))
        self.sweep_index = 0

    def static_sf(self, tc, dt):
        return np.exp(-dt / tc)

    def dynamic_sf(self, static_sf):
        return min(static_sf, 1.0 - 1.0 / (1.0 + self.sweep_index))

    def process(self, sweep):
        mean_subsweep = sweep.mean(axis=0)

        if self.sweep_index == 0:
            self.fast_lp_mean_subsweep = np.zeros_like(mean_subsweep)
            self.slow_lp_mean_subsweep = np.zeros_like(mean_subsweep)
            self.lp_bandpass = np.zeros_like(mean_subsweep)
            self.lp_noise = np.zeros_like(mean_subsweep)

        sf = self.dynamic_sf(self.fast_sf)
        self.fast_lp_mean_subsweep = sf * self.fast_lp_mean_subsweep + (1.0 - sf) * mean_subsweep

        sf = self.dynamic_sf(self.slow_sf)
        self.slow_lp_mean_subsweep = sf * self.slow_lp_mean_subsweep + (1.0 - sf) * mean_subsweep

        bandpass = np.abs(self.fast_lp_mean_subsweep - self.slow_lp_mean_subsweep)
        sf = self.dynamic_sf(self.bandpass_sf)
        self.lp_bandpass = sf * self.lp_bandpass + (1.0 - sf) * bandpass

        nd = self.noise_est_diff_order
        noise = np.diff(sweep, n=nd, axis=0).std(axis=0) / self.noise_norm_factor
        sf = self.dynamic_sf(self.noise_sf)
        self.lp_noise = sf * self.lp_noise + (1.0 - sf) * noise

        norm_lp_bandpass = self.lp_bandpass / self.lp_noise
        norm_lp_bandpass *= np.sqrt(self.num_subsweeps)

        depth_filter = np.ones(self.depth_filter_length) / self.depth_filter_length
        depth_filt_norm_lp_bandpass = np.correlate(norm_lp_bandpass, depth_filter, mode="same")

        output = np.max(depth_filt_norm_lp_bandpass)
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
            "movement": depth_filt_norm_lp_bandpass,
            "movement_index": np.argmax(depth_filt_norm_lp_bandpass),
            "movement_history": self.output_history,
            "present": present,
        }

        self.sweep_index += 1

        return out_data


class PGUpdater:
    def __init__(self, sensor_config, processing_config):
        self.sensor_config = sensor_config
        self.processing_config = processing_config
        self.movement_limit = processing_config["threshold"]["value"]

    def setup(self, win):
        win.setWindowTitle("Acconeer presence detection example")

        dashed_pen = pg.mkPen("k", width=2.5, style=QtCore.Qt.DashLine)

        if self.processing_config["show_sweep"]["value"]:
            data_plot = win.addPlot(title="Sweep (blue), fast (orange), and slow (green)")
            data_plot.showGrid(x=True, y=True)
            data_plot.setLabel("bottom", "Depth (m)")
            data_plot.setYRange(-2**15, 2**15)
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
            data_plot.addItem(self.sweep_scatter)
            data_plot.addItem(self.fast_scatter)
            data_plot.addItem(self.slow_scatter)

            win.nextRow()

        if self.processing_config["show_noise"]["value"]:
            self.noise_plot = win.addPlot(title="Noise")
            self.noise_plot.showGrid(x=True, y=True)
            self.noise_plot.setLabel("bottom", "Depth (m)")
            self.noise_curve = self.noise_plot.plot(pen=example_utils.pg_pen_cycler())
            self.noise_smooth_max = example_utils.SmoothMax(self.sensor_config.sweep_rate)

            win.nextRow()

        if self.processing_config["show_depthwise_output"]["value"]:
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
            limit_line = pg.InfiniteLine(self.movement_limit, angle=0, pen=dashed_pen)
            self.move_plot.addItem(limit_line)

            win.nextRow()

        move_hist_plot = win.addPlot(title="Presence history")
        move_hist_plot.showGrid(x=True, y=True)
        move_hist_plot.setLabel("bottom", "Time (s)")
        move_hist_plot.setXRange(-HISTORY_LENGTH_S, 0)
        move_hist_plot.setYRange(0, OUTPUT_MAX)
        self.move_hist_curve = move_hist_plot.plot(pen=example_utils.pg_pen_cycler())
        limit_line = pg.InfiniteLine(self.movement_limit, angle=0, pen=dashed_pen)
        move_hist_plot.addItem(limit_line)

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
        move_hist_plot.addItem(self.present_text_item)
        move_hist_plot.addItem(self.not_present_text_item)
        self.present_text_item.hide()

    def update(self, data):
        sweep = data["sweep"]
        _, num_depths = sweep.shape
        depths = np.linspace(*self.sensor_config.range_interval, num_depths)

        if self.processing_config["show_sweep"]["value"]:
            self.sweep_scatter.setData(
                    np.tile(depths, self.sensor_config.number_of_subsweeps),
                    sweep.flatten(),
                    )
            self.fast_scatter.setData(depths, data["fast"])
            self.slow_scatter.setData(depths, data["slow"])

        if self.processing_config["show_noise"]["value"]:
            noise = data["noise"]
            self.noise_curve.setData(depths, noise)
            self.noise_plot.setYRange(0, self.noise_smooth_max.update(np.max(noise)))

        movement_x = depths[data["movement_index"]]

        if self.processing_config["show_depthwise_output"]["value"]:
            move_ys = data["movement"]
            self.move_curve.setData(depths, move_ys)
            self.move_plot.setYRange(0, self.move_smooth_max.update(np.max(move_ys)))
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
