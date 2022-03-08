.. _gui-select-service:

Choosing a service or detector
==============================

At this point, you should have connected to your sensor via one of the available options.
By default, the GUI selects the Envelope service, if no other service has been selected.
Other services or detectors can be selected via the drop down list.

Our sensor can be run in one of these four basic services:

+---------------------------+------------------------------+-----------------------------------------------------------------------+
| **Service**               | **Data Type**                | **Example Use Case**                                                  |
+===========================+==============================+=======================================================================+
| :ref:`envelope-service`   | | Amplitude only             | | Absolute distance (e.g. water level)                                |
| (:ref:`pb-service`)       |                              | | Static presence (e.g. parking sensor)                               |
+---------------------------+------------------------------+-----------------------------------------------------------------------+
| :ref:`iq-service`         | | Amplitude and Phase        | | Obstacle detection (e.g. lawn mower, RVC, <30 cm/s)                 |
|                           |                              | | Breathing                                                           |
|                           |                              | | Relative distance (down to 50 microns)                              |
+---------------------------+------------------------------+-----------------------------------------------------------------------+
| :ref:`sparse-service`     | | Instantaneous amplitude    | | Speed (up to m/s)                                                   |
|                           | | at high rep-rate           | | Presence detection (moving objects)                                 |
|                           |                              | | People counting                                                     |
+---------------------------+------------------------------+-----------------------------------------------------------------------+

.. _select-service-figure:
.. figure:: /_static/gui/select_service.png
    :figwidth: 40%
    :align: right

    Service and detector drop-down menu in the GUI

Each of these services has it's own advantages and disadvantages and knowing about the capabilities of each service will help you select the correct one for your use-case.

In order to better understand the type of information you can get with each service, the GUI can be used to look at the unprocessed data of each of those.
Just select any of those services from the **Select service and detectors** drop-down menu and click **Start measurement**.

.. attention::
    Using the Acconeer Exploration Tool interface, you can only use one service/detector at a time. Even when using several sensors, you cannot use different service types or detectors on different sensors with the GUI.

Detectors
---------
Each detector is based on one of the above listed services, but applies post-processing to the data in order to work out the information relevant to the detector.
In the drop-down list, you can see the used service added in brackets after the detector name (see :numref:`select-service-figure`).
At the moment we have the following examples and detectors to choose from:

#. **Envelope Service**

   - :ref:`Distance Detection <distance-detector>`  (Detector)
   - :ref:`Button Press <button-press>` (Example)

#. **IQ Service**

   - :ref:`Phase Tracking <phase-tracking>` (Example)
   - Breathing (Example)
   - :ref:`Sleep Breathing <sleep-breathing>` (Example)
   - :ref:`Obstacle Detection <obstacle-detection>` (Detector)

#. **Sparse Service**

   - :ref:`Presence Detection <sparse-presence-detection>` (Detector)
   - Sparse short-time FFT (Example)
   - Sparse long-time FFT (Example)
   - Speed (Example)

The main difference between a detector and an example is that for detectors, we have the matching C-code available.

.. tip::
    All settings and names you can find for the detector in the GUI are kept the same in the C-code and the processing is identical to allow tuning parameters in the GUI and just copy & pasting the settings to your C-code implementation.


Adding your own detector
^^^^^^^^^^^^^^^^^^^^^^^^
At some point you may want to write your example/detector for your application and use the GUI to test and tune it.
You will need to do the following steps:

#. Create a new python file in the `/examples/processing/ <https://github.com/acconeer/acconeer-python-exploration/tree/master/examples/processing>`_ sub-folder. Best is to copy one of the existing files and rename it to something like *my_new_detector.py*
#. Change the `modules.py <https://github.com/acconeer/acconeer-python-exploration/blob/master/gui/elements/modules.py>`_, which defines the services and detectors loaded into the GUI, to include the new detector.

