import numpy as np

from acconeer.exptool.clients import SocketClient, SPIClient, UARTClient
from acconeer.exptool import configs
from acconeer.exptool import utils
from acconeer.exptool.pg_process import PGProcess, PGProccessDiedException


def main():
    args = utils.ExampleArgumentParser().parse_args()
    utils.config_logging(args)

    if args.socket_addr:
        client = SocketClient(args.socket_addr)
    elif args.spi:
        client = SPIClient()
    else:
        port = args.serial_port or utils.autodetect_serial_port()
        client = UARTClient(port)

    client.squeeze = False

    config = configs.EnvelopeServiceConfig()
    config.sensor = args.sensors
    config.range_interval = [0.2, 0.6]
    config.sweep_rate = 60
    config.gain = 0.6
    # config.experimental_stitching = True
    # config.session_profile = configs.EnvelopeServiceConfig.MAX_SNR
    # config.running_average_factor = 0.5
    # config.compensate_phase = False  # not recommended

    info = client.setup_session(config)
    num_points = info["data_length"]

    pg_updater = PGUpdater(config, num_points)
    pg_process = PGProcess(pg_updater)
    pg_process.start()

    client.start_session()

    interrupt_handler = utils.ExampleInterruptHandler()
    print("Press Ctrl-C to end session")

    while not interrupt_handler.got_signal:
        info, data = client.get_next()

        try:
            pg_process.put_data(data)
        except PGProccessDiedException:
            break

    print("Disconnecting...")
    pg_process.close()
    client.disconnect()


class PGUpdater:
    def __init__(self, config, num_points):
        self.config = config
        self.num_points = num_points

    def setup(self, win):
        win.setWindowTitle("Acconeer envelope example")

        self.plot = win.addPlot(title="Envelope")
        self.plot.showGrid(x=True, y=True)
        self.plot.setLabel("bottom", "Depth (m)")
        self.plot.setLabel("left", "Amplitude")

        self.curves = []
        for i in range(len(self.config.sensor)):
            pen = utils.pg_pen_cycler(i)
            curve = self.plot.plot(pen=pen)
            self.curves.append(curve)

        self.xs = np.linspace(*self.config.range_interval, self.num_points)
        self.smooth_max = utils.SmoothMax(self.config.sweep_rate)

    def update(self, data):
        for curve, ys in zip(self.curves, data):
            curve.setData(self.xs, ys)

        self.plot.setYRange(0, self.smooth_max.update(np.amax(data)))


if __name__ == "__main__":
    main()
