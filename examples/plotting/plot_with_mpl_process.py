import numpy as np

from acconeer_utils.clients.reg.client import RegClient
from acconeer_utils.clients.json.client import JSONClient
from acconeer_utils.clients import configs
from acconeer_utils import example_utils
from acconeer_utils.mpl_process import PlotProcess, PlotProccessDiedException, FigureUpdater


def main():
    args = example_utils.ExampleArgumentParser().parse_args()
    example_utils.config_logging(args)

    if args.socket_addr:
        client = JSONClient(args.socket_addr)
    else:
        port = args.serial_port or example_utils.autodetect_serial_port()
        client = RegClient(port)

    client.squeeze = False

    config = configs.IQServiceConfig()
    config.sensor = args.sensors
    config.range_interval = [0.2, 0.6]
    config.sweep_rate = 30
    config.gain = 0.6
    # config.running_average_factor = 0.5

    info = client.setup_session(config)
    num_points = info["data_length"]

    fig_updater = ExampleFigureUpdater(config, num_points)
    plot_process = PlotProcess(fig_updater)
    plot_process.start()

    client.start_streaming()

    interrupt_handler = example_utils.ExampleInterruptHandler()
    print("Press Ctrl-C to end session")

    while not interrupt_handler.got_signal:
        info, data = client.get_next()

        plot_data = {
            "amplitude": np.abs(data),
            "phase": np.angle(data),
        }

        try:
            plot_process.put_data(plot_data)
        except PlotProccessDiedException:
            break

    print("Disconnecting...")
    plot_process.close()
    client.disconnect()


class ExampleFigureUpdater(FigureUpdater):
    def __init__(self, config, num_points):
        self.interval = config.range_interval
        self.num_points = num_points

    def setup(self, fig):
        self.axs = {
            "amplitude": fig.add_subplot(2, 1, 1),
            "phase": fig.add_subplot(2, 1, 2),
        }

        for ax in self.axs.values():
            ax.grid(True)
            ax.set_xlabel("Depth (m)")
            ax.set_xlim(self.interval)

        self.axs["amplitude"].set_title("Amplitude")
        self.axs["amplitude"].set_ylim(0, 0.5)
        self.axs["phase"].set_title("Phase")
        example_utils.mpl_setup_yaxis_for_phase(self.axs["phase"])

        fig.canvas.set_window_title("Acconeer matplotlib process example")
        fig.set_size_inches(10, 7)
        fig.tight_layout()

    def first(self, d):
        xs = np.linspace(*self.interval, self.num_points)

        self.all_arts = {}
        for key, ax in self.axs.items():
            self.all_arts[key] = [ax.plot(xs, ys)[0] for ys in d[key]]
        return [art for arts in self.all_arts.values() for art in arts]

    def update(self, d):
        for key, arts in self.all_arts.items():
            for art, ys in zip(arts, d[key]):
                art.set_ydata(ys)


if __name__ == "__main__":
    main()