Detector file structure
"""""""""""""""""""""""
If your *my_new_detector.py* file follows has the correct structure, the GUI will populate buttons and settings automatically for you.
You must not change any function or class names; the only class name you can change, is the *DetectorProcessor* class!

.. code-block:: python
   :emphasize-lines: 11,12,26,27,39,40,41,61,62,63,71,72,75,76,77,87,88,95,96,97,113,114,117,118,119

    import numpy as np

    from PySide6 import QtCore

    import pyqtgraph as pg

    from acconeer.exptool import configs, utils
    from acconeer.exptool.clients import SocketClient, SPIClient, UARTClient
    from acconeer.exptool.pg_process import PGProccessDiedException, PGProcess
    from acconeer.exptool.structs import configbase

    def main():
        # Only needed if you want to run the detector from the command line
        args = utils.ExampleArgumentParser(num_sens=1).parse_args()
        utils.config_logging(args)

        if args.socket_addr:
            client = SocketClient(args.socket_addr)
        elif args.spi:
            client = SPIClient()
        else:
            port = args.serial_port or utils.autodetect_serial_port()
            client = UARTClient(port)

        ...

    def get_sensor_config():
        # Define default sensor config and service to use
        config = a111.EnvelopeServiceConfig()
        config.profile = a111.EnvelopeServiceConfig.Profile.PROFILE_1
        config.range_interval = [0.04, 0.05]
        config.running_average_factor = 0.01
        config.maximize_signal_attenuation = True
        config.update_rate = 60
        config.gain = 0.2
        config.repetition_mode = a111.EnvelopeServiceConfig.RepetitionMode.SENSOR_DRIVEN
        return config


    class ProcessingConfiguration(configbase.ProcessingConfig):
        # Define configuration options for detector. The GUI will populate buttons and sliders for
        # all parameters defined here. Check the other detectors for examples!
        VERSION = 2

        signal_tc_s = configbase.FloatParameter(
            label="Signal time constant",
            unit="s",
            default_value=5.0,
            limits=(0.01, 10),
            logscale=True,
            updateable=True,
            order=10,
            help="Time constant of the low pass filter for the signal.",
        )

        ...


    class MyNewProcessor:
        # Detector class, which does all the processing. This is the only class/function name you
        # can change!
        def __init__(self, sensor_config, processing_config, session_info):
            assert sensor_config.update_rate is not None

            ...

            self.update_processing_config(processing_config)

        def update_processing_config(self, processing_config):
            # This function is called when you change sliders or values for the detector in the GUI
            ...

        def process(self, sweep):
            # This function is called every frame and should return the struct out_data, which
            # contains all processed data needed for graphs and plots
            ...

            out_data = {
                ...
            }

            return out_data


    class PGUpdater:
        # This class does all the plotting.
        def __init__(self, sensor_config, processing_config, session_info):
            self.sensor_config = sensor_config
            self.processing_config = processing_config

            ...

        def setup(self, win):
            # This function sets up all graphs and plots. Check the other detectors to see how to
            # initialize different types of graphs and plots!
            win.setWindowTitle("My new detector example")

            self.my_plot = win.addPlot(title="My Plot")
            self.my_plot.setMenuEnabled(False)
            self.my_plot.setMouseEnabled(x=False, y=False)
            self.my_plot.hideButtons()
            self.my_plot.addLegend()
            self.my_plot.showGrid(x=True, y=True)
            self.my_plot.setLabel("bottom", "Time (s)")
            self.my_plot.setXRange(-HISTORY_LENGTH_S, 0)
            self.my_plot.setYRange(0, OUTPUT_MAX_SIGNAL)
            self.my_plot_curve = self.my_plot.plot(
                pen=utils.pg_pen_cycler(0),
                name="Envelope signal",
            )
                ...

        def update_processing_config(self, processing_config=None):
            # This function is called when you change sliders or values for the detector in the GUI
            ...

        def update(self, data):
            # This function is called each frame and receives the struct out_data. Any plotting of
            # data you want to do, needs to be within this struct.
            ...

Module definition for the GUI
"""""""""""""""""""""""""""""
When you change the modules file for the GUI, you need to import your new detector and then define the module info.

There are three options for handling multi-sensor support:

#. Do not allow multiple sensors --> set mutli-sensor flag to False
#. Allow multiple sensors        --> set mutli-sensor flag to True

    a) Use a wrapper (multiplies graphs and plots, when you select more than one sensor)
    b) Define plots and graphs for individual sensors in your processor

.. code-block:: python
   :emphasize-lines: 7,23,34,58

    from collections import namedtuple
    from types import ModuleType

    from acconeer.exptool.modes import Mode

    import examples.processing.breathing as breathing_module
    # Import your new dector here
    ...

    from helper import PassthroughProcessor


    def multi_sensor_wrap(module):
        ...

        class WrappedPGUpdater:
            ...


    multi_sensor_distance_detector_module = multi_sensor_wrap(distance_detector_module)
    multi_sensor_sparse_speed_module = multi_sensor_wrap(sparse_speed_module)
    multi_sensor_presence_detection_sparse_module = multi_sensor_wrap(presence_detection_sparse_module)
    # If you want to wrap your graphs for multiple sensors, define a wrapper for your detector here

    ModuleInfo = namedtuple("ModuleInfo", [
        "key",
        "label",
        "module",
        "sensor_config_class",
        "processor",
        "multi_sensor",
        "docs_url"
    ])
    # Module info tuple

    MODULE_INFOS = [
        ModuleInfo(
            None,
            "Select service or detector",
            None,
            ModuleFamily.OTHER,
            None,
            None,
            True,
            "https://acconeer-python-exploration.readthedocs.io/en/latest/services/index.html",
        ),
        ModuleInfo(
            Mode.ENVELOPE.name.lower(),
            "Envelope",
            envelope_module,
            ModuleFamily.SERVICE,
            envelope_module.get_sensor_config,
            envelope_module.Processor,
            True,
            "https://acconeer-python-exploration.readthedocs.io/en/latest/services/envelope.html",
        ),

        ...

        # Add your module info here, following above tuple structure.
    ]

    ...
