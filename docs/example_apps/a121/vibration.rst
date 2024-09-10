Vibration Measurement
=====================

This example application illustrates how the A121 sensor can be used to estimate the
frequency content of a vibrating object, measured at a distance.

The Sparse IQ service produces complex data samples where the amplitude reflects the amount of
returning energy and the phase the relative timing between the transmitted and received pulse.
The phase can be used to detect small displacements.
The vibration measurement application takes advantage of this, by forming a time series of the
measured phase at a single distance point, which is then analyzed using an FFT.
See :ref:`interpreting_radar_data` for more information about the produced data.

Usage
-----
This section describes how to get started with the Vibration Example Application, how to configure it and important concepts.

Your first measurement
^^^^^^^^^^^^^^^^^^^^^^
To make a first measurement, it is recommended to connect one of Acconeer's evaluation kits to the Exploration Tool.
Choose Vibration Measurement in the GUI.
Place the sensor facing the object in the vibrating direction.
Set the distance from the sensor to the object by adjusting the parameter
:attr:`~acconeer.exptool.a121.algo.vibration._example_app.ExampleAppConfig.measured_point` and then press start measurement.


Exploration Tool
^^^^^^^^^^^^^^^^

The GUI, see figure below, has three plots. The upper left plot indicates the amplitude at the
measured point. The purpose of this is to provide visual feedback on whether or not the
object is located at the right distance from the sensor. The blue horizontal line shows the chosen amplitude threshold.
With no object in front of the sensor, the value should be close to zero.
When moving an object into the correct location, the value increases.
Next, the upper right plot shows the displacement of the measured object.
Here, the phase has been converted to :math:`\mu m`, indicating the physical displacement of the object.
Lastly, the lower plot shows the calculated spectrum. In this case, the vibrating object has a dominant frequency at 166 Hz.
The orange line shows the CFAR threshold, and the orange dot shows the peak value.
Note that the upper right plot and bottom plot only are updated when the object's amplitude
is above the amplitude threshold.

.. image:: /_static/processing/a121_vibration_gui.png
    :align: center

Embedded C
^^^^^^^^^^

An embedded C application is provided in the Acconeer SDK, available at the `Acconeer Developer Site <https://developer.acconeer.com/>`_.

The embedded application has the same presets as Exploration Tool and has most of the output Exploration Tool has.
Max amplitude (upper left plot), peak displacement and frequency of the spectrum (peak in lower plot)
are available in the result struct.

By default, the application prints the result using ``printf`` which usually is connected to stdout or a debug UART, depending on environment. The application is provided in source code.

Presets
^^^^^^^
In the Vibration Example App there are two presets that can help as a starting point depending on the desired frequency span that is of interest:

High frequency
    This preset will detect vibrations with frequencies up to 5000 Hz. The measurement distance is 0.2 m.
Low frequency
    For this preset, low frequency enhancement is enabled, see :ref:`low-freq_enhancement`.
    Vibrations with frequencies up to 100 Hz will be detected at a distance of 0.2 m.


Time Series
^^^^^^^^^^^
If continuous sweep mode is enabled, set by :attr:`~acconeer.exptool.a121.algo.vibration._example_app.ExampleAppConfig.continuous_sweep_mode`,
the length of the time series is determined by the parameter
:attr:`~acconeer.exptool.a121.algo.vibration._example_app.ExampleAppConfig.time_series_length`.
A longer time series will give more points in the resulting spectrum. The frequency resolution
is given by the ratio of the sweep rate and the number of points in the time series.
If continuous sweep mode is not enabled, the time between two consecutive sweeps and two consecutive frames will not be the same.
Due to this, the FFT will be calculated on a per frame basis, meaning that the time series length will be equal to the number of sweeps per frame,
:attr:`~acconeer.exptool.a121.algo.vibration._example_app.ExampleAppConfig.sweeps_per_frame`,
and :attr:`~acconeer.exptool.a121.algo.vibration._example_app.ExampleAppConfig.time_series_length` parameter
will be redundant.
The sweep rate, :attr:`~acconeer.exptool.a121.algo.vibration._example_app.ExampleAppConfig.sweep_rate`,
should be set high enough to be able to capture the highest frequency of interest.
The Nyquist theorem states that the sampling rate must be at least twice the highest frequency that is of interest.

