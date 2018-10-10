import numpy as np
from pyqtgraph.Qt import QtGui
import pyqtgraph as pg

from acconeer_utils.streaming_client import StreamingClient
from acconeer_utils.config_builder import ConfigBuilder
from acconeer_utils.example_argparse import ExampleArgumentParser


class IQPyQtGraphExample:
    def run(self):
        parser = ExampleArgumentParser()
        args = parser.parse_args()

        range_start = 0.2
        range_end = 0.8
        self.plot_x_min = int(100 * range_start + 0.5)
        self.plot_x_max = int(100 * range_end + 0.5)
        self.sweep_index = 0
        self.amplitude_y_max = 1000

        self.app = QtGui.QApplication([])
        self.win = pg.GraphicsLayoutWidget()
        self.win.closeEvent = lambda _: exit()
        self.win.setWindowTitle("Acconeer IQ data example")
        self.ampl_plot = self.win.addPlot()
        self.win.nextRow()
        self.phase_plot = self.win.addPlot()

        self.ampl_plot.showGrid(x=True, y=True)
        self.ampl_plot.setLabel("bottom", "Depth (cm)")
        self.ampl_plot.setLabel("left", "Amplitude")
        self.ampl_curve = self.ampl_plot.plot()

        self.phase_plot.showGrid(x=True, y=True)
        self.phase_plot.setLabel("bottom", "Depth (cm)")
        self.phase_plot.setLabel("left", "Phase")
        self.phase_plot.setYRange(-np.pi, np.pi)
        self.phase_curve = self.phase_plot.plot()

        pg.setConfigOptions(antialias=True)
        self.win.show()

        self.config_builder = ConfigBuilder()
        self.config_builder.service = ConfigBuilder.SERVICE_IQ
        self.config_builder.range_start = 0.20
        self.config_builder.range_length = 0.30
        self.config_builder.sweep_count = 2**16
        self.config_builder.sweep_frequency = 80

        streaming_client = StreamingClient(args.host)
        streaming_client.run_session(self.config_builder.config, self.on_data)

    def on_data(self, metadata, payload):
        data = payload[0]

        if self.sweep_index == 0:
            self.smooth_data = data
        else:
            alpha = 0.8
            self.smooth_data = alpha*self.smooth_data + (1-alpha)*data

        xs = np.linspace(self.plot_x_min, self.plot_x_max, len(data))
        ampl = np.abs(self.smooth_data)
        phase = np.angle(self.smooth_data)

        self.ampl_curve.setData(xs, ampl)
        self.phase_curve.setData(xs, phase)

        self.amplitude_y_max = max(self.amplitude_y_max, max(ampl))
        self.ampl_plot.setYRange(0, self.amplitude_y_max)

        self.app.processEvents()

        self.sweep_index += 1
        return True


if __name__ == "__main__":
    IQPyQtGraphExample().run()
