import pyqtgraph as pg

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

    sensor_config = configs.PowerBinServiceConfig()
    sensor_config.sensor = args.sensors
    sensor_config.range_interval = [0.1, 0.7]

    session_info = client.setup_session(sensor_config)

    pg_updater = PGUpdater(sensor_config, None, session_info)
    pg_process = PGProcess(pg_updater)
    pg_process.start()

    client.start_session()

    interrupt_handler = utils.ExampleInterruptHandler()
    print("Press Ctrl-C to end session")

    while not interrupt_handler.got_signal:
        data_info, data = client.get_next()

        try:
            pg_process.put_data(data)
        except PGProccessDiedException:
            break

    print("Disconnecting...")
    pg_process.close()
    client.disconnect()


class PGUpdater:
    def __init__(self, sensor_config, processing_config, session_info):
        self.sensor_config = sensor_config
        self.depths = utils.get_range_depths(sensor_config, session_info)

    def setup(self, win):
        win.setWindowTitle("Acconeer power bins example")

        self.plot = win.addPlot()
        self.plot.showGrid(x=True, y=True)
        self.plot.setLabel("bottom", "Depth (m)")
        self.plot.setLabel("left", "Amplitude")

        self.curves = []
        for i, _ in enumerate(self.sensor_config.sensor):
            curve = self.plot.plot(
                pen=utils.pg_pen_cycler(i),
                symbol="o",
                symbolPen="k",
                symbolBrush=pg.mkBrush(utils.color_cycler(i)),
            )
            self.curves.append(curve)

        self.smooth_max = utils.SmoothMax(self.sensor_config.update_rate)

    def update(self, data):
        for curve, ys in zip(self.curves, data):
            curve.setData(self.depths, ys)

        self.plot.setYRange(0, self.smooth_max.update(data))


if __name__ == "__main__":
    main()
