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

    config = configs.PowerBinServiceConfig()
    config.sensor = args.sensors
    config.range_interval = [0.1, 0.7]
    config.sweep_rate = 60
    config.gain = 0.6
    # config.bin_count = 8

    info = client.setup_session(config)
    num_points = info["actual_bin_count"]

    fig_updater = ExampleFigureUpdater(config, num_points)
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
    def __init__(self, config, num_points):
        self.interval = config.range_interval
        self.num_points = num_points

    def setup(self, fig):
        self.ax = fig.add_subplot(1, 1, 1)
        self.ax.set_title("Amplitude")
        self.ax.set_xlabel("Depth (m)")
        self.ax.set_ylim(0, 500)
        self.ax.grid(True)

        fig.canvas.set_window_title("Acconeer power bin data example")
        fig.set_size_inches(10, 7)
        fig.tight_layout()

    def first(self, data):
        xs = np.linspace(*self.interval, self.num_points)
        self.arts = [self.ax.plot(xs, ys, '-o')[0] for ys in data]
        return self.arts

    def update(self, data):
        for art, ys in zip(self.arts, data):
            art.set_ydata(ys)


if __name__ == "__main__":
    main()
