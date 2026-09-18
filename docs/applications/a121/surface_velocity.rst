Surface Velocity
================

This example uses the A121 to measure the surface velocity of a water flow.
Both direction and velocity are estimated.

Setup
-----
The sensor needs to be positioned at an angle. The sensor angle, :attr:`~acconeer.exptool.a121.algo.surface_velocity._example_app.ExampleAppConfig.sensor_angle`, is defined
as the angle from the water surface, thus 0 degrees is defined as the sensor facing straight down to the surface.
The angle needs to be big enough to get a good velocity estimate and small enough to get enough reflected radar signal back to the sensor.
It was found that the optimal angle is between 35 and 45 degrees.
The optimal range to be measured is calculated based on the sensor angle, the perpendicular distance from the sensor to the surface,
:attr:`~acconeer.exptool.a121.algo.surface_velocity._example_app.ExampleAppConfig.surface_distance`,
the number of points to be measured, and the step length.
Based on the measured range, the optimal profile is automatically chosen.

The direction of the flow is seen as either positive or negative. Water flowing towards the sensor will be seen as negative flow,
while water flowing away from the sensor will be seen as positive flow.

.. image:: /_static/processing/surface_velocity_setup.png
    :align: center

Time series
-----------
Based on the set sweep rate and the sensor angle, the maximum velocity that can be measured is decided.
The resolution is determined by the number of samples in the time series, set by the
:attr:`~acconeer.exptool.a121.algo.surface_velocity._example_app.ExampleAppConfig.time_series_length`.
By default, continuous sweep mode and double buffering are enabled.
With continuous sweep mode, the interval between the last sweep in one frame and the first sweep in the following frame is the same as
the interval between the sweeps in the frames, see :ref:`rdac-a121-csm`.
This makes it possible to create a time series that is longer than the number of sweeps per frame, giving good resolution with a high sweep rate.
If the continuous sweep mode is not used, the time series length will be set to the number of sweeps per frame.

To estimate the velocity, the power spectral density (PSD) is calculated for all measured distances and the PSD with the most energy
is used for the velocity estimate.
The PSD is low pass filtered in time and the filter coefficient is set by the
:attr:`~acconeer.exptool.a121.algo.surface_velocity._example_app.ExampleAppConfig.psd_lp_coeff`.
If a small sensor angle is used, the PSD can get a high peak around 0 Hz. Due to this, a slow zone is defined,
:attr:`~acconeer.exptool.a121.algo.surface_velocity._example_app.ExampleAppConfig.slow_zone`.
The slow zone is neglected when choosing PSD based on energy. Furthermore, peaks in the PSD outside the slow zone are prioritized.

Peak finding
------------
The threshold method used to find peaks in the PSD is based on a one-sided constant false alarm rate (CFAR) threshold.
The parameters for this threshold are the window from which the neighboring frequency bins are averaged,
:attr:`~acconeer.exptool.a121.algo.surface_velocity._example_app.ExampleAppConfig.cfar_win`,
and the guard or gap around the frequency bin of interest, which is omitted,
:attr:`~acconeer.exptool.a121.algo.surface_velocity._example_app.ExampleAppConfig.cfar_guard`.
Finally, there is a sensitivity parameter, between zero and one, adjusting the threshold,
:attr:`~acconeer.exptool.a121.algo.surface_velocity._example_app.ExampleAppConfig.cfar_sensitivity`.

Because of the chaotic nature of water flow, the peaks in the PSD are not constantly present.
With lower velocities, the time between peaks is larger. To have a steady estimate of the velocity, an interval is set and during this time
the velocity estimate does not change if the new estimate is a decrease larger than 20%. The maximum interval time is controlled by the
:attr:`~acconeer.exptool.a121.algo.surface_velocity._example_app.ExampleAppConfig.max_peak_interval_s`.

Peaks in the PSD that are closer together than 0.1 m/s will be regarded as the same. If the estimated velocity is based on
a merged peak, it will be seen as a colored area around the velocity estimate in the GUI.

As a final step, the estimated velocity from the PSD is low pass filtered with a filter coefficient that is controlled by the
:attr:`~acconeer.exptool.a121.algo.surface_velocity._example_app.ExampleAppConfig.velocity_lp_coeff`.

GUI
---
The top plot in the GUI shows a timeline of the estimated velocity. It also displays the distance that was used for the estimate.
In the second plot, the PSD together with the CFAR threshold is shown.
The frequencies have been converted to velocities and the colored middle section in the PSD represents the slow zone.

.. image:: /_static/processing/surface_velocity_gui.png
    :align: center

Configuration parameters
------------------------

.. autoclass:: acconeer.exptool.a121.algo.surface_velocity._example_app.ExampleAppConfig
   :members:

Detector result
--------------------
.. autoclass:: acconeer.exptool.a121.algo.surface_velocity._example_app.ExampleAppResult
   :members:
