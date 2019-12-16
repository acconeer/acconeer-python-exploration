import numpy as np

from acconeer.exptool import configs, utils
from acconeer.exptool.clients import SocketClient, SPIClient, UARTClient
from acconeer.exptool.pg_process import PGProccessDiedException, PGProcess


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

    sensor_config = configs.IQServiceConfig()
    sensor_config.sensor = args.sensors
    sensor_config.range_interval = [0.2, 1.0]
    sensor_config.profile = sensor_config.Profile.PROFILE_2
    sensor_config.sampling_mode = sensor_config.SamplingMode.B
    sensor_config.hw_accelerated_average_samples = 20
    sensor_config.downsampling_factor = 2

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
        win.setWindowTitle("Acconeer IQ example")

        self.ampl_plot = win.addPlot()
        self.ampl_plot.setMenuEnabled(False)
        self.ampl_plot.showGrid(x=True, y=True)
        self.ampl_plot.setLabel("bottom", "Depth (m)")
        self.ampl_plot.setLabel("left", "Amplitude")
        win.nextRow()
        self.phase_plot = win.addPlot()
        self.phase_plot.setMenuEnabled(False)
        self.phase_plot.showGrid(x=True, y=True)
        self.phase_plot.setLabel("bottom", "Depth (m)")
        self.phase_plot.setLabel("left", "Phase")
        self.phase_plot.setYRange(-np.pi, np.pi)
        self.phase_plot.getAxis("left").setTicks(utils.pg_phase_ticks)

        self.ampl_curves = []
        self.phase_curves = []
        for i, _ in enumerate(self.sensor_config.sensor):
            pen = utils.pg_pen_cycler(i)
            self.ampl_curves.append(self.ampl_plot.plot(pen=pen))
            self.phase_curves.append(self.phase_plot.plot(pen=pen))

        self.smooth_max = utils.SmoothMax(self.sensor_config.update_rate)

    def update(self, data):
        for ampl_curve, phase_curve, ys in zip(self.ampl_curves, self.phase_curves, data):
            ampl_curve.setData(self.depths, np.abs(ys))
            phase_curve.setData(self.depths, np.angle(ys))

        self.ampl_plot.setYRange(0, self.smooth_max.update(np.abs(data)))


if __name__ == "__main__":
    main()
