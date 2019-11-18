import numpy as np
import pyqtgraph as pg
from matplotlib.colors import LinearSegmentedColormap
import sys
import os

from acconeer.exptool.clients import SocketClient, SPIClient, UARTClient
from acconeer.exptool.clients import configs
from acconeer.exptool import example_utils
from acconeer.exptool.pg_process import PGProcess, PGProccessDiedException

sys.path.append(os.path.join(os.path.dirname(__file__), "../.."))  # noqa: E402
from examples.processing import presence_detection_sparse


def main():
    args = example_utils.ExampleArgumentParser().parse_args()
    example_utils.config_logging(args)

    if args.socket_addr:
        client = SocketClient(args.socket_addr)
    elif args.spi:
        client = SPIClient()
    else:
        port = args.serial_port or example_utils.autodetect_serial_port()
        client = UARTClient(port)

    client.squeeze = False

    sensor_config = get_sensor_config()
    sensor_config.sensor = args.sensors

    processing_config = get_processing_config()

    session_info = client.setup_session(sensor_config)

    pg_updater = PGUpdater(sensor_config, processing_config, session_info)
    pg_process = PGProcess(pg_updater)
    pg_process.start()

    client.start_streaming()

    interrupt_handler = example_utils.ExampleInterruptHandler()
    print("Press Ctrl-C to end session")

    processor = Processor(sensor_config, processing_config, session_info)

    while not interrupt_handler.got_signal:
        info, sweep = client.get_next()
        plot_data = processor.process(sweep)

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
    sensor_config.sweep_rate = 60
    sensor_config.number_of_subsweeps = 16
    return sensor_config


def get_processing_config():
    return {
        "image_buffer": {
            "name": "Image history",
            "value": 100,
            "limits": [10, 10000],
            "type": int,
            "text": None,
        },
    }


class Processor:
    def __init__(self, sensor_config, processing_config, session_info):
        num_sensors = len(sensor_config.sensor)
        num_depths = len(get_range_depths(sensor_config, session_info))
        history_len = processing_config["image_buffer"]["value"]

        pd_config = presence_detection_sparse.get_processing_config()
        processor_class = presence_detection_sparse.PresenceDetectionSparseProcessor

        try:
            self.pd_processors = [processor_class(sensor_config, pd_config, session_info)]
        except AssertionError:
            self.pd_processors = None

        self.smooth_max = example_utils.SmoothMax(sensor_config.sweep_rate)

        self.data_history = np.zeros([history_len, num_sensors, num_depths])
        self.presence_history = np.zeros([history_len, num_sensors, num_depths])

        self.sweep_index = 0

    def process(self, data):
        if self.pd_processors:
            processed_datas = [p.process(s) for s, p in zip(data, self.pd_processors)]
            presences = [d["depthwise_presence"] for d in processed_datas]

            self.presence_history = np.roll(self.presence_history, -1, axis=0)
            self.presence_history[-1] = presences

        self.data_history = np.roll(self.data_history, -1, axis=0)
        self.data_history[-1] = data.mean(axis=1)

        smooth_max = self.smooth_max.update(np.max(np.abs(data)))

        out_data = {
            "data": data,
            "data_smooth_max": smooth_max,
            "data_history": self.data_history,
            "presence_history": self.presence_history,
        }

        self.sweep_index += 1

        return out_data


class PGUpdater:
    def __init__(self, sensor_config, processing_config, session_info):
        self.sensor_config = sensor_config

        self.depths = get_range_depths(sensor_config, session_info)
        self.num_depths = self.depths.size
        self.num_subsweeps = sensor_config.number_of_subsweeps
        self.xs = np.tile(self.depths, self.num_subsweeps)
        self.time_res = 1.0 / self.sensor_config.sweep_rate
        self.depth_res = session_info["actual_stepsize"]

        history_len = processing_config["image_buffer"]["value"]
        self.history_len_s = history_len * self.time_res

    def setup(self, win):
        win.setWindowTitle("Acconeer sparse example")

        self.data_plots = []
        self.scatters = []
        self.data_history_ims = []
        self.presence_history_ims = []

        for i in range(len(self.sensor_config.sensor)):
            data_plot = win.addPlot(title="Sparse data", row=0, col=i)
            data_plot.showGrid(x=True, y=True)
            data_plot.setLabel("bottom", "Depth (m)")
            data_plot.setLabel("left", "Amplitude")
            data_plot.setYRange(-2**15, 2**15)
            scatter = pg.ScatterPlotItem(size=10)
            data_plot.addItem(scatter)

            cmap_cols = ["steelblue", "lightblue", "#f0f0f0", "moccasin", "darkorange"]
            cmap = LinearSegmentedColormap.from_list("mycmap", cmap_cols)
            cmap._init()
            lut = (cmap._lut * 255).view(np.ndarray)

            data_history_plot = win.addPlot(title="Data history", row=1, col=i)
            data_history_im = pg.ImageItem(autoDownsample=True)
            data_history_im.setLookupTable(lut)
            data_history_plot.addItem(data_history_im)
            data_history_plot.setLabel("bottom", "Time (s)")
            data_history_plot.setLabel("left", "Depth (m)")

            presence_history_plot = win.addPlot(title="Movement history", row=2, col=i)
            presence_history_im = pg.ImageItem(autoDownsample=True)
            presence_history_im.setLookupTable(example_utils.pg_mpl_cmap("viridis"))
            presence_history_plot.addItem(presence_history_im)
            presence_history_plot.setLabel("bottom", "Time (s)")
            presence_history_plot.setLabel("left", "Depth (m)")

            self.data_plots.append(data_plot)
            self.scatters.append(scatter)
            self.data_history_ims.append(data_history_im)
            self.presence_history_ims.append(presence_history_im)

            for im in [presence_history_im, data_history_im]:
                im.resetTransform()
                im.translate(-self.history_len_s, self.depths[0] - self.depth_res / 2)
                im.scale(self.time_res, self.depth_res)

    def update(self, d):
        for i in range(len(self.sensor_config.sensor)):
            ys = d["data"][i].flatten()
            self.scatters[i].setData(self.xs, ys)
            m = max(500, d["data_smooth_max"])
            self.data_plots[i].setYRange(-m, m)

            data_history_adj = d["data_history"][:, i]
            sign = np.sign(data_history_adj)
            data_history_adj = np.abs(data_history_adj)
            data_history_adj /= data_history_adj.max()
            data_history_adj = np.power(data_history_adj, 1/2.2)  # gamma correction
            data_history_adj *= sign
            self.data_history_ims[i].updateImage(data_history_adj, levels=(-1.05, 1.05))

            m = np.max(d["presence_history"][:, i]) * 1.1
            self.presence_history_ims[i].updateImage(d["presence_history"][:, i], levels=(0, m))


def get_range_depths(sensor_config, session_info):
    range_start = session_info["actual_range_start"]
    range_end = range_start + session_info["actual_range_length"]
    num_depths = session_info["data_length"] // sensor_config.number_of_subsweeps
    return np.linspace(range_start, range_end, num_depths)


if __name__ == "__main__":
    main()