The example app configuration also has a time constant,
:attr:`~acconeer.exptool.a121.algo.vibration._example_app.ExampleAppConfig.lp_coeff`,
applied together with an exponential filter, providing the possibility to time filter the
calculated spectrum. A higher time constant gives a more stable spectrum.
However, the spectrum will also adapt slower to changes in the frequency content.

For every frequency in the spectrum, the power is converted to a displacement.
The displacements can be computed in two different ways, either as amplitude or peak to peak value.
This is set by the :attr:`~acconeer.exptool.a121.algo.vibration._example_app.ExampleAppConfig.reported_displacement_mode`
parameter.

Thresholds
^^^^^^^^^^
There are two threshold parameters,
:attr:`~acconeer.exptool.a121.algo.vibration._example_app.ExampleAppConfig.amplitude_threshold`,
and :attr:`~acconeer.exptool.a121.algo.vibration._example_app.ExampleAppConfig.threshold_margin`, which are used together.
The first one determines if an object is in front of the sensor and if the
algorithm should run, while the second one is used to find peaks in the frequency spectrum.
The algorithm only calculates the FFT if there is an object in front of the sensor and
the amplitude threshold,
:attr:`~acconeer.exptool.a121.algo.vibration._example_app.ExampleAppConfig.amplitude_threshold`,
sets the needed amplitude for an object to be considered detected.
When an object is detected, the FFT is calculated and a CFAR threshold is computed to determine peaks in the spectrum,
and the overall sensitivity of the CFAR threshold is adjusted by the threshold margin,
:attr:`~acconeer.exptool.a121.algo.vibration._example_app.ExampleAppConfig.threshold_margin`.

.. _low-freq_enhancement:

Low Frequency Enhancement
^^^^^^^^^^^^^^^^^^^^^^^^^
Low frequencies, down to about 1 Hz, can sometimes be difficult to detect in the spectrum due to an increased noise floor.
To correct the noise floor, a subsweep with a loopback measurement (see :ref:`api_a121_configs` for more information) can be added.
The loopback measurement is used to adjust the phase for each sweep to compensate for jitter in the measurement.
This will create a flat noise floor in the FFT, see figure below.
This feature can be enabled with the parameter
:attr:`~acconeer.exptool.a121.algo.vibration._example_app.ExampleAppConfig.low_frequency_enhancement`.
Since a subsweep is added, the number of samples is increased and thus, the sweep rate cannot be as high as without this feature.
Due to this, it is only recommended to enable this feature if there is an interest in detecting very low frequencies.

.. image:: /_static/processing/a121_vibration_flat_fft.png
    :align: center

Example App Output
^^^^^^^^^^^^^^^^^^
The :attr:`~acconeer.exptool.a121.algo.vibration._example_app.ExampleAppResult` class contains all output result from this example application.
For the decision if an object is present in front of the sensor or not, the maximal amplitude is used, and this is reported in the
:attr:`~acconeer.exptool.a121.algo.vibration._example_app.ExampleAppConfig.max_sweep_amplitude`.
As well as reporting the largest detected displacement,
:attr:`~acconeer.exptool.a121.algo.vibration._example_app.ExampleAppConfig.max_displacement`,
and for which frequency this is found,
:attr:`~acconeer.exptool.a121.algo.vibration._example_app.ExampleAppConfig.max_displacement_freq`,
all displacement together with all the frequencies they are calculated for is reported in the
:attr:`~acconeer.exptool.a121.algo.vibration._example_app.ExampleAppConfig.lp_displacements`
and the
:attr:`~acconeer.exptool.a121.algo.vibration._example_app.ExampleAppConfig.lp_displacements_freqs`.
However, usually it is the maximal displacement and the corresponding frequency that is of highest interest.
The last reported result is the
:attr:`~acconeer.exptool.a121.algo.vibration._example_app.ExampleAppConfig.time_series_std`,
which is the standard deviation of the last processed time series.

Exploration Tool Python API
---------------------------

Configuration Parameters
^^^^^^^^^^^^^^^^^^^^^^^^
.. autoclass:: acconeer.exptool.a121.algo.vibration._example_app.ExampleAppConfig
   :members:

Example App Result
^^^^^^^^^^^^^^^^^^
.. autoclass:: acconeer.exptool.a121.algo.vibration._example_app.ExampleAppResult
   :members:
