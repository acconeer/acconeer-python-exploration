import sys

from acconeer_utils.clients.reg.client import RegClient
from acconeer_utils.clients import configs
from acconeer_utils import example_utils
from acconeer_utils.mpl_process import PlotProcess, PlotProccessDiedException, FigureUpdater


def main():
    args = example_utils.ExampleArgumentParser().parse_args()
    example_utils.config_logging(args)

    if args.socket_addr:
        print("Using detectors is not supported over socket")
        sys.exit()
    else:
        port = args.serial_port or example_utils.autodetect_serial_port()
        client = RegClient(port)

    client.squeeze = False

    config = configs.DistancePeakDetectorConfig()
    config.sensor = args.sensors
    config.range_interval = [0.1, 0.8]
    config.sweep_rate = 60
    config.gain = 0.5

    client.setup_session(config)

    fig_updater = ExampleFigureUpdater(config)
    plot_process = PlotProcess(fig_updater)
    plot_process.start()

    client.start_streaming()

    interrupt_handler = example_utils.ExampleInterruptHandler()
    print("Press Ctrl-C to end session")

    while not interrupt_handler.got_signal:
        info, data = client.get_next()

        try:
            plot_process.put_data(data)
        except PlotProccessDiedException:
            break

    print("Disconnecting...")
    plot_process.close()
    client.disconnect()


class ExampleFigureUpdater(FigureUpdater):
    def __init__(self, config):
        self.config = config

    def setup(self, fig):
        self.ax = fig.add_subplot(1, 1, 1)
        self.ax.set_title("Amplitude")
        self.ax.set_xlabel("Depth (m)")
        self.ax.set_xlim(self.config.range_interval)
        self.ax.set_ylim(50, 20000)
        self.ax.grid(True)

        self.arts = [self.ax.semilogy([], '^', markersize=20)[0] for _ in self.config.sensor]

        fig.canvas.set_window_title("Acconeer distance peak example")
        fig.set_size_inches(8, 5)
        fig.tight_layout()

    def first(self, data):
        self.update(data)
        return self.arts

    def update(self, data):
        for art, ps in zip(self.arts, data):
            art.set_data(ps[:, 0], ps[:, 1])


if __name__ == "__main__":
    main()
