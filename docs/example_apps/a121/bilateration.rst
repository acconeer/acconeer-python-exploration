Bilateration
============

The bilateration algorithm estimates the distance and angle to objects, utilizing distance
estimates from two sensors.
It can be used in various scenarios, where the most obvious use cases are related to obstacle
detection and object tracking.

The algorithm utilizes the following key concepts:

**1. Distance estimation:**
The distance to objects, estimated using the existing distance detector algorithm.

**2. Kalman filter:**
Kalman filtering, employed for tracking the radial distance to objects over consecutive frames.

**3. Point formation:**
Combining the filtered result from the sensors into points, located in the plane spanned by the
two sensors.

Distance estimation
-------------------

The bilateration algorithm takes advantage of the existing distance detector algorithm for
estimating the radial distance to various objects in the scene.
For more information regarding the detector, see the
:doc:`/detectors/a121/distance_detection`
documentation.

Kalman filtering
----------------

Kalman filters are used for tracking the radial distance and velocity of individual objects
over consecutive frames.
In the case of multiple objects being detected in the scene, the corresponding number of filters
are instantiated to track each object individually.

In common Kalman filtering nomenclature, a measurement is a value typically originating from a
sensor reading.
The measurement is fed to the filter, producing a state estimate.
Here, the measurement is a estimated distance, provided by the distance detector.
The estimated state is the state vector of the Kalman filter, containing the estimated distance
and velocity of the object being tracked.
Note, the distance detector can output multiple distance estimates if multiple objects are
detected in the scene.

Each Kalman filter is updated using measurements provided by the distance detector.
The first step in the updating process is to pair an existing filter with one of the estimated
distances.
The pairing is done by comparing the filter distance state to each distance measurement from the
detector.
The measurement closest to the state is used.
However, the distance must be smaller than a threshold, derived from the user defined parameter
:attr:`~acconeer.exptool.a121.algo.bilateration._processors.ProcessorConfig.max_anticipated_velocity_mps`,
which is reflecting the largest anticipated change in distance between frames.

If a filter does not get paired with a distance measurement i.e., no distance was smaller than the
threshold, it is propagated using dead reckoning. Dead reckoning refers to the process of
predicting the states without a new measurement, based on the state is updated using the current
the state.
Each time dead reckoning is performed, a counter is incremented.
If the filter is paired with a distance measurement, the counter is reset back to zero.
The duration of the dead reckoning is determined by the user specified parameter
:attr:`~acconeer.exptool.a121.algo.bilateration._processors.ProcessorConfig.dead_reckoning_duration_s`.
Once exceeded, the filter is terminated and the object is no longer tracked.

The purpose of dead reckoning is to get a more robust behavior of the algorithm with regards to
temporary data dropouts.

The trade-off between responsiveness and robustness of the filter is determined by the user
provided configuration parameter
:attr:`~acconeer.exptool.a121.algo.bilateration._processors.ProcessorConfig.sensitivity`,
controlling the two following aspects of the filtering:

- **Process noise gain**: The process noise gain is applied to the process noise matrix, controlling the amount of uncertainty added to the state covariance matrix during each update. A higher sensitivity corresponds to higher process noise gain and a more responsive filter.

- **Filter initialization**: For a filter to be regarded as initialized and to be used in the subsequent bilateration process, it must have had a number of consecutive updates. The sensitivity parameter is mapped to this limit. A higher sensitivity corresponds to fewer required updates for the filter to be regarded as initialized.

Point formation
---------------
Point formation is the process of pairing distances tracked by the Kalman filters from each
sensor to form points in the 2D plan, spanned by the two sensors.

The distance between the two sensors is referred to as the sensor spacing.
The value is used by the algorithm and is defined through the processor configuration parameter
:attr:`~acconeer.exptool.a121.algo.bilateration._processors.ProcessorConfig.sensor_spacing_m`.
The parameter is used in the distance pairing process, detailed below.

For a given target, the theoretically largest distance difference measured by the two sensors, is
the sensor spacing. This occur when the object is located 90 degrees from the normal of the two
forward facing sensors. For all other locations of the target, the difference will be smaller than
the sensor spacing. Based on this, a point is formed if the absolute difference between two
estimates is less than the sensor spacing.

Once a point has been formed, the angle to the object can be determined through the following
formula.

.. math::
    \alpha = arctan (\frac{r^2_1-r^2_2}{\sqrt{2d^2(r^2_1+r^2_2) - (r^2_1-r^2_2)^2 - d^4/2}})

where :math:`r_1` and :math:`r_2` denotes the paired distances, and :math:`d` the sensor spacing.

The distance to the object is calculated as the average of :math:`r_1` and :math:`r_2`.
The point is visualized in the GUI as a blue dot(see section on the GUI below), indicating the
location of the object in the 2D plan.

Any distances from either sensor not matched during the process is regarded as an object without
a counterpart at the other sensor. This distance is visualized in the GUI as a half circle,
centered around the sensor location, providing distance information, but not angular information.

Considerations
--------------

Below follows some useful information and tips when optimizing the sensor integration.

Sensor installation
^^^^^^^^^^^^^^^^^^^

The following considerations and trade-offs comes into play, regarding the sensor installation.

    **Sensor spacing**: A wider spacing will be more robust to errors in the distance measurement,
    provided by the distance detector.
    However, a wider spacing can make the bilateration more sensitive in the case of non-uniform
    objects as the distance to the object could in fact vary due to the shape of the target, and
    not due to its location relative the sensors.

    **Sensor installation angle**: The sensors can be angled inwards(towards each other) to
    minimize the dead zone between the sensors. However, when doing this, the width of the overall
    detection zone is reduced. The sensors can also be angled upwards to avoid false detection
    from the ground.

    **Usage of lenses**: Lenses can be used to increase SNR and improve the performance of the
    algorithm, but will reduce the width of the detection zone.

Object shape and material
^^^^^^^^^^^^^^^^^^^^^^^^^
The following properties of an object will impact its detectability.

    **Material**: The material of the object impacts how much of the transmitted pulse if
    reflected back towards the sensor. More reflected energy will yield a higher SNR and better
    estimate. For instance, the metal leg of some garden furniture is typically a better reflector
    than a ceramic flower pot and will be detectable at a greater distance and with better
    accuracy, even if its geometrical shape is smaller.

    **Shape**: There are a few aspects related to the shape of the object that will determine
    its detectability. Firstly, the orientation of the normal of the object
    will impact how much of the transmitted energy is reflected back towards the sensor. A normal
    pointing towards the sensor is typically more favorable. Next, the uniformness of the object
    is also an important factor. Objects such as a furniture leg or a wall results in
    a distinct reflection, while a less uniform object such a tree trunk with roots will result in
    a wider distribution of the reflected energy, resulting in a less defined peak in the measured
    sweep.


GUI
---
The GUI contains the following two graphs.
The upper shows the sweep of each sensor, along with the corresponding threshold.
The lower plot shows a point(blue), identified by the algorithm, located at roughly 0.0 m
to the left and 0.40 m in front of the sensors. The plot also shows a blue half circle,
corresponding to a measurement from the left sensor at 0.9 m, without a counterpart at the right
sensor.

.. image:: /_static/processing/a121_bilateration_capture.png
    :align: center

.. autoclass:: acconeer.exptool.a121.algo.bilateration.ProcessorConfig
   :members:
