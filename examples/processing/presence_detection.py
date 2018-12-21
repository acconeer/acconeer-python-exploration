import numpy as np
from matplotlib.gridspec import GridSpec

from acconeer_utils.clients.reg.client import RegClient
from acconeer_utils.clients.json.client import JSONClient
from acconeer_utils.clients import configs
from acconeer_utils import example_utils
from acconeer_utils.mpl_process import PlotProcess, PlotProccessDiedException, FigureUpdater


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

    fig_updater = ExampleFigureUpdater(config)
    plot_process = PlotProcess(fig_updater)
    plot_process.start()

    client.start_streaming()

    interrupt_handler = example_utils.ExampleInterruptHandler()
    print("Press Ctrl-C to end session")

    processor = PresenceDetectionProcessor(config)

    while not interrupt_handler.got_signal:
        info, sweep = client.get_next()
        plot_data = processor.process(sweep)

        try:
            plot_process.put_data(plot_data)  # Will ignore the first None from processor
        except PlotProccessDiedException:
            break

    print("Disconnecting...")
    plot_process.close()
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


class ExampleFigureUpdater(FigureUpdater):
    def __init__(self, config):
        self.config = config

        self.movement_limit = 0.3

    def setup(self, fig):
        gs = GridSpec(1, 2)

        self.axs = {
            "envelope": fig.add_subplot(gs[0, 0]),
            "movement_history": fig.add_subplot(gs[0, 1]),
        }

        self.axs["envelope"].set_title("Envelope")
        self.axs["envelope"].set_xlabel("Depth (m)")
        self.axs["envelope"].set_xlim(self.config.range_interval)
        self.axs["envelope"].set_ylim(0, 0.5)

        self.axs["movement_history"].set_title("Movement history")
        self.axs["movement_history"].set_xlabel("Time (s)")
        self.axs["movement_history"].set_xlim(-5, 0)
        self.axs["movement_history"].set_ylim(0, 1)

        for ax in self.axs.values():
            ax.grid(True)

        fig.canvas.set_window_title("Acconeer presence detection example")
        fig.set_size_inches(10, 5)
        fig.tight_layout()

    def first(self, data):
        xs = {
            "envelope": np.linspace(*self.config.range_interval, data["envelope"].size),
            "movement_history": np.linspace(-5, 0, data["movement_history"].size),
        }
        self.arts = {k: self.axs[k].plot(xs[k], data[k])[0] for k in xs.keys()}

        mh_ax = self.axs["movement_history"]
        self.arts["movement_limit"] = mh_ax.axhline(self.movement_limit, color="k", ls="--")
        self.arts["movement_text"] = mh_ax.text(-2.5, 0.95, "", size=30, ha="center", va="top")

        return self.arts.values()

    def update(self, data):
        for k, v in data.items():
            self.arts[k].set_ydata(v)

        if data["movement_history"][-1] > self.movement_limit:
            self.arts["movement_text"].set_text("Present!")
        else:
            self.arts["movement_text"].set_text("Not present")


if __name__ == "__main__":
    main()
