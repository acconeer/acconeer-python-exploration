Waste Level
===========

This waste level example application uses the A121 radar sensor to measure the fill level in a waste bin.
Some waste materials are bad reflectors, such as paper and plastic. Hence, the :doc:`Tank Level</exploration_tool/algo/a121/ref_apps/tank_level>` reference application,
which is built on top of the :doc:`Distance Detector</exploration_tool/algo/a121/detectors/distance_detection>`,
cannot be used as the received signal in this case does not typically yield a distinct peak.
Instead, a metric based on the phase stability is utilized.

Algorithm
---------
The algorithm assumes a sensor placed at the top of the bin and facing towards the bottom.
The placement could be beneath the lid or on the outside depending on the material of the waste bin.
Due to low reflectivity of some materials, especially different kinds of plastics, an algorithm based on the amplitude of the signal is not a good fit.
Instead, the coherent part of the A121 radar sensor is used when looking at the phase of the reflected signal.
When measuring in open air, no energy is reflected towards the sensor and the measured signal consists of pure noise, hence the phase is random.
When an object is present, even with low reflectivity as for some plastics, the phase gets stable and therefore has a low standard deviation.
These characteristics make the standard deviation of the phase to be high when measuring open air and low when measuring a static object.
This is utilized in the waste level example application.
Multiple sweeps per frame are needed to measure the standard deviation of the phase.
This is done per frame for each distance in the chosen range.
To get a good estimation of the fill level, several distances in a row should have stable phase.
In this distance sequence, the fill level is estimated as the distance closest to the sensor, i.e., the distance closest to the top of the bin.
Finally, to reduce variation further, a median filter is applied on the estimated fill level.

Processing Configuration
------------------------
The top, :attr:`~acconeer.exptool.a121.algo.waste_level._processor.ProcessorConfig.bin_start_m`,
and the bottom, :attr:`~acconeer.exptool.a121.algo.waste_level._processor.ProcessorConfig.bin_end_m`, of the bin need to be configured by the user.
This is the distance from the sensor to the respective parts of the bin.
Then the threshold, :attr:`~acconeer.exptool.a121.algo.waste_level._processor.ProcessorConfig.threshold`, needs to be set.
If the standard deviation of the phase is below this value, it is assumed stable.
A good value to start with is the default threshold setting, but further evaluation can be done in the waste bin of choice and with the desired waste material.
The threshold value should be set higher than the standard deviation values seen where the waste is present.
However, it should be as close as possible to these values to reduce false detection levels.
Next, the number of distances in sequence that needs to have stable phase for the distance to be regarded as a fill level is set by
:attr:`~acconeer.exptool.a121.algo.waste_level._processor.ProcessorConfig.distance_sequence_n`.
Furthermore, the length of the median filter, :attr:`~acconeer.exptool.a121.algo.waste_level._processor.ProcessorConfig.median_filter_length`, can be adjusted.
A longer filter will give a more robust estimate of the fill level, but also make the algorithm slower to adapt to changes in the fill level.

Sensor Configuration
--------------------
In the waste level application, there are two conditions for the sensor configuration.
The number of sweeps per frame must be more than three.
This is to get a statistically significant value of the standard deviation.
However, a higher number of sweeps per frame is preferable to get an even better estimate of the metric.
The second condition is that if subsweeps are used, they cannot overlap in distance.

Considerations
--------------
A lens or reflector that narrows down the radar beam is recommended with this application to avoid detection of the bin's sides.
For the same reasons, the sensor should be placed at the center of the bin or where there is a clear sight to the bottom.
Depending on the material of the waste bin, the sensor can be placed on the outside of the lid or beneath it.

GUI
---
The bottom plot in the GUI shows the metric from which the fill level is decided.
This is the standard deviation of the phase per frame for each distance point.
The chosen threshold is illustrated with a dashed line.
In this example, the fill level is where four or more distance points in a row are below the threshold, these distances can be seen in green in the example figure.
If only one to three distance points are below the threshold, these can be seen in orange.
The top left plot illustrates the waste bin together with the fill level in both meters and percent.
The top right plot shows the history of the detected fill level in meters.

.. image:: /_static/processing/waste_level_gui.png
    :align: center

Sanity Testing
--------------
The testing performed with this application was made in a plastic waste bin with height 1 m, width 0.5 m and depth 0.5 m, and with waste consisting of plastic.
The FZP lens from the Acconeer lens kit was used together with an EVK.
The fill levels tested together with the estimated levels can be found in :numref:`tab_a121_waste_level_test_result`.

.. _tab_a121_waste_level_test_result:
.. table:: Sanity test results.
   :align: center
   :widths: auto

   +--------------+-----------------+
   | True level   | Estimated level |
   +==============+=================+
   | 0%           | 9%              |
   +--------------+-----------------+
   | 25%          | 26%             |
   +--------------+-----------------+
   | 50%          | 59%             |
   +--------------+-----------------+
   | 75%          | 73%             |
   +--------------+-----------------+
   | 100%         | 93%-100%        |
   +--------------+-----------------+

One reason for the errors seen in the estimated levels could be because of an uneven level of the plastic bags.
In the test with the empty waste bin, the reason for the higher level is because of an uneven bottom.
For the full waste bin, the estimated fill level was alternating between 93% and 100%.
For the other tests, the estimated fill level was static.

Configuration Parameters
------------------------

.. autoclass:: acconeer.exptool.a121.algo.waste_level._processor.ProcessorConfig
   :members:

Detector Result
--------------------
.. autoclass:: acconeer.exptool.a121.algo.waste_level._processor.ProcessorResult
   :members:
