.. _a212_heatmap_channel_corrections:

Channel Corrections
===================

Introduction
^^^^^^^^^^^^

All four beamformers in the previous sections compare the channel data with a :term:`steering vector <Steering vector>` :math:`\mathbf{a}`: the phase and amplitude that each channel is expected to observe for a reflection from a given direction.

A steering vector computed from the antenna positions alone is called a *nominal steering vector*. On a real A212, the response of each channel deviates from the *nominal steering vector*, and the deviation depends on the direction of the reflection. Acconeer has measured these deviations and provides them as *channel corrections* (also called *channel calibration*), which turn the *nominal steering vector* into a *corrected steering vector*.

This page describes how Exploration Tool computes the *corrected steering vectors*. All four heatmap processors use them, and they should be used whenever A212 sparse IQ data is beamformed, including in custom processing outside the heatmap processors.

Antenna array
^^^^^^^^^^^^^

Positions and directions are given in the sensor coordinate system. Its y axis points along the boresight, its x axis is horizontal and its z axis is vertical.

The A212 has three TX antennas and four RX antennas. Their positions are given by :attr:`a2.AntennaArray.AP212 <acconeer.exptool.a2.AntennaArray.AP212>`. All antennas lie in the x-z plane, at y = 0.

Each combination of one TX antenna and one RX antenna forms a virtual channel, called a channel in the rest of this page. This gives 12 channels in total. The channels are numbered in TX-major order: :math:`m` = 4 × TX index + RX index. Channels 0 to 3 thus use TX0, channels 4 to 7 use TX1, and channels 8 to 11 use TX2. The position :math:`\mathbf{p}_m` of a channel is the sum of the positions of its TX and RX antennas.

A subsweep does not have to use all antennas. Its TX and RX antenna masks (:attr:`~acconeer.exptool.a2.SubsweepConfig.tx_antenna_mask` and :attr:`~acconeer.exptool.a2.SubsweepConfig.rx_antenna_mask`) select the active antennas: bit :math:`i` of a mask enables antenna :math:`i`. Only the channels whose TX and RX antennas are both active are measured. These are the active channels.

Steering vectors
^^^^^^^^^^^^^^^^

A reflection from azimuth :math:`\theta` and elevation :math:`\phi` arrives from the direction given by the unit vector

.. math::

   \mathbf{u}(\theta, \phi)
   = \begin{bmatrix} \sin \theta \\ \cos \theta \cos \phi \\ \cos \theta \sin \phi \end{bmatrix}.

At boresight, :math:`\theta = \phi = 0`. A positive azimuth turns the direction towards the x axis, and a positive elevation turns it towards the z axis.

For this direction, the *nominal steering vector* :math:`\mathbf{a}_0` has one element for each active channel :math:`m`:

.. math::

   a_{0,m}(\theta, \phi)
   = \frac{1}{\sqrt{N_{ch}}} \exp\left(-j \frac{2\pi}{\lambda}\, \mathbf{p}_m \cdot \mathbf{u}(\theta, \phi)\right).

Here, :math:`N_{ch}` is the number of active channels, and :math:`\lambda \approx 4.96` mm is the wavelength at 60.5 GHz. The factor :math:`1/\sqrt{N_{ch}}` normalizes the vector to unit length.

To obtain the *corrected steering vector* :math:`\mathbf{a}_\text{c}`, each element is multiplied by the complex channel correction :math:`k_m(\theta, \phi)` of its channel, and the result is normalized to unit length again:

.. math::

   \mathbf{a}_\text{c}(\theta, \phi)
   = \frac{\mathbf{k}(\theta, \phi) \odot \mathbf{a}_0(\theta, \phi)}{\lVert \mathbf{k}(\theta, \phi) \odot \mathbf{a}_0(\theta, \phi) \rVert}.

Since both vectors contain only the active channels, the norm in the denominator is also taken over the active channels only.

The :math:`\mathbf{a}(\theta, \phi)` in the beamformer outputs of the previous sections is this *corrected steering vector* :math:`\mathbf{a}_\text{c}(\theta, \phi)`.

Channel correction tables
^^^^^^^^^^^^^^^^^^^^^^^^^

The channel corrections are computed with a two-dimensional Chebyshev model over azimuth and elevation. The coefficients of the model are stored in two tables, one calibrated to recordings made with :term:`profile <Profile>` 3 and one calibrated to recordings made with profile 6. The profile of the subsweep determines which table to use, as shown in :numref:`a212_heatmap_channel_corrections_table_profiles`.

.. list-table:: Correction table used for each profile.
   :name: a212_heatmap_channel_corrections_table_profiles
   :header-rows: 1

   * - Profiles
     - Correction table
   * - 1 to 5
     - Calibrated based on profile 3 recordings
   * - 6 and 7
     - Calibrated based on profile 6 recordings

Using the steering vectors
^^^^^^^^^^^^^^^^^^^^^^^^^^

Each subsweep needs its own steering vectors, computed with its profile and antenna masks for all directions to beamform. The elements must be in the same order as the channels in the data.

The steering vectors depend only on the configuration. Compute them once when the configuration is set, not for every frame, and compute them again if the profile or the antenna masks change.

Exploration Tool
^^^^^^^^^^^^^^^^

In Exploration Tool, the antenna array :attr:`a2.AntennaArray.AP212 <acconeer.exptool.a2.AntennaArray.AP212>` holds the antenna positions and the correction tables, and the methods in :numref:`a212_heatmap_channel_corrections_table_methods` compute the steering vectors. Profiles are given as ``a2.Profile.PROFILE_1`` to ``a2.Profile.PROFILE_7``. The heatmap processors call ``get_steering_vectors`` when they are created, with the :attr:`~acconeer.exptool.a2.algo.heatmap.config_common.HeatmapConfigCommon.antenna_array` of their configuration and the profile and antenna masks of their subsweep.

.. list-table:: Methods of ``a2.AntennaArray.AP212``.
   :name: a212_heatmap_channel_corrections_table_methods
   :widths: 40 60
   :header-rows: 1

   * - Method
     - Description
   * - ``get_steering_vectors(az_angles, el_angles, tx_antenna_mask, rx_antenna_mask, *, profile)``
     - Returns the *corrected steering vectors* for all combinations of the azimuths ``az_angles`` and the elevations ``el_angles``, both given as arrays in degrees. The result is a complex array of shape ``(num_az, num_el, num_channels)``.
   * - ``get_steering_vector(az, el, rx_mask, tx_mask, corrected=True, *, profile)``
     - Returns the steering vector for a single direction, with ``az`` and ``el`` in radians. Note that ``rx_mask`` comes before ``tx_mask``. With ``corrected=False``, the *nominal steering vector* is returned.
   * - ``get_correction_scalar(channel_number, az, el, *, profile)``
     - Returns the channel correction :math:`k_m` of channel ``channel_number`` for the direction (``az``, ``el``), given in radians.
   * - ``channels(tx_mask, rx_mask)``
     - Returns the active channels, keyed by channel number. The ``.position`` of a channel is its position :math:`\mathbf{p}_m` in mm.

The data layout of a subsweep is described in :ref:`rdac-a212-sweeps-and-frames`.

Example
^^^^^^^

The following example computes the *corrected steering vectors* for the first subsweep, and then the delay-and-sum output power :math:`|y|^2` (see :doc:`Coherent <coherent>`) at one distance point. It assumes that ``sensor_config`` is the sensor configuration, ``result`` is an :class:`a2.Result <acconeer.exptool.a2.Result>` of one frame, and ``distance_point`` is the index of a distance point.

.. code-block:: python

   import numpy as np

   from acconeer.exptool import a2

   subsweep_index = 0
   subsweep = sensor_config.subsweeps[subsweep_index]

   # Once per configuration
   az_deg = np.linspace(-60, 60, 121)
   el_deg = np.linspace(-40, 40, 81)
   steering_vectors = a2.AntennaArray.AP212.get_steering_vectors(
       az_deg,
       el_deg,
       subsweep.tx_antenna_mask,
       subsweep.rx_antenna_mask,
       profile=subsweep.profile,
   )  # (num_az, num_el, num_channels)
   num_channels = steering_vectors.shape[-1]

   # For every frame
   subframe = result.get_subframe(sensor_config, subsweep_index)
   data = subframe.reshape(subframe.shape[0], subsweep.num_points, num_channels)
   x = data[:, distance_point, :].mean(axis=0)  # Channel vector at the distance point
   power = np.abs(steering_vectors.conj() @ x) ** 2  # (num_az, num_el)

Limitations
^^^^^^^^^^^

The channel corrections describe the sensor population rather than an individual sensor, so the response of a single sensor deviates from them. This deviation is small enough for :doc:`Capon <capon>` to estimate the :term:`direction of arrival <DOA>`, but too large for Capon to estimate amplitudes. :doc:`Robust Capon <robust_capon>` handles amplitudes better.

The correction tables were fitted to measurements at azimuths from :math:`-60^\circ` to :math:`60^\circ` and elevations from :math:`-40^\circ` to :math:`40^\circ`. Outside this range, the correction is extrapolated.
