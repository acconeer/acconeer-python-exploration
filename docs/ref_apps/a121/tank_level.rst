Tank Level Reference Application
================================

The tank level reference application shows the liquid level in a tank with an A121 sensor mounted at the top.
This reference application is built on top of the distance detector (see :doc:`/detectors/a121/distance_detector`) with some additional configurations specific to the tank level application.

Measurement range
    The liquid level in the tank can be measured from a minimum distance of 3 cm from the sensor to a maximum distance of 23 m.

Presets
    The application includes three predefined configurations optimized for tanks of varying sizes: small, medium, and large, corresponding to depths of 50 cm, 6.0 m, and 20.0 m, respectively.

Configuration
    The configuration parameter :attr:`~acconeer.exptool.a121.algo.tank_level._ref_app.RefAppConfig.start_m` defines the distance from the sensor to the surface of the liquid when the tank is full. Similarly, :attr:`~acconeer.exptool.a121.algo.tank_level._ref_app.RefAppConfig.end_m` defines the distance from the sensor to the tank base, i.e., the liquid level when the tank is empty.

    Multiple peaks can be detected in the distance domain by the detector due to various factors such as sensor installation, tank geometry, etc. The peak sorting method in the detector parameters can be used to ensure that the correct peak is chosen as the first peak for calculating the liquid level. Refer to :doc:`/detectors/a121/distance_detector` for a detailed description of the detector parameters.

    The tank level reference application also contains an additional power saving feature, applicable for medium to large tanks called *level tracking*. When enabling *level tracking* its possible to reduce the power consumption by up to 70-90% for large tanks (~15m). This is done by making the sweep range smaller than the nominal full range [:attr:`~acconeer.exptool.a121.algo.tank_level._ref_app.RefAppConfig.start_m`, :attr:`~acconeer.exptool.a121.algo.tank_level._ref_app.RefAppConfig.end_m`] while *tracking* the level. The parameter :attr:`~acconeer.exptool.a121.algo.tank_level._ref_app.RefAppConfig.level_tracking_active` is used to activate the *level tracking*. When this check box is enabled the distance detector will be configured to use a *partial* window centered around the previously measured level. The size of this partial window is determined by the parameter :attr:`~acconeer.exptool.a121.algo.tank_level._ref_app.RefAppConfig.partial_tracking_range_m`. A lower limit on the window size apply too ensure that the peak corresponding to the level can be resolved. Note that the peak width is affected by both the profile used and the object's physical properties. The allowed minimum partial window is only accounting for the maximum profile used, :attr:`~acconeer.exptool.a121.algo.tank_level._ref_app.RefAppConfig.max_profile`. The partial window will be active and track the level as long as some peak is detected by the distance detector within the partial window.

    In certain situations it is possible that the peak corresponding to the level is lost by the partial window. In this situation two scenarios are possible:

    * No peak is detected. Full range measurement is triggered next sample to locate the peak again.
    * Some other peak is detected corresponding to e.g reflections of the level or stationary objects. In this case the partial window will lose track of the actual level and give a false reading.

    Because of the second scenario with possibility of a silent errors, *level tracking* should be used with care only in applications where it can be ensured that the peak corresponding to the tank level will be the only peak above the threshold. Alternatively, *Level tracking* can be be used if level changes are slow (compared to sampling frequency), such that :attr:`~acconeer.exptool.a121.algo.tank_level._ref_app.RefAppConfig.partial_tracking_range_m` :math:`>2X_{max}`, where :math:`X_{max}` is the maximum level movement between two consecutive samples. This ensures that the peak corresponding to the level is not lost by the partial window between samples.

Calibration
    The distance detector calibration process performs noise level estimation and offset compensation.
    The close range measurement calibration is also performed in case the close range measurement is active, which depends on the starting distance.
    In addition, the recorded threshold is also computed if the detector is configured to use the recorded threshold or if the close range measurement is active.

    Before starting level measurements, the detector needs to be calibrated.
    For close range measurements, no object must be present in the close range when the calibration is started.

Processing
    The liquid level is given as the distance of the surface of the liquid from the tank base, and is calculated using the distance to the first peak in the distance detector results.
    Due to movement in the surface of the liquid, the level measurements may fluctuate.
    A median filter is employed to counter the fluctuation in the level results by calculating the median of :attr:`~acconeer.exptool.a121.algo.tank_level._ref_app.RefAppConfig.median_filter_length` results.
    Averaging :attr:`~acconeer.exptool.a121.algo.tank_level._ref_app.RefAppConfig.num_medians_to_average` median filter results can further improve the confidence in the level result.

GUI
---
The GUI includes three plots. The top left plot indicates the fluid level, and the top right plot shows the level history.
The bottom plot shows the tank size, the subsweeps, and the threshold used by the distance detector to detect amplitude peaks in the subsweeps. The subsweeps and different threshold types are described in :doc:`/detectors/a121/distance_detector`.

.. image:: /_static/processing/a121_tank_level.png
    :align: center

Testing
-------

Test setup
    The level estimation performance of the reference application is tested using the three different setups shown below, which correspond to small (left), medium (middle), and large (right) tanks.

    .. image:: /_static/processing/a121_tank_level_test_small.png
        :width: 32%

    .. image:: /_static/processing/a121_tank_level_test_medium.png
        :width: 31.8%

    .. image:: /_static/processing/a121_tank_level_test_large.png
        :width: 32.70%

Test equipment
    * A121 EVK + XR121
    * FZP lens ( for medium and large tanks)
    * Small tank (height = 30 cm)
    * Test tank (height = 1.0 m)
    * Exploration tool with Tank level reference application

    A simple workaround is used to estimate the performance for the medium and the large tank, where the sensor is mounted at a height to have the water level in at a longer distance than the actual test tank size.

Test case
    Fill tank x cm and verify that the actual distance is equal to the measured distance.
Configurations
    .. list-table:: Application parameter configurations
        :widths: 40 20 20 20
        :header-rows: 1

        * - Parameter
          - Small
          - Medium
          - Large
        * - Median filter length
          - 5
          - 3
          - 3
        * - Num measurements averaged
          - 5
          - 3
          - 1
        * - Tank start
          - 0.03 m
          - 0.05 m
          - 0.5 m
        * - Tank end
          - 0.3 m
          - 2.7 m
          - 7.8 m
        * - Max step length
          - 1
          - 2
          - 8
        * - Max profile
          - 1
          - 3
          - 5
        * - Threshold method
          - CFAR
          - CFAR
          - CFAR
        * - Reflector shape
          - Planar
          - Planar
          - Planar
        * - Peak sorting method
          - Closest
          - Strongest
          - Strongest
        * - Threshold sensitivity
          - 0.0
          - 0.0
          - 0.0
        * - Signal quality
          - 20
          - 20
          - 20

Results
    Few results obtained using the above configurations are listed below.

    .. list-table:: Test results
        :widths: 25 25 25
        :header-rows: 1

        * - Tank
          - Actual level (m)
          - Measured level (m)
        * - Small
          - 0.106
          - 0.104
        * - Medium
          - 0.398
          - 0.401
        * - Large
          - 0.100
          - 0.085

Configuration parameters
-------------------------
.. autoclass:: acconeer.exptool.a121.algo.tank_level._ref_app.RefAppConfig
   :members:

Results
-------
.. autoclass:: acconeer.exptool.a121.algo.tank_level._ref_app.RefAppResult
   :members:

.. autoclass:: acconeer.exptool.a121.algo.tank_level._processor.ProcessorLevelStatus
    :members:
    :undoc-members:
