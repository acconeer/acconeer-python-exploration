Presence detection (sparse)
===========================

An example of a presence/motion detection algorithm based on the :ref:`sparse-service` service. Similarly to its :ref:`iq-service` service counterpart, :ref:`iq-presence-detection`, this example of presence detection measures small changes in radar response over time through the difference between a fast and a slow IIR filter.

The :ref:`sparse-service` service returns sweeps in the form of multiple subsweeps. Each subsweep constitutes of :math:`N_d` range points spaced roughly 6 cm apart. We denote sweeps captured using the sparse service as :math:`x(f,s,d)`, where :math:`f` denotes the sweep index, :math:`s` the subsweep index and :math:`d` the range index. As described in the documentation of the :ref:`sparse-service` service, small movements within the field of view of the radar appear as large sinusoidal movements of the spatial sampling points over time. For each range point, we thus wish to detect any changes between individual point samples occurring in the :math:`s` dimension.

In this example, this is accomplished using exponential smoothing. Two exponential filters are used, one with a larger smoothing factor, :math:`\alpha_{fa}`, and one with a smaller, :math:`\alpha_{sl}`. Each subsweep of a sweep is thus filtered through

.. math::
    x_{sl}(d) \leftarrow \alpha_{sl}x_{sl}(d) + (1 - \alpha_{sl})x(f, s, d),

.. math::
    x_{fa}(d) \leftarrow \alpha_{fa}x_{fa}(d) + (1 - \alpha_{fa})x(f, s, d).

A detection metric, :math:`\delta`, is obtained by taking the average difference between the two smoothed outputs as in

.. math::
    \delta = \frac{1}{N_d}\sum_{i=0}^{N_d-1}|x_{fa}(i) - x_{sl}(i)|.

:math:`\delta` thus corresponds to amount of movement occurring in the radars field of view. Finally, :math:`\delta` is thresholded to produce a prediction if movement was significant.

The presence detector can be tuned by changing the :math:`\alpha_{fa}` parameter. This parameter can be related to a time constant :math:`\tau_{fa}`, which corresponds to what movement speeds will be detected. Increasing :math:`\tau_{fa}` will also increase the noise floor in :math:`\delta`, so a tuning of the threshold might be necessary when altering :math:`\tau_{fa}`.

.. image:: /_static/processing/sparse_presence.png

In the above image output of the sparse presence detection algorithm is shown. The top plot shows the :math:`|x_{fa}(d) - x_{sl}(d)|` vector. Clear detection of a moving target is seen at a distance of roughly 1.3 m. In the bottom part the evolution of :math:`\delta` is plotted. Since :math:`\delta` is above the threshold of 0.3 presence is detected.
