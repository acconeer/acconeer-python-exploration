import numpy as np
import pyqtgraph as pg
from PyQt5 import QtCore

from acconeer_utils.clients.reg.client import RegClient, RegSPIClient
from acconeer_utils.clients.json.client import JSONClient
from acconeer_utils.clients import configs
from acconeer_utils import example_utils
from acconeer_utils.pg_process import PGProcess, PGProccessDiedException


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
    config.range_interval = [0.5, 1.5]
    config.sweep_rate = 60
    config.gain = 0.65
    config.number_of_subsweeps = 16
    return config


def get_processing_config():
    return {
        "threshold": {
            "name": "Threshold",
            "value": 0.3,
            "limits": [0, 1],
            "type": float,
            "text": None,
        },
        "upper_speed_limit": {
            "name": "Max movement [mm/s]",
            "value": 30,
            "limits": [1, 500],
            "type": float,
            "text": None,
        },
    }


class PresenceDetectionSparseProcessor:
    def __init__(self, sensor_config, processing_config):
        self.threshold = processing_config["threshold"]["value"]
        num_subsweeps = sensor_config.number_of_subsweeps
        upper_speed_limit = processing_config["upper_speed_limit"]["value"]
        f = int(round(sensor_config.sweep_rate))

        self.movement_history = np.zeros(f * 5)  # 5 seconds

        self.a_fast_tau = 1.0 / (upper_speed_limit / 2.5)
        self.a_slow_tau = 0.8
        self.a_diff_tau = 0.4
        self.a_move_tau = 0.8
        self.static_a_fast = self.alpha(self.a_fast_tau, 1.0 / (f * num_subsweeps))
        self.static_a_slow = self.alpha(self.a_slow_tau, 1.0 / (f * num_subsweeps))
        self.a_diff = self.alpha(self.a_diff_tau, 1.0 / (f * num_subsweeps))
        self.a_move = self.alpha(self.a_move_tau, 1.0 / (f * num_subsweeps))

        self.sweep_lp_fast = None
        self.sweep_lp_slow = None
        self.lp_diff = None
        self.subsweep_index = 0
        self.movement_lp = 0

    def dynamic_filter_coefficient(self, static_alpha):
        dynamic_alpha = 1.0 - 1.0 / (1 + self.subsweep_index)
        return min(static_alpha, dynamic_alpha)

    def process(self, sweep):
        for subsweep in sweep:
            if self.subsweep_index == 0:
                self.sweep_lp_fast = subsweep.copy()
                self.sweep_lp_slow = subsweep.copy()
                self.lp_diff = np.zeros_like(subsweep)
            else:
                a_fast = self.dynamic_filter_coefficient(self.static_a_fast)
                self.sweep_lp_fast = self.sweep_lp_fast * a_fast + subsweep * (1-a_fast)

                a_slow = self.dynamic_filter_coefficient(self.static_a_slow)
                self.sweep_lp_slow = self.sweep_lp_slow * a_slow + subsweep * (1-a_slow)

                diff = np.abs(self.sweep_lp_fast - self.sweep_lp_slow)
                self.lp_diff = self.lp_diff * self.a_diff + diff * (1-self.a_diff)

                depth_filtered_lp_diff = np.correlate(self.lp_diff, np.ones(3) / 3)

                movement = np.max(depth_filtered_lp_diff)
                movement *= 0.0025
                self.movement_lp = self.movement_lp*self.a_move + movement*(1-self.a_move)

            self.subsweep_index += 1

        self.movement_history = np.roll(self.movement_history, -1)
        self.movement_history[-1] = self.movement_lp

        present = np.tanh(self.movement_history[-1]) > self.threshold

        out_data = {
            "movement": depth_filtered_lp_diff,
            "movement_index": np.argmax(depth_filtered_lp_diff),
            "movement_history": np.tanh(self.movement_history),
            "present": present,
        }

        return out_data

    def alpha(self, tau, dt):
        return np.exp(-dt/tau)


class PGUpdater:
    def __init__(self, sensor_config, processing_config):
        self.config = sensor_config
        self.movement_limit = processing_config["threshold"]["value"]

    def setup(self, win):
        win.setWindowTitle("Acconeer presence detection example")

        dashed_pen = pg.mkPen("k", width=2.5, style=QtCore.Qt.DashLine)

        self.move_plot = win.addPlot(title="Movement")
        self.move_plot.showGrid(x=True, y=True)
        self.move_plot.setLabel("bottom", "Depth (m)")
        self.move_curve = self.move_plot.plot(pen=example_utils.pg_pen_cycler())
        self.move_smooth_max = example_utils.SmoothMax(self.config.sweep_rate)

        self.move_depth_line = pg.InfiniteLine(pen=dashed_pen)
        self.move_depth_line.hide()
        self.move_plot.addItem(self.move_depth_line)

        win.nextRow()

        move_hist_plot = win.addPlot(title="Movement history")
        move_hist_plot.showGrid(x=True, y=True)
        move_hist_plot.setLabel("bottom", "Time (s)")
        move_hist_plot.setXRange(-5, 0)
        move_hist_plot.setYRange(0, 1)
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
        self.present_text_item.setPos(-2.5, 0.95)
        self.not_present_text_item.setPos(-2.5, 0.95)
        move_hist_plot.addItem(self.present_text_item)
        move_hist_plot.addItem(self.not_present_text_item)
        self.present_text_item.hide()

    def update(self, data):
        move_ys = data["movement"]
        move_xs = np.linspace(*self.config.range_interval, len(move_ys))
        self.move_curve.setData(move_xs, move_ys)
        self.move_plot.setYRange(0, self.move_smooth_max.update(np.max(move_ys)))

        movement_x = move_xs[data["movement_index"]]
        self.move_depth_line.setPos(movement_x)

        move_hist_ys = data["movement_history"]
        move_hist_xs = np.linspace(-5, 0, len(move_hist_ys))
        self.move_hist_curve.setData(move_hist_xs, move_hist_ys)

        if data["present"]:
            present_text = "Presence detected at {:.1f}m!".format(movement_x)
            present_html = self.present_html_format.format(present_text)
            self.present_text_item.setHtml(present_html)

            self.present_text_item.show()
            self.not_present_text_item.hide()
            self.move_depth_line.show()
        else:
            self.present_text_item.hide()
            self.not_present_text_item.show()
            self.move_depth_line.hide()


if __name__ == "__main__":
    main()
