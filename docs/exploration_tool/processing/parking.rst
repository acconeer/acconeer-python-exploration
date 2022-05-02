.. _parking:

Parking (envelope)
==================

An example of a detection algorithm for a parked car using a ground mounted sensor.

Detection of a parked car over the sensor is straightforward if it is parked with a
large metal surface directly above the sensor. A plastic cover over the metal surface
is usually not a problem either. A harder but not unusual case occurs when a car with
a polymer fuel tank is parked with the tank directly above the sensor. In that case,
the radar reflection can be weak enough to make detection difficult.

This example algorithm is meant as a starting point for parking detector implementations
that can handle weak radar reflections as well. One issue with the use of weak
reflections is that reflections from people or items near the sensor can lead to false
detects. For that reason, the detection algorithm monitors changes between each sweep
to exclude objects that move.

The algorithm is designed to work with only one radar sweep every 10 seconds to keep
power consumption low enough for a battery supply to last for several years. Designs
that do not have this limitation can use a higher sweep rate.

The exclusion of moving objects leads to delayed detection of a car that just has parked.
For default settings, the first two scans after a car stopped over the sensor will report
false detection status. Hence, it takes up to 30 seconds before a parked car is detected
with one scan every 10 seconds. There is no extra delay when a car leaves, as the first
scan with no car above the sensor gives a false detection status.

The quality of the radar data depends strongly on the design of the sensor casing. It's
important that the amount of radar waves that bounce back within the casing is minimized
to enable detection of weak reflections from a parked car. If the default settings of
this example detector lead to false detects when there is nothing in front of the
sensor, it's likely that the reflections within the casing are too strong for reliable
detection. If that is the case, then consider a revisit of the sensor integration or
tuning of the detector parameters (described below).

The default values of the parameters are selected based on laboratory tests in the full
sensor design temperature range of -40°C to 85°C. These tests have progressed since our
first release of this parking detector, and we have changed the ``leak_max_amplitude``
parameter default value from 1000 to 2000. This change is intended to avoid false car
detections at temperatures near -40°C.

Plots
-----

.. figure:: /_static/processing/parking_plots.png
    :align: center

    A screenshot of the parking detection plots for a sensor placed under a parked car.

**Top plot:**
The envelope data :math:`x(d)` (blue) from the last sweep and the corresponding background
estimate (green). The orange dots represent control parameters of the background estimate
as described in the section "Leakage subtraction" below.

**Middle plot:**
The weight distribution :math:`w(d)` from the last sweep (blue), coordinates :math:`(D, W)`
in the detector queue (orange and green), and visualization of the detection criterion (red)
controlled by the parameters :math:`W_{\textrm{threshold}}`, :math:`Q`, and :math:`S`.
The last coordinate (corresponding to the blue sweep data) is shown in orange and older
coordinates that are still in the detector queue are shown in green. The red rectangle is
drawn in such a way that the detection criterion is satisfied if and only if the detector
queue is full and all coordinates in the detector queue (orange and green) fall within the
rectangle. The width of the rectangle is :math:`S` and the ratio of the weight coordinates
between the top and bottom is :math:`Q`. The threshold :math:`W_{\textrm{threshold}}` is
marked with a dashed red line.

**Bottom plot:**
Detection status (True or False) for sweeps in the last measurement sequence. This plot is
cleared when a setting is changed or when data collection is restarted. Note that the first
two results are false although there is a car above the sensor. Due to the exclusion of
moving objects, the first :math:`K - 1` scans always get false detection results. Similarly,
a newly parked car will not be detected during the first :math:`K - 1` scans immediately
after it parked.


Detailed description
--------------------

This example detector uses the :ref:`envelope-service` service with settings that work
well for detection of weak reflections in laboratory tests. Only the update rate is
different from our recommended starting point for application development. This rate is
set to 0.5 Hz instead of 0.1 Hz to work better for interactive exploration.


Leakage subtraction
~~~~~~~~~~~~~~~~~~~

The default configuration for parking detection uses Profile 2 and a sweep range that
starts 12 cm from the sensor. This setting excludes direct leakage caused by radar waves
travelling directly between the Tx and Rx antennas. There is also an an indirect leakage
of radar waves that bounce within the sensor casing. This form of leakage is very hard
to avoid in typical sensor casing designs (for the above-mentioned settings). For this
reason, the parking detection algorithm is designed to work as long as the leakage stays
within some fixed limits.

