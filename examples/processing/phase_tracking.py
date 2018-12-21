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

    processor = PhaseTrackingProcessor(config)

    while not interrupt_handler.got_signal:
        info, sweep = client.get_next()
        plot_data = processor.process(sweep)

        if plot_data is not None:
            try:
                plot_process.put_data(plot_data)
            except PlotProccessDiedException:
                break

    print("Disconnecting...")
    plot_process.close()
    client.disconnect()


def get_base_config():
    config = configs.IQServiceConfig()
    config.range_interval = [0.3, 0.6]
    config.sweep_rate = 80
    config.gain = 0.7
    return config


class PhaseTrackingProcessor:
    def __init__(self, config):
        self.f = config.sweep_rate
        self.dt = 1 / self.f

        num_hist_points = self.f * 3

        self.lp_vel = 0
        self.last_sweep = None
        self.hist_vel = np.zeros(num_hist_points)
        self.hist_pos = np.zeros(num_hist_points)
        self.sweep_index = 0

    def process(self, sweep):
        n = len(sweep)

        ampl = np.abs(sweep)
        power = ampl*ampl
        if np.sum(power) > 1e-6:
            com = np.sum(np.arange(n)/n * power) / np.sum(power)  # center of mass
        else:
            com = 0

        if self.sweep_index == 0:
            self.lp_ampl = ampl
            self.lp_com = com
            plot_data = None
        else:
            a = self.alpha(0.1, self.dt)
            self.lp_ampl = a*ampl + (1 - a)*self.lp_ampl
            a = self.alpha(0.25, self.dt)
            self.lp_com = a*com + (1-a)*self.lp_com

            com_idx = int(self.lp_com * n)
            delta_angle = np.angle(sweep[com_idx] * np.conj(self.last_sweep[com_idx]))
            vel = self.f * 2.5 * delta_angle / (2*np.pi)

            a = self.alpha(0.1, self.dt)
            self.lp_vel = a*vel + (1 - a)*self.lp_vel

            self.hist_vel = np.roll(self.hist_vel, -1)
            self.hist_vel[-1] = self.lp_vel

            dp = self.lp_vel / self.f
            self.hist_pos = np.roll(self.hist_pos, -1)
            self.hist_pos[-1] = self.hist_pos[-2] + dp

            hist_len = len(self.hist_pos)
            plot_hist_pos = self.hist_pos - self.hist_pos.mean()
            plot_hist_pos_zoom = self.hist_pos[hist_len//2:] - self.hist_pos[hist_len//2:].mean()

            iq_val = np.exp(1j*np.angle(sweep[com_idx])) * self.lp_ampl[com_idx]

            plot_data = {
                "abs": self.lp_ampl,
                "arg": np.angle(sweep),
                "com": self.lp_com,
                "hist_pos": plot_hist_pos,
                "hist_pos_zoom": plot_hist_pos_zoom,
                "iq_val": iq_val,
            }

        self.last_sweep = sweep
        self.sweep_index += 1
        return plot_data

    def alpha(self, tau, dt):
        return 1 - np.exp(-dt/tau)


class ExampleFigureUpdater(FigureUpdater):
    def __init__(self, config):
        self.interval = config.range_interval

    def setup(self, fig):
        gs = GridSpec(2, 3)
        self.axs = {
            "abs": fig.add_subplot(gs[0, 0]),
            "arg": fig.add_subplot(gs[1, 0]),
            "iq": fig.add_subplot(gs[1, 1]),
            "hist_pos": fig.add_subplot(gs[0, 1:]),
            "hist_pos_zoom": fig.add_subplot(gs[1, 2]),
        }

        max_ampl = 0.5
        self.axs["abs"].set_ylim(0, max_ampl)
        self.axs["hist_pos"].set_ylim(-5, 5)
        self.axs["hist_pos_zoom"].set_ylim(-0.5, 0.5)
        self.axs["iq"].set_xlim(-max_ampl, max_ampl)
        self.axs["iq"].set_ylim(-max_ampl, max_ampl)
        example_utils.mpl_setup_yaxis_for_phase(self.axs["arg"])
        self.axs["abs"].set_ylabel("Amplitude")
        self.axs["arg"].set_ylabel("Phase")
        self.axs["iq"].set_xlabel("Real part at line")
        self.axs["iq"].set_ylabel("Imaginary part at line")

        for k in ["hist_pos", "hist_pos_zoom"]:
            ax = self.axs[k]
            ax.set_xlabel("Time (s)")
            ax.set_ylabel("Tracking (mm)")

        for k in ["abs", "arg"]:
            ax = self.axs[k]
            ax.set_xlim(*self.interval)
            ax.set_xlabel("Depth (m)")

        for ax in self.axs.values():
            ax.grid(True)

        fig.canvas.set_window_title("Acconeer phase tracking example")
        fig.set_size_inches(10, 7)
        fig.tight_layout()

    def first(self, data):
        n = len(data["abs"])
        xs = np.linspace(*self.interval, n)
        ts = np.linspace(-3, 0, len(data["hist_pos"]))
        ts_zoom = np.linspace(-1.5, 0, len(data["hist_pos_zoom"]))

        self.arts = {
            "abs": self.axs["abs"].plot(xs, data["abs"])[0],
            "arg": self.axs["arg"].plot(xs, data["arg"])[0],
            "abs_vline": self.axs["abs"].axvline(-1, color="C1", ls="--"),
            "arg_vline": self.axs["arg"].axvline(-1, color="C1", ls="--"),
            "hist_pos": self.axs["hist_pos"].plot(ts, data["hist_pos"])[0],
            "hist_pos_zoom": self.axs["hist_pos_zoom"].plot(ts_zoom, data["hist_pos_zoom"])[0],
            "iq": self.axs["iq"].plot(0, "-o", markevery=2)[0],
        }

        return self.arts.values()

    def update(self, data):
        com_x = (1-data["com"])*self.interval[0] + data["com"]*self.interval[1]

        iq_vals = [[np.real(data["iq_val"]), 0], [np.imag(data["iq_val"]), 0]]

        self.arts["abs"].set_ydata(data["abs"])
        self.arts["arg"].set_ydata(data["arg"])
        self.arts["abs_vline"].set_xdata(com_x)
        self.arts["arg_vline"].set_xdata(com_x)
        self.arts["hist_pos"].set_ydata(data["hist_pos"])
        self.arts["hist_pos_zoom"].set_ydata(data["hist_pos_zoom"])
        self.arts["iq"].set_data(iq_vals)


if __name__ == "__main__":
    main()
