.. _sparse-button-press:

Button press (sparse)
===========================
This processor aims to implement a touchless button for close range, based on the :ref:`sparse-service` service. The intended use range is within 0.06-0.12 m, but works for longer ranges as well. For longer and/or more distant ranges there are more suitable options, like the "Wave to exit" algorithm, but experimentation is encouraged.

An algorithm calibration is required to compensate for the so called *direct leakage*. This processor can be thought of as a high pass filter in combination with an amplifier that facilitates the intuitive behavior of a button.


Data processing
---------------
The service data is processed depth wise. First it is averaged over all sweeps and then filtered with a exponential filter and then subtracted from the original signal. This difference is then amplified and filtered in two separate filters, called *trigger* and *cool-down*.
The trigger filter can trigger a detection (i.e. a button press) if the value is above a given threshold. After a detection has triggered, the cool-down filter must be below a given threshold in order to be able to trigger again.


Calibration
-----------
The calibration system is designed for usage in the Exploration Tool and similar experimental environments. If this code is to be used in a deployment, the calibration method could need adjustment.

The time constant of the first filter indirectly determines how much the underlying noise will affect the output. A slow filter will let through small deviations to the amplifier, and vice versa.

The calibration makes an estimate of the noise level and then adjusts the filter so that the noise passed to the amplifier is at a fixed level.

In exploration tool, the calibration is automatically applied after 1 second. So it is important that nothing is in front of the sensor at that time (it will likely cause the system to calibrate way too conservatively). The time slider adjusts the time between subsequent re-calibrations. Setting the calibration time to max will turn off the re-calibration completely.


Trigger behavior
------------------
The thresholds for trigger and cool-down are adjusted through two parameters: *Detection Sensitivity* and *Double-Trigger Sensitivity*. The detection sensitivity adjusts the threshold used for the trigger and cool-down filter. An increased detection sensitivity lowers the threshold and vice-versa.

The double-trigger sensitivity adjusts the time constant of the trigger and cool-down filters. The intended intuition is that a low value will make the gap between subsequent triggers shorter, with the caveat that a too low value will cause two triggers from one movement.

However, values close to 1 (larger than 0.95) can cause the cool down filter not to go above the trigger value at all, causing the system to report a trigger for each cycle.

If the range settings for the processor remains unchanged, the default values for the sensitivity and double-trigger can be left untouched. However, if the range is adjusted, it might be necessary to re-adjust the sensitivity to achieve the desired behavior.


.. figure:: /_tikz/res/button_press_sparse/button_press_data.png
   :align: center
   :width: 95%

   The raw data (blue) and the exponential filtered (orange). The orange follow the blue data very closely, as seen in the plot.

.. figure:: /_tikz/res/button_press_sparse/button_press_filter.png
   :align: center
   :width: 95%

   The filtered trigger values (blue) and cool-down values (orange) as well as button press indicators (green) when a trigger is found.

Recommended settings
--------------------
It is recommended to use shorter ranges (> 0.18 m), since the wave-to-exit is better suited for longer distances. It is also strongly recommended to only use profile 1 with this processor, even though profile 2 works as well. Profiles above that is mostly associated with longer ranges, and not recommended for this processor.

The update rate has a default value of 80 Hz, this might be too high for a power critical application, so this can be adjusted down. Update rates below 20 Hz risks to feel unresponsive to the user.
