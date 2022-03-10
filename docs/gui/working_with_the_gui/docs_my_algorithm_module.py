# my_algorithm_module.py

from enum import Enum

import pyqtgraph as pg

import acconeer.exptool as et
from acconeer.exptool.a111.algo import ModuleFamily, ModuleInfo


class MySensorConfig(et.a111.EnvelopeServiceConfig):
    """Defines default sensor config and service to use"""

    def __init__(self):
        super().__init__()
        self.profile = et.a111.EnvelopeServiceConfig.Profile.PROFILE_1
        self.range_interval = [0.1, 0.5]  # in meters
        self.running_average_factor = 0.01
        self.maximize_signal_attenuation = True
        self.update_rate = 60
        self.gain = 0.2
        self.repetition_mode = et.a111.EnvelopeServiceConfig.RepetitionMode.SENSOR_DRIVEN


class MyProcessingConfiguration(et.configbase.ProcessingConfig):
    """
    Define configuration options for plotting and processing.
    The GUI will populate buttons and sliders for
    all parameters defined here. Check the other detectors for examples!
    """

    VERSION = 1

    class PlotColors(Enum):
        ACCONEER_BLUE = "#38bff0"
        WHITE = "#ffffff"
        BLACK = "#000000"
        PINK = "#f280a1"

    plot_color = et.configbase.EnumParameter(
        label="Plot color",
        enum=PlotColors,
        default_value=PlotColors.ACCONEER_BLUE,
        updateable=True,
        order=10,
        help="What color the plot graph should be",
    )

    scale = et.configbase.FloatParameter(
        label="Scale",
        default_value=1.0,
        decimals=3,
        limits=[0.001, 1.0],
        updateable=True,
        order=20,
        help="Allows you to scale the incoming envelope by a factor",
    )


class MyNewProcessor:
    """Processor class, which should do all the processing in the example."""

    def __init__(self, sensor_config, processing_config, session_info, calibration=None):
        self.scale = processing_config.scale

    def update_processing_config(self, processing_config):
        """This function is called when you change sliders or values in the GUI"""

        self.scale = processing_config.scale

    def process(self, data, data_info):
        """
        This function is called every frame and should return the `dict` out_data.
        """

        scaled_data = self.scale * data
        out_data = {"scaled_data": scaled_data}
        return out_data


class MyPGUpdater:
    """This class does all the plotting."""

    def __init__(self, sensor_config, processing_config, session_info):
        self.plot_color = processing_config.plot_color.value
        self.data_length = session_info["data_length"]

    def setup(self, win):
        """
        This function sets up all graphs and plots. Check the other
        detectors and examples to see how to initialize different
        types of graphs and plots!
        """
        win.setWindowTitle("My new example")

        self.my_plot = win.addPlot(title="My Plot")
        self.my_plot.setMenuEnabled(False)
        self.my_plot.setMouseEnabled(x=False, y=False)
        self.my_plot.hideButtons()
        self.my_plot.addLegend()
        self.my_plot.showGrid(x=True, y=True)
        self.my_plot.setXRange(0, self.data_length)
        self.my_plot.setYRange(0, 100)

        self.my_plot_curve = self.my_plot.plot(
            pen=pg.mkPen(self.plot_color, width=2),
            name="Envelope signal",
        )

    def update_processing_config(self, processing_config=None):
        """This function is called when you change sliders or values in the GUI"""

        self.plot_color = processing_config.plot_color.value
        self.my_plot_curve.setPen(self.plot_color, width=2)

    def update(self, out_data):
        """
        This function is called each frame and receives the dict `out_data` from `MyProcessor`.
        """
        data_from_my_processor = out_data["scaled_data"]
        self.my_plot_curve.setData(data_from_my_processor)


my_module_info = ModuleInfo(
    key="my_algorithm_module",
    label="My Algorithm Module",
    module_family=ModuleFamily.EXAMPLE,
    multi_sensor=False,
    docs_url=None,
    pg_updater=MyPGUpdater,
    processing_config_class=MyProcessingConfiguration,
    sensor_config_class=MySensorConfig,
    processor=MyNewProcessor,
)
