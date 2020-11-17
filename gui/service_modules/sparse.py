import os
import sys

import numpy as np
import pyqtgraph as pg
from matplotlib.colors import LinearSegmentedColormap

from acconeer.exptool import configs, utils
from acconeer.exptool.clients import SocketClient, SPIClient, UARTClient
from acconeer.exptool.pg_process import PGProccessDiedException, PGProcess
from acconeer.exptool.structs import configbase


sys.path.append(os.path.join(os.path.dirname(__file__), "../.."))  # noqa: E402

from examples.processing import presence_detection_sparse  # isort:skip


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

    sensor_config = get_sensor_config()
    sensor_config.sensor = args.sensors

    processing_config = get_processing_config()

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
    sensor_config = configs.SparseServiceConfig()
    sensor_config.range_interval = [0.24, 1.20]
    sensor_config.update_rate = 60
    sensor_config.sampling_mode = configs.SparseServiceConfig.SamplingMode.A
    sensor_config.profile = configs.SparseServiceConfig.Profile.PROFILE_3
    sensor_config.hw_accelerated_average_samples = 60
    return sensor_config


class ProcessingConfiguration(configbase.ProcessingConfig):
    VERSION = 1

    history_length = configbase.IntParameter(
        label="History length",
        default_value=100,
    )


get_processing_config = ProcessingConfiguration


class Processor:
    def __init__(self, sensor_config, processing_config, session_info):
        num_sensors = len(sensor_config.sensor)
        num_depths = utils.get_range_depths(sensor_config, session_info).size
        history_len = processing_config.history_length

        pd_config = presence_detection_sparse.get_processing_config()
        processor_class = presence_detection_sparse.Processor

        try:
            self.pd_processors = []
            for _ in sensor_config.sensor:
                p = processor_class(sensor_config, pd_config, session_info)
                self.pd_processors.append(p)
        except AssertionError:
            self.pd_processors = None

        self.data_history = np.ones([history_len, num_sensors, num_depths]) * 2**15
        self.presence_history = np.zeros([history_len, num_sensors, num_depths])

    def process(self, data):
        if self.pd_processors:
            processed_datas = [p.process(s) for s, p in zip(data, self.pd_processors)]
            presences = [d["depthwise_presence"] for d in processed_datas]

            self.presence_history = np.roll(self.presence_history, -1, axis=0)
            self.presence_history[-1] = presences

        self.data_history = np.roll(self.data_history, -1, axis=0)
        self.data_history[-1] = data.mean(axis=1)

        out_data = {
            "data": data,
            "data_history": self.data_history,
            "presence_history": self.presence_history,
        }

        return out_data


class PGUpdater:
    def __init__(self, sensor_config, processing_config, session_info):
        self.sensor_config = sensor_config
        self.processing_config = processing_config

        self.depths = utils.get_range_depths(sensor_config, session_info)
        self.depth_res = session_info["step_length_m"]
        self.xs = np.tile(self.depths, sensor_config.sweeps_per_frame)
        self.smooth_limits = utils.SmoothLimits(sensor_config.update_rate)

    def setup(self, win):
        win.setWindowTitle("Acconeer sparse example")

        # For history images:
        rate = self.sensor_config.update_rate
        xlabel = "Frames" if rate is None else "Time (s)"
        x_scale = 1.0 if rate is None else 1.0 / rate
        y_scale = self.depth_res
        x_offset = -self.processing_config.history_length * x_scale
        y_offset = self.depths[0] - 0.5 * self.depth_res

        self.data_plots = []
        self.scatters = []
        self.data_history_ims = []
        self.presence_history_ims = []

        for i in range(len(self.sensor_config.sensor)):
            data_plot = win.addPlot(title="Sparse data", row=0, col=i)
            data_plot.setMenuEnabled(False)
            data_plot.setMouseEnabled(x=False, y=False)
            data_plot.hideButtons()
            data_plot.showGrid(x=True, y=True)
            data_plot.setLabel("bottom", "Depth (m)")
            data_plot.setLabel("left", "Amplitude")
            scatter = pg.ScatterPlotItem(size=10)
            data_plot.addItem(scatter)

            cmap_cols = ["steelblue", "lightblue", "#f0f0f0", "moccasin", "darkorange"]
            cmap = LinearSegmentedColormap.from_list("mycmap", cmap_cols)
            cmap._init()
            lut = (cmap._lut * 255).view(np.ndarray)

            data_history_plot = win.addPlot(title="Data history", row=1, col=i)
            data_history_plot.setMenuEnabled(False)
            data_history_plot.setMouseEnabled(x=False, y=False)
            data_history_plot.hideButtons()
            data_history_im = pg.ImageItem(autoDownsample=True)
            data_history_im.setLookupTable(lut)
            data_history_plot.addItem(data_history_im)
            data_history_plot.setLabel("bottom", xlabel)
            data_history_plot.setLabel("left", "Depth (m)")

            presence_history_plot = win.addPlot(title="Movement history", row=2, col=i)
            presence_history_plot.setMenuEnabled(False)
            presence_history_plot.setMouseEnabled(x=False, y=False)
            presence_history_plot.hideButtons()
            presence_history_im = pg.ImageItem(autoDownsample=True)
            presence_history_im.setLookupTable(utils.pg_mpl_cmap("viridis"))
            presence_history_plot.addItem(presence_history_im)
            presence_history_plot.setLabel("bottom", xlabel)
            presence_history_plot.setLabel("left", "Depth (m)")

            for im in [presence_history_im, data_history_im]:
                im.resetTransform()
                im.translate(x_offset, y_offset)
                im.scale(x_scale, y_scale)

            self.data_plots.append(data_plot)
            self.scatters.append(scatter)
            self.data_history_ims.append(data_history_im)
            self.presence_history_ims.append(presence_history_im)

    def update(self, d):
        data_limits = self.smooth_limits.update(d["data"])

        for i in range(len(self.sensor_config.sensor)):
            ys = d["data"][i].flatten()
            self.scatters[i].setData(self.xs, ys)
            self.data_plots[i].setYRange(*data_limits)

            data_history_adj = d["data_history"][:, i] - 2**15
            sign = np.sign(data_history_adj)
            data_history_adj = np.abs(data_history_adj)
            data_history_adj /= data_history_adj.max()
            data_history_adj = np.power(data_history_adj, 1 / 2.2)  # gamma correction
            data_history_adj *= sign
            self.data_history_ims[i].updateImage(data_history_adj, levels=(-1.05, 1.05))

            m = np.max(d["presence_history"][:, i]) * 1.1
            self.presence_history_ims[i].updateImage(d["presence_history"][:, i], levels=(0, m))


if __name__ == "__main__":
    main()
