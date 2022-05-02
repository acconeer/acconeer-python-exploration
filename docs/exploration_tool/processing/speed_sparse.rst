.. _sparse-speed:

Speed (sparse)
===========================

This is a speed measuring algorithm built on top of the :ref:`sparse-service` service -- based on measuring changes in the radar response over time. The algorithm calculates a speed estimate of a target's radial speed from or towards the sensor.

Plots
-----

.. figure:: /_static/processing/sparse_speed.png
    :align: center

    A screenshot of the plots. A target detected with the speed 4.4 m/s can be seen.

**Top plot:**
The plot shows the normalized power spectral density (PSD) for a frame in dB on the y-axis and speed in m/s on the x-axis. The dotted black line marks the threshold level set in *Processing settings*.

**Lower left plot:**
The scatter plot shows all points which surpass the threshold in the top plot. The black line marks the point with the greatest speed.

**Lower right plot:**
The plot illustrates the the latest top speeds in a bar graph. There must be approximately 0.5s between two point clusters to make the graph register a new top speed.

Detailed description
--------------------

The :ref:`sparse-service` service returns data frames in the form of :math:`N_s` sweeps, each consisting of :math:`N_d` range depth points, normally spaced roughly 6 cm apart. We denote frames captured using the sparse service as :math:`x(f,s,d)`, where :math:`f` denotes the frame index, :math:`s` the sweep index and :math:`d` the range depth index. As described in the documentation of the :ref:`sparse-service` service, small movements within the field of view of the radar appear as sinusoidal movements of the sampling points over time. Thus, for each range depth point, we wish to detect changes between individual point samples occurring in the :math:`f` and :math:`s` dimensions.

Speed estimation
^^^^^^^^^^^^^^^^
The speed estimation algorithm is based on the power spectral density of the radar signal. Welch's or Bartlett's method is used to estimate this PSD.

The estimation is carried out by dividing the sweeps for each distance into segments, then forming a windowed periodogram of each segment and averaging all segments together.

The *m*:th windowed and zero-padded segement from the signal *x* can be denoted by

.. math::
   x_m(n) \triangleq w(n)x(n+mR), \; \; n=0, 1 ... M-1, \;\; m=0, 1, .., K-1

where *R* is defined as the segment size, :math:`w(n)` is defined as the window function and *K* is defined as the number of segments. The periodogram of the *m* th segment is given by

.. math::
   P_{x_m,M}(w_k) = \frac{1}{M}|\text{FFT}_{N,k}(x_m)|² \triangleq \frac{1}{M}\left | \sum_{n=0}^{N-1} x_m(n)e^{-j2\pi nk/N}\right |^2

The power spectral density estimation is then given by

.. math::

   \hat{S_x}(w_k)\triangleq \frac{1}{K} \sum_{m=0}^{K-1} P_{x_m, M}(w_k)

which calculates the average of the periodograms.

In *Processing settings* the estimation method can be chosen as either Welch's or Bartlett's method. In Welch's method the overlap of the segments are 50% and the used window, :math:`w(n)`, is a Hann window.
In Bartlett's method the segments does not overlap and :math:`w(n)` is a rectangular window, which results in a non-modified periodogram. Welch's method will result in lower variance, less leakage but decreased resolution compared to Bartlett's method.


When the estimated PSD is attained by the methods above, the speed can easily be derived from its frequency contents. A period of a sinusoid in the data corresponds to an object having moved a perceived wavelength of the radar, i.e., ~2.5mm. So, for example, if we see a sinusoid with a frequency of 1kHz, we can calculate that this corresponds to a speed of 1000 Hz * 0.0025m = 2.5m/s.



Graphical overview
^^^^^^^^^^^^^^^^^^

.. graphviz:: /_graphs/speed_sparse.dot
   :align: center

Configuration parameters
------------------------

.. autoclass:: acconeer.exptool.a111.algo.speed_sparse._processor.ProcessingConfiguration
   :members:
   :exclude-members: SpeedUnit