The leakage is assumed to drop off linearly in the envelope amplitude from a sample distance
:math:`d_{\textrm{leak sample}}` to zero at a larger distance that is at most
:math:`d_{\textrm{leak end}}`. A maximal value :math:`x_{\textrm{max leak}}` is set for
the envelope amplitude at :math:`d_{\textrm{leak sample}}` as a result of leakage.
Let :math:`x(d)` denote envelope data and let :math:`x_{\textrm{BG}}` denote the
envelope sweep background level, i.e. an envelope sweep level taken at distances without
leakage and without objects. Let

.. math:: A_{\textrm{leak}} = \max\left(
              \min(x(d_{\textrm{leak sample}}), d_{\textrm{max leak}}) - d_{\textrm{BG}},
	      0\right).

A leakage subtracted envelope :math:`y(d)` is calculated from the envelope data
according to

.. math:: y(d) = \max\left(x(d) - A_{\textrm{leak}}\,\frac{\max(d_{\textrm{leak end}} - d, 0)}
                {d_{\textrm{leak end}} - d_{\textrm{leak sample}}}, 0\right).


Calculation of weight and distance
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The parking detector needs to work for weak reflections with amplitudes that are not much
larger than the background noise level. The noise-level normalization ensures that the
background level is close to a typical value :math:`x_{\textrm{BG}}` and that is useful for
calculation of suitable observables.

A fixed threshold may be used to filter out amplitude values that are too close to the noise
level. That approach has the drawback that it adds a parameter that can be hard to find a
suitable value for. Instead, a smooth ramping is used for calculations that are likely to work
well enough over varying circumstances. Define the ramp function :math:`f` according to

.. math:: f(x) = \max(0, \min(x, 1)).

With this ramp function, a smoothly filtered amplitude observable with background subtraction
is calculated according to

.. math:: z(d) = f\left(y(d)\big/x_{\textrm{BG}} - 1\right)\max\left(y(d) - x_{\textrm{BG}}, 0\right).

The intensity of the radar reflection from a flat surface falls off as :math:`d^{-2}` with
distance and that corresponds to a proportionality to :math:`d^{-1}` for the signal amplitude.
To correct for that distance dependence, a weight function is calculated according to

.. math:: w(d) = z(d)d.

From the weight function, a weight average :math:`W` and a mean reflection distance :math:`D`
are calculated for each sweep according to

.. math:: W = \frac1N\sum_{i=1}^N w(d_i)

and

.. math:: D = \frac{\sum_{i=1}^N w(d_i)d_i}{\sum_{i=1}^N w(d_i)},

where :math:`d_1, d_2, \ldots, d_N` are the distance points that are sampled by the envelope
service.


Detector queue and detection criterion
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Reflections from non-stationary objects and people standing near the parking sensor shall not
be classified as a parked car. For that reason, the weights and distances for a few sweeps
need to be considered and if there is a sufficiently large variation in :math:`W` or :math:`D`,
the detected reflections are unlikely to come from a parked car.

Value pairs :math:`(W, D)` for recent sweeps are stored in a queue called the *detector queue*.
The queue has a fixed size denoted by :math:`K`, and the value pair for the oldest sweep in
the queue is dropped when a new pair is added to a full queue. No detection is generated before
the queue is filled. The detection criterion operates on the minimum and maximum values of
:math:`W` and :math:`D` denoted by :math:`W_{\textrm{min}}`, :math:`D_{\textrm{min}}`,
:math:`W_{\textrm{max}}`, and :math:`D_{\textrm{max}}`, respectively.

The criterion detecting a car and excluding moving objects is

.. math:: W_{\textrm{min}} \ge W_{\textrm{threshold}} \textrm{ and }
          W_{\textrm{max}} \big/ W_{\textrm{min}} \le Q \textrm{ and }
          D_{\textrm{max}} - D_{\textrm{min}} \le S

where :math:`W_{\textrm{threshold}}`, :math:`Q`, and :math:`S` are configurable parameters.


Configuration parameters
------------------------

.. autoclass:: acconeer.exptool.a111.algo.parking._processor.ProcessingConfiguration
   :members:
