import numpy as np
import pyqtgraph as pg
from PyQt5 import QtCore

from acconeer_utils.clients.reg.client import RegClient
from acconeer_utils.clients.json.client import JSONClient
from acconeer_utils.clients import configs
from acconeer_utils import example_utils
from acconeer_utils.pg_process import PGProcess, PGProccessDiedException


def main():
    args = example_utils.ExampleArgumentParser(num_sens=1).parse_args()
    example_utils.config_logging(args)

    if args.socket_addr:
        client = JSONClient(args.socket_addr)
    else:
        port = args.serial_port or example_utils.autodetect_serial_port()
        client = RegClient(port)

    config = get_base_config()
    config.sensor = args.sensors

    client.setup_session(config)

    pg_updater = PGUpdater(config)
    pg_process = PGProcess(pg_updater)
    pg_process.start()

    client.start_streaming()

    interrupt_handler = example_utils.ExampleInterruptHandler()
    print("Press Ctrl-C to end session")

    processor = PresenceDetectionProcessor(config)

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


def get_base_config():
    config = configs.IQServiceConfig()
    config.range_interval = [0.3, 0.9]
    config.sweep_rate = 40
    config.gain = 0.7
    return config


class PresenceDetectionProcessor:
    def __init__(self, config):
        self.config = config

        self.movement_history = np.zeros(5 * config.sweep_rate)  # 5 seconds

        self.a_fast_tau = 0.1
        self.a_slow_tau = 1
        self.a_move_tau = 1
        self.a_fast = self.alpha(self.a_fast_tau, 1.0/config.sweep_rate)
        self.a_slow = self.alpha(self.a_slow_tau, 1.0/config.sweep_rate)
        self.a_move = self.alpha(self.a_move_tau, 1.0/config.sweep_rate)

        self.sweep_lp_fast = None
        self.sweep_lp_slow = None
        self.movement_lp = 0

        self.sweep_index = 0

    def process(self, sweep):
        if self.sweep_index == 0:
            self.sweep_lp_fast = np.array(sweep)
            self.sweep_lp_slow = np.array(sweep)

            out_data = None
        else:
            self.sweep_lp_fast = self.sweep_lp_fast*self.a_fast + sweep*(1-self.a_fast)
            self.sweep_lp_slow = self.sweep_lp_slow*self.a_slow + sweep*(1-self.a_slow)

            movement = np.mean(np.abs(self.sweep_lp_fast - self.sweep_lp_slow))
            movement *= 100
            self.movement_lp = self.movement_lp*self.a_move + movement*(1-self.a_move)

            self.movement_history = np.roll(self.movement_history, -1)
            self.movement_history[-1] = self.movement_lp

            out_data = {
                "envelope": np.abs(self.sweep_lp_fast),
                "movement_history": np.tanh(self.movement_history),
            }

        self.sweep_index += 1
        return out_data

    def alpha(self, tau, dt):
        return np.exp(-dt/tau)


class PGUpdater:
    def __init__(self, config):
        self.config = config
        self.movement_limit = 0.3

    def setup(self, win):
        win.setWindowTitle("Acconeer presence detection example")

        self.env_plot = win.addPlot(title="IQ amplitude")
        self.env_plot.showGrid(x=True, y=True)
        self.env_plot.setLabel("bottom", "Depth (m)")
        self.env_curve = self.env_plot.plot(pen=example_utils.pg_pen_cycler(0))
        self.env_smooth_max = example_utils.SmoothMax(self.config.sweep_rate)

        win.nextRow()
        move_hist_plot = win.addPlot(title="Movement history")
        move_hist_plot.showGrid(x=True, y=True)
        move_hist_plot.setLabel("bottom", "Time(s)")
        move_hist_plot.setXRange(-5, 0)
        move_hist_plot.setYRange(0, 1)
        self.move_hist_curve = move_hist_plot.plot(pen=example_utils.pg_pen_cycler(0))
        limit_pen = pg.mkPen("k", width=2.5, style=QtCore.Qt.DashLine)
        limit_line = pg.InfiniteLine(self.movement_limit, angle=0, pen=limit_pen)
        move_hist_plot.addItem(limit_line)
        self.move_hist_text = pg.TextItem(color=pg.mkColor("k"), anchor=(0.5, 0))
        self.move_hist_text.setPos(-2.5, 0.95)
        move_hist_plot.addItem(self.move_hist_text)

    def update(self, data):
        env_ys = data["envelope"]
        env_xs = np.linspace(*self.config.range_interval, len(env_ys))
        self.env_curve.setData(env_xs, env_ys)
        self.env_plot.setYRange(0, self.env_smooth_max.update(np.amax(env_ys)))

        move_hist_ys = data["movement_history"]
        move_hist_xs = np.linspace(-5, 0, len(move_hist_ys))
        self.move_hist_curve.setData(move_hist_xs, move_hist_ys)

        if move_hist_ys[-1] > self.movement_limit:
            self.move_hist_text.setText("Present!")
        else:
            self.move_hist_text.setText("Not present")


if __name__ == "__main__":
    main()
