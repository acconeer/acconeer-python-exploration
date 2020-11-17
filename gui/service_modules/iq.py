import numpy as np
import pyqtgraph as pg

from acconeer.exptool import clients, configs, utils
from acconeer.exptool.pg_process import PGProccessDiedException, PGProcess
from acconeer.exptool.structs import configbase


def main():
    args = utils.ExampleArgumentParser().parse_args()
    utils.config_logging(args)

    if args.socket_addr:
        client = clients.SocketClient(args.socket_addr)
    elif args.spi:
        client = clients.SPIClient()
    else:
        port = args.serial_port or utils.autodetect_serial_port()
        client = clients.UARTClient(port)

    client.squeeze = False

    sensor_config = get_sensor_config()
    processing_config = get_processing_config()
    sensor_config.sensor = args.sensors

    session_info = client.setup_session(sensor_config)

    pg_updater = PGUpdater(sensor_config, processing_config, session_info)
    pg_process = PGProcess(pg_updater)
    pg_process.start()

    client.start_session()

    interrupt_handler = utils.ExampleInterruptHandler()
    print("Press Ctrl-C to end session")

    processor = Processor(sensor_config, processing_config, session_info)

    while not interrupt_handler.got_signal:
        info, data = client.get_next()
        plot_data = processor.process(data)

        if plot_data is not None:
            try:
                pg_process.put_data(plot_data)
            except PGProccessDiedException:
                break

    print("Disconnecting...")
    pg_process.close()
    client.disconnect()


def get_sensor_config():
    config = configs.IQServiceConfig()
    config.range_interval = [0.2, 0.8]
    config.update_rate = 30
    return config


class ProcessingConfig(configbase.ProcessingConfig):
    VERSION = 2

    history_length = configbase.IntParameter(
        default_value=100,
        limits=(10, 1000),
        label="History length",
        order=0,
    )

    sf = configbase.FloatParameter(
        label="Smoothing factor",
        default_value=None,
        limits=(0.1, 0.999),
        decimals=3,
        optional=True,
        optional_label="Enable filter",
        optional_default_set_value=0.9,
        updateable=True,
        order=10,
    )


get_processing_config = ProcessingConfig


class Processor:
    def __init__(self, sensor_config, processing_config, session_info):
        depths = utils.get_range_depths(sensor_config, session_info)
        num_depths = depths.size
        num_sensors = len(sensor_config.sensor)
        history_length = processing_config.history_length
        self.history = np.zeros([history_length, num_sensors, num_depths], dtype="complex")
        self.lp_data = np.zeros([num_sensors, num_depths], dtype="complex")
        self.update_index = 0
        self.update_processing_config(processing_config)

    def update_processing_config(self, processing_config):
        self.sf = processing_config.sf if processing_config.sf is not None else 0.0

    def dynamic_sf(self, static_sf):
        return min(static_sf, 1.0 - 1.0 / (1.0 + self.update_index))

    def process(self, data):
        self.history = np.roll(self.history, -1, axis=0)
        self.history[-1] = data

        sf = self.dynamic_sf(self.sf)
        self.lp_data = sf * self.lp_data + (1 - sf) * data

        self.update_index += 1

        return {
            "data": self.lp_data,
            "history": self.history,
        }


class PGUpdater:
    def __init__(self, sensor_config, processing_config, session_info):
        self.sensor_config = sensor_config
        self.processing_config = processing_config

        self.depths = utils.get_range_depths(sensor_config, session_info)
        self.depth_res = session_info["step_length_m"]
        self.smooth_max = utils.SmoothMax(sensor_config.update_rate)

    def setup(self, win):
        num_sensors = len(self.sensor_config.sensor)

        self.ampl_plot = win.addPlot(row=0, col=0, colspan=num_sensors)
        self.ampl_plot.setMenuEnabled(False)
        self.ampl_plot.setMouseEnabled(x=False, y=False)
        self.ampl_plot.hideButtons()
        self.ampl_plot.showGrid(x=True, y=True)
        self.ampl_plot.setLabel("bottom", "Depth (m)")
        self.ampl_plot.setLabel("left", "Amplitude")
        self.ampl_plot.setXRange(*self.depths.take((0, -1)))
        self.ampl_plot.addLegend(offset=(-10, 10))

        self.phase_plot = win.addPlot(row=1, col=0, colspan=num_sensors)
        self.phase_plot.setMenuEnabled(False)
        self.phase_plot.setMouseEnabled(x=False, y=False)
        self.phase_plot.hideButtons()
        self.phase_plot.showGrid(x=True, y=True)
        self.phase_plot.setLabel("bottom", "Depth (m)")
        self.phase_plot.setLabel("left", "Phase")
        self.phase_plot.setXRange(*self.depths.take((0, -1)))
        self.phase_plot.setYRange(-np.pi, np.pi)
        self.phase_plot.getAxis("left").setTicks(utils.pg_phase_ticks)

        self.ampl_curves = []
        self.phase_curves = []
        for i, sensor_id in enumerate(self.sensor_config.sensor):
            legend = "Sensor {}".format(sensor_id)
            pen = utils.pg_pen_cycler(i)
            ampl_curve = self.ampl_plot.plot(pen=pen, name=legend)
            phase_curve = self.phase_plot.plot(pen=pen)
            self.ampl_curves.append(ampl_curve)
            self.phase_curves.append(phase_curve)

        rate = self.sensor_config.update_rate
        xlabel = "Sweeps" if rate is None else "Time (s)"
        x_scale = 1.0 if rate is None else 1.0 / rate
        y_scale = self.depth_res
        x_offset = -self.processing_config.history_length * x_scale
        y_offset = self.depths[0] - 0.5 * self.depth_res
        is_single_sensor = len(self.sensor_config.sensor) == 1

        self.history_plots = []
        self.history_ims = []
        for i, sensor_id in enumerate(self.sensor_config.sensor):
            title = None if is_single_sensor else "Sensor {}".format(sensor_id)
            plot = win.addPlot(row=2, col=i, title=title)
            plot.setMenuEnabled(False)
            plot.setMouseEnabled(x=False, y=False)
            plot.hideButtons()
            plot.setLabel("bottom", xlabel)
            plot.setLabel("left", "Depth (m)")
            im = pg.ImageItem(autoDownsample=True)
            im.setLookupTable(utils.pg_mpl_cmap("viridis"))
            im.resetTransform()
            im.translate(x_offset, y_offset)
            im.scale(x_scale, y_scale)
            plot.addItem(im)
            self.history_plots.append(plot)
            self.history_ims.append(im)

    def update(self, d):
        sweeps = d["data"]
        histories = np.abs(d["history"])

        ampls = np.abs(sweeps)

        for i, _ in enumerate(self.sensor_config.sensor):
            self.ampl_curves[i].setData(self.depths, ampls[i])
            self.phase_curves[i].setData(self.depths, np.angle(sweeps[i]))

            im = self.history_ims[i]
            history = histories[:, i]
            im.updateImage(history, levels=(0, 1.05 * history.max()))

        m = self.smooth_max.update(ampls)
        self.ampl_plot.setYRange(0, m)


if __name__ == "__main__":
    main()
