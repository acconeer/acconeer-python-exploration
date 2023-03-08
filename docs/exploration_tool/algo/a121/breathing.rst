Breathing
=========

This example shows how the breathing rate of a stationary person can be estimated using the A121 sensor.

The algorithm consists of the following key concepts:

- Form time series of relative movements.
- Apply a bandpass filter to time series.
- Estimate the power spectrum.

Form time series
----------------

The utilized concept is similar to the phase tracking example.
For details, see the :doc:`phase tracking documentation</exploration_tool/algo/a121/phase_tracking>`.

The sparse IQ service produce complex data samples where the amplitude corresponds to the amount of reflected energy
and the phase to the relative timing of the returning pulse.

A displacement of the reflecting object results in an altered phase of the returning pulse.
The change in phase between two consecutive measurements can be converted to a corresponding relative change in distance of the reflecting object.

The time series is formed by adding the relative change to the previous value and store the result in a fifo buffer.

The length of the time series is set by the processor configuration parameter :attr:`~acconeer.exptool.a121.algo.breathing.ProcessorConfig.time_series_length`.

Apply bandpass filter
---------------------

A bandpass filter is applied to each time series to remove signal content outside of the relevant frequency range.

The upper and lower cutoff frequencies of the bandpass filter are set through the processor configuration parameters
:attr:`~acconeer.exptool.a121.algo.breathing.ProcessorConfig.min_freq` and
:attr:`~acconeer.exptool.a121.algo.breathing.ProcessorConfig.max_freq`.

Estimate power spectrum
-----------------------

The power spectrum of each time series is estimated using Welch method, where the window size is set to 5 s.

The power spectrum for each distance is weighted with the corresponding amplitude and then averaged together to form a single power spectrum.

Lastly, the power spectrum is low pass filtered, using an exponential filter, where the filter constant is set through
the processor configuration parameter :attr:`~acconeer.exptool.a121.algo.breathing.ProcessorConfig.lp_coeff`.

GUI
---

The GUI consists of two plots.

The upper plot shows the time series.
If multiple distances are measured, the time series with the largest amplitude is visualized.
The distance being plotted is indicated at the top of the plot.

The lower plot shows the low pass filtered power spectrum.
The estimated breathing rate is indicated at the top of the plot.

.. image:: /_static/processing/a121_breathing.png
    :align: center

Heart rate
----------

The a121 sensor is also capable of detecting heart beats.
However, it is harder to estimate the heart rate as the displacement is much smaller compared to the breathing motion.

The following picture shows an initial segment of data where breathing and the heart beats are overlayed,
followed by a second segment where the person is holding its breath, making the heart beats more visable.

.. image:: /_static/processing/a121_breathing_and_heart.png
    :align: center

In this case, the upper freuqency of the bandpass filter has been increased, allowing more high
frequency content to pass.

Configuration parameters
------------------------

.. autoclass:: acconeer.exptool.a121.algo.breathing.ProcessorConfig
   :members:
