.. _rdac-a212-interpreting-radar-data:

.. include:: ../common/interpreting_radar_data.rst

Multi-channel IQ data
---------------------

For A212, each frame carries IQ data from multiple virtual channels (TX-RX antenna pairs).
The data model from the section above extends to a third index :math:`c` for the channel:

.. math::

   z(s, d, c)

where :math:`s` is the sweep index, :math:`d` the distance point index, and :math:`c` the
virtual channel index (TX-major order, see :ref:`rdac-a212-sweeps-and-frames`).

Across any single channel, the same concepts apply as described above: coherent averaging
over sweeps improves SNR for static objects, and changes in phase over sweeps indicate motion.

Having IQ data from multiple TX-RX pairs enables *spatial processing*.
Each TX transmits from a distinct position and each RX receives from a distinct position.
A signal from a target at angle :math:`\theta` therefore arrives at each channel with
a characteristic phase offset determined by the antenna positions and the carrier wavelength.
These phase offsets can be utilized by *beamforming*, which forms a weighted sum of the
channels to filter returns by direction.
The result is a spatial map of received power versus angle and distance, commonly
referred to as a *heatmap*, as illustrated in :numref:`fig_data_beamformed_a212`.

.. _fig_data_beamformed_a212:
.. figure:: /images/handbook/a212/data_beamformed.png
   :align: center
   :width: 80%

   Mocked beamformed output of an environment with two objects at different positions.
   The x-axis is the cross-range dimension and the y-axis is the range dimension.
   Bright regions indicate high reflected signal amplitude.
