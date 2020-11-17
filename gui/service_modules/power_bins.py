import numpy as np
import pyqtgraph as pg

from acconeer.exptool import configs, utils
from acconeer.exptool.clients import SocketClient, SPIClient, UARTClient
from acconeer.exptool.pg_process import PGProccessDiedException, PGProcess


def main():
    args = utils.ExampleArgumentParser(num_sens=1).parse_args()
    utils.config_logging(args)

    if args.socket_addr:
        client = SocketClient(args.socket_addr)
    elif args.spi:
        client = SPIClient()
    else:
        port = args.serial_port or utils.autodetect_serial_port()
        client = UARTClient(port)

    sensor_config = get_sensor_config()
    sensor_config.sensor = args.sensors

    session_info = client.setup_session(sensor_config)

    pg_updater = PGUpdater(sensor_config, None, session_info)
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


def get_sensor_config():
    return configs.PowerBinServiceConfig()


class PGUpdater:
    def __init__(self, sensor_config, processing_config, session_info):
        self.session_info = session_info
        self.smooth_max = utils.SmoothMax(sensor_config.update_rate)

    def setup(self, win):
        num_depths = self.session_info["bin_count"]
        start = self.session_info["range_start_m"]
        length = self.session_info["range_length_m"]
        end = start + length

        xs = np.linspace(start, end, num_depths * 2 + 1)[1::2]
        bin_width = 0.8 * length / num_depths

        self.plot = win.addPlot()
        self.plot.setMenuEnabled(False)
        self.plot.setMouseEnabled(x=False, y=False)
        self.plot.hideButtons()
        self.plot.showGrid(x=True, y=True)
        self.plot.setLabel("bottom", "Depth (m)")
        self.plot.setLabel("left", "Amplitude")
        self.plot.setXRange(start, end)
        self.plot.setYRange(0, 1)

        self.bar_graph = pg.BarGraphItem(
            x=xs,
            height=np.zeros_like(xs),
            width=bin_width,
            brush=pg.mkBrush(utils.color_cycler()),
        )

        self.plot.addItem(self.bar_graph)

    def update(self, data):
        self.bar_graph.setOpts(height=data)
        self.plot.setYRange(0, self.smooth_max.update(data))


if __name__ == "__main__":
    main()
