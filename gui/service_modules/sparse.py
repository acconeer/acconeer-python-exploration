import numpy as np
import pyqtgraph as pg
from matplotlib.colors import LinearSegmentedColormap
import sys
import os

from acconeer_utils.clients.reg.client import RegClient, RegSPIClient
from acconeer_utils.clients.json.client import JSONClient
from acconeer_utils.clients import configs
from acconeer_utils import example_utils
from acconeer_utils.pg_process import PGProcess, PGProccessDiedException

sys.path.append(os.path.join(os.path.dirname(__file__), "../.."))  # noqa: E402
from examples.processing import presence_detection_sparse


def main():
    args = example_utils.ExampleArgumentParser().parse_args()
    example_utils.config_logging(args)

    if args.socket_addr:
        client = JSONClient(args.socket_addr)
    elif args.spi:
        client = RegSPIClient()
    else:
        port = args.serial_port or example_utils.autodetect_serial_port()
        client = RegClient(port)

    sensor_config = get_sensor_config()
    sensor_config.sensor = args.sensors

    processing_config = get_processing_config()

    client.setup_session(sensor_config)

    pg_updater = PGUpdater(sensor_config, processing_config)
    pg_process = PGProcess(pg_updater)
    pg_process.start()

    client.start_streaming()

    interrupt_handler = example_utils.ExampleInterruptHandler()
    print("Press Ctrl-C to end session")

    processor = Processor(sensor_config, processing_config)

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
    def __init__(self, sensor_config, processing_config):
        self.history_len = processing_config["image_buffer"]["value"]

        pd_config = presence_detection_sparse.get_processing_config()
        self.pd_processor = presence_detection_sparse.PresenceDetectionSparseProcessor(
            sensor_config,
            pd_config
        )

        self.smooth_max = example_utils.SmoothMax(sensor_config.sweep_rate)

        self.sweep_index = 0

    def process(self, sweep):
        pd_data = self.pd_processor.process(sweep)
        movement = pd_data["movement"]

        if self.sweep_index == 0:
            num_subsweeps, num_depths = sweep.shape

            self.data_history = np.zeros([self.history_len, num_depths])
            self.movement_history = np.zeros([self.history_len, num_depths])

        self.data_history = np.roll(self.data_history, 1, axis=0)
        self.data_history[0] = sweep.mean(axis=0)

        self.movement_history = np.roll(self.movement_history, 1, axis=0)
        self.movement_history[0] = movement

        smooth_max = self.smooth_max.update(np.max(np.abs(sweep)))

        out_data = {
            "data": sweep,
            "data_smooth_max": smooth_max,
            "data_history": self.data_history,
            "movement_history": self.movement_history,
        }

        self.sweep_index += 1

        return out_data


class PGUpdater:
    def __init__(self, sensor_config, processing_config):
        self.sensor_config = sensor_config

        self.sweep_index = 0

    def setup(self, win):
        win.setWindowTitle("Acconeer sparse example")

        self.data_plot = win.addPlot(title="Sparse data")
        self.data_plot.showGrid(x=True, y=True)
        self.data_plot.setLabel("bottom", "Depth (m)")
        self.data_plot.setLabel("left", "Amplitude")
        self.data_plot.setYRange(-2**15, 2**15)
        self.scatter = pg.ScatterPlotItem(size=10)
        self.data_plot.addItem(self.scatter)

        win.nextRow()

        cmap_cols = ["steelblue", "lightblue", "#f0f0f0", "moccasin", "darkorange"]
        cmap = LinearSegmentedColormap.from_list("mycmap", cmap_cols)
        cmap._init()
        lut = (cmap._lut * 255).view(np.ndarray)

        self.data_history_plot = win.addPlot(title="Data history")
        self.data_history_im = pg.ImageItem(autoDownsample=True)
        self.data_history_im.setLookupTable(lut)
        self.data_history_plot.addItem(self.data_history_im)
        self.data_history_plot.setLabel("bottom", "Time (s)")
        self.data_history_plot.setLabel("left", "Depth (m)")

        win.nextRow()

        self.movement_history_plot = win.addPlot(title="Movement history")
        self.movement_history_im = pg.ImageItem(autoDownsample=True)
        self.movement_history_im.setLookupTable(example_utils.pg_mpl_cmap("viridis"))
        self.movement_history_plot.addItem(self.movement_history_im)
        self.movement_history_plot.setLabel("bottom", "Time (s)")
        self.movement_history_plot.setLabel("left", "Depth (m)")

    def update(self, d):
        if self.sweep_index == 0:
            num_subsweeps, num_depths = d["data"].shape
            depths = np.linspace(*self.sensor_config.range_interval, num_depths)
            self.xs = np.tile(depths, num_subsweeps)

            time_res = 1.0 / self.sensor_config.sweep_rate
            depth_res = self.sensor_config.range_length / (num_depths - 1)

            for im in [self.data_history_im, self.movement_history_im]:
                im.resetTransform()
                im.translate(0, self.sensor_config.range_start - depth_res / 2)
                im.scale(time_res, depth_res)

        ys = d["data"].flatten()
        self.scatter.setData(self.xs, ys)
        m = max(500, d["data_smooth_max"])
        self.data_plot.setYRange(-m, m)

        data_history_adj = d["data_history"]
        sign = np.sign(data_history_adj)
        data_history_adj = np.abs(data_history_adj)
        data_history_adj /= data_history_adj.max()
        data_history_adj = np.power(data_history_adj, 1/2.2)  # gamma correction
        data_history_adj *= sign
        self.data_history_im.updateImage(data_history_adj, levels=(-1.05, 1.05))

        m = np.max(d["movement_history"]) * 1.1
        self.movement_history_im.updateImage(d["movement_history"], levels=(0, m))

        self.sweep_index += 1


if __name__ == "__main__":
    main()
