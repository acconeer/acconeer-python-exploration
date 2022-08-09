How to configure
================

Considerations
--------------

Start by asking yourself the following questions related to your application:

- What range do we need to cover, from :math:`r_\text{near}` to :math:`r_\text{far}`?
- Do we need to distinguish multiple objects? If so, how close could they be?
- Do we need to measure distance to objects? If so, what trueness is needed?
- If objects move, how fast could they go?
- Do we need to measure motions of objects? If so, what speeds?
- With what rate do we need to obtain a result?
- What are our requirements on overall power consumption?
- What is the farthest distance from the sensor that an object may appear which could result in range ambiguities?

Range-related parameters
------------------------

Having these questions and answers in mind, we go though the parameters in order, starting with those related to the range:

- Use the highest **profile** possible for maximum overall power and time efficiency.
  It is often limited by :math:`r_\text{near}` since the *close-in distance (CID)* must be smaller than :math:`r_\text{near}`, and higher profiles have a larger CID.
  If you need to resolve multiple objects, the duration of the pulse must be short enough to give the resolution needed.
  Finally, lower profiles may give more precise distance measurements.
- The **step length** should be as long as possible to reduce memory usage and decrease measurement time.
  It is typically limited by two things:

  - Distance measurement trueness:
    As a rule of thumb, the steps need to be 1/10 to 1/2 of the required trueness.
    Note that as steps get smaller, other factors such as SNR and pulse duration (profile) have a bigger impact on the general accuracy.
  - The profile:
    If steps are too long, reflecting objects may fall between points, creating "blind spots" in the range.
    See :numref:`fig_a121_optimal_range_config` for an example.
- From here, the **start point** and **number of points** can be set.
  Just make sure the points cover :math:`r_\text{near}` to :math:`r_\text{far}`.
  Due to the pulse length (profile), the start and end points doesn't necessarily have to pass :math:`r_\text{near}` and :math:`r_\text{far}`.
  Again, see figure~\ref{fig:optimal_range_config} for an example of this.
  However, keep in mind that distance measurements typically cannot be done in the very edge of the range, so you might have to extend it outside :math:`r_\text{near}` and :math:`r_\text{far}` anyways.
- Set the PRF such that the resulting maximum unambiguous range (MUR) extends beyond the farthest distance an object may appear.
  Keep it as high as possible since a higher PRF is more power and time efficient overall.

.. _fig_a121_optimal_range_config:
.. figure:: /_tikz/res/handbook/a121/optimal_range_config.png
   :align: center
   :width: 80%

   A sketch of setting up the measurement range for efficient coverage of a given area.

Rate-related parameters
-----------------------

With the range related parameters all set up, we move on to parameters related to sampling rate:

- If you need to estimate velocities, that typically means applying an FFT on a frame over sweeps to produce a distance-velocity (a.k.a. range-Doppler) map.
  In that case, the
  **sweeps per frame (SPF)**
  sets the frequency (velocity) resolution.
  For e.g. micro- and macro gesture recognition, typical values range from 16 to 64.
  For more accurate velocity measurements, typical values are much higher ranging from 128 to 2048.

  If you don't need to estimate velocities but still need to detect "fast" motions (:math:`\gtrapprox 500 \text{Hz}`),
  that typically means estimating the energy within a frame.
  For such cases, e.g. running, walking, waving, typical SPF:s range from 8 to 16.

  If you need to detect "slow" motions or have a mostly static environment, there is no need to use multiple sweeps per frame (SPF), so set it to 1.
  Such cases include (inter-frame) presence detection and distance measurements.

- For cases where SPF = 1, the **sweep rate** is not applicable.
  What matters then is setting the **HWAAS** to achieve the needed SNR.
  Keep in mind that measurement time linearly increases with HWAAS,
  so keeping it as low as possible is important to manage the overall power consumption.

  For cases where SPF > 1,
  the **sweep rate** :math:`f_s` should be adapted to the range of speeds of interest.
  A good rule of thumb is

  .. math::
    :label:

    f_s
    \approx \frac{10}{\lambda_{RF}} \cdot |v|_\text{max}
    \approx 2000 \text{m}^{-1} \cdot |v|_\text{max}

  where :math:`|v|_\text{max}` is the possible maximum relative speed between the radar and the object (in m/s).

  In many cases, the most efficient way to achieve the target sweep rate is by adapting the HWAAS.
  The sweep rate is inversely proportional to the number of HWAAS.
  It is also possible to directly control the sweep rate, letting the sensor idle between sweeps.
  However, idling between sweeps is rarely as efficient as idling between frames.

- If power consumption is not an issue, start by using the highest possible **frame rate**.
  Otherwise, it is crucial to minimize the frame rate to let the sensor idle in a lower power state as much as possible.
  See :numref:`tab_a121_typical_parameter_values` for typical values.

.. _tab_a121_typical_parameter_values:
.. table:: Typical parameter values for some applications.
    :align: center
    :widths: auto

    +----------------------------------+------------+
    | Application                      | Frame rate |
    +==================================+============+
    | Micro gesture recognition        | 30 - 50 Hz |
    +----------------------------------+------------+
    | Medium power presence detection  | 10 - 80 Hz |
    +----------------------------------+------------+
    | Low power presence detection     | 1 - 5 Hz   |
    +----------------------------------+------------+

Other parameters
----------------

- Leave **receiver gain** at the default value and reduce if saturation occurs.
- Leave **enable TX** set (default).
