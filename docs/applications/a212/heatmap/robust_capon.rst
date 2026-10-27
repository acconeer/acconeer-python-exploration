.. _a212_heatmap_robust_capon:

Robust Capon Heatmap Processor
==============================

Introduction
^^^^^^^^^^^^

The robust Capon heatmap processor is a variant of Capon that protects against :term:`steering-vector <Steering vector>` mismatch by allowing the assumed :term:`steering vector <Steering vector>` to lie anywhere inside a spherical uncertainty set of radius :attr:`~acconeer.exptool.a2.algo.heatmap.robust_capon.HeatmapConfig.steering_vector_epsilon` rather than being a single fixed vector. The beamformer is implemented via an eigenvalue decomposition of the channel covariance matrix followed by a clamped Newton iteration on a Lagrange multiplier, both applied per range bin and per grid direction.

It keeps most of Capon's angular resolution while preserving amplitude estimates when calibration is imperfect or the :term:`SNR` is very low. The A212 sensor uses an offline-calculated :term:`steering-vector <Steering vector>` correction. Most of the :term:`steering-vector <Steering vector>` errors hence come from sensor population variations. The accuracy of the :term:`steering vectors <Steering vector>` is high enough to reliably use regular Capon. But the performance will degrade for large angles faster than the actual :term:`SNR` drops, because of the net effect of low :term:`SNR` and :term:`steering-vector <Steering vector>` uncertainties.

Typical use case
^^^^^^^^^^^^^^^^
* Same use cases as Capon.
* High-resolution :term:`direction-of-arrival <DOA>` with accurate amplitude estimates.
* :term:`Direction of arrival <DOA>` estimation in low :term:`SNR` data.

Pros and cons
^^^^^^^^^^^^^

**Pros**

* Retains most of Capon's resolution while being far more robust to :term:`steering-vector <Steering vector>` mismatch and low :term:`SNR`.
* Better amplitude estimate (compared to regular Capon).
* Full-rank covariance not needed.
* More stable performance over sensor population.

**Cons**

* Most expensive of the four processors: adds an eigenvalue decomposition plus a Newton iteration per ``(range, az, el)`` grid point.
* Slightly broader peaks than Capon as the uncertainty radius grows.
* Slightly higher heatmap noise level compared to Capon as the uncertainty radius grows.

Math and theory
^^^^^^^^^^^^^^^

Let :math:`R \in \mathbb{C}^{N_{ch} \times N_{ch}}` be the smoothed estimate of the channel covariance matrix at a given range bin and :math:`\bar{\mathbf{a}}(\theta, \phi) \in \mathbb{C}^{N_{ch}}` the nominal :term:`steering vector <Steering vector>` for direction :math:`(\theta, \phi)`. Robust Capon treats the true :term:`steering vector <Steering vector>` :math:`\mathbf{a}` as unknown, constrains it to lie within a spherical uncertainty set of radius :math:`\varepsilon` around :math:`\bar{\mathbf{a}}`, and solves the worst-case signal-power problem

.. math::

   P_{\text{robust\_capon}}(\theta, \phi)
   = \max_{\sigma_s^2,\, \mathbf{a}} \;\; \sigma_s^2
   \quad \text{subject to} \quad
   R - \sigma_s^2 \mathbf{a} \mathbf{a}^H \succeq 0,
   \quad
   (\mathbf{a} - \bar{\mathbf{a}})^H \mathbf{C}^{-1} (\mathbf{a} - \bar{\mathbf{a}}) \leq 1.

Here :math:`\sigma_s^2` is the candidate signal power at the direction; the first constraint requires the residual covariance (after subtracting the signal contribution :math:`\sigma_s^2 \mathbf{a}\mathbf{a}^H`) to remain positive semi-definite; the second confines the :term:`steering vector <Steering vector>` to an uncertainty ellipsoid defined by :math:`\mathbf{C}`. For the spherical case used here, :math:`\mathbf{C} = \varepsilon \mathbf{I}`, so the ellipsoid reduces to :math:`\lVert \mathbf{a} - \bar{\mathbf{a}} \rVert^2 \leq \varepsilon`.

The problem reduces to a one-dimensional search; the implementation solves it with an eigenvalue decomposition :math:`R = U\,\mathrm{diag}(\boldsymbol{\lambda})\,U^H` and a clamped Newton iteration on the Lagrange multiplier enforcing the uncertainty constraint. See P. Stoica and R. Moses, *Spectral Analysis of Signals* (Prentice Hall, 2005) for the full derivation.

Example spectrum plots
^^^^^^^^^^^^^^^^^^^^^^
Compared to Capon, Robust Capon achieves higher heatmap :term:`SNR` because the peak power better matches the actual signal power.

.. figure:: /images/processing/a212_heatmap_processing/figures/heatmap_robust_capon.png
    :align: center

    Robust Capon D–Az heatmap on a recording of three corner reflectors. The three colored markers and dashed lines mark the true reflector locations. The 1D plots show the distance and azimuth spectra cut at each of the three true peak locations. Recorded using :term:`Profile` 3, with :math:`\varepsilon = 0.02`.

.. figure:: /images/processing/a212_heatmap_processing/figures/el_spectrum_robust_capon.png
    :align: center

    Elevation spectrum of the Robust Capon heatmap at each of the three true peak locations. Recorded using :term:`Profile` 3, with :math:`\varepsilon = 0.02`.

Configuration
^^^^^^^^^^^^^

Shared parameters are documented in :doc:`common`. Processor-specific fields:

:attr:`~acconeer.exptool.a2.algo.heatmap.robust_capon.HeatmapConfig.covariance_matrix_time_constant_s`
    Time constant of the exponential smoothing applied to the per-range covariance matrices across frames. See the :ref:`shared notes <a212_heatmap_covariance_smoothing>` for more tuning guidance.

:attr:`~acconeer.exptool.a2.algo.heatmap.robust_capon.HeatmapConfig.high_pass_filter_time_constant_s`
    Time constant of the per-channel high-pass filter that runs before the covariance is built. The robust Capon processor always runs this filter; there is no :attr:`~acconeer.exptool.a2.algo.heatmap.conventional.HeatmapConfig.heatmap_mode` toggle. See the :ref:`shared notes <a212_heatmap_iq_highpass_filter>` for more tuning guidance.

:attr:`~acconeer.exptool.a2.algo.heatmap.robust_capon.HeatmapConfig.steering_vector_epsilon`
    Radius of the spherical uncertainty set around the nominal :term:`steering vector <Steering vector>`. Larger values increase robustness against :term:`steering-vector <Steering vector>` mismatch but broaden the main lobe and increase the heatmap noise floor. Values smaller than the actual uncertainty will produce poor amplitude estimates. A value of 0 gives the same behavior as normal Capon. ``0.1`` is a reasonable starting point for profile 6. ``0.02`` is a reasonable starting point for profile 3.

Typical processing cost
^^^^^^^^^^^^^^^^^^^^^^^

Per frame, Robust Capon does everything Capon does and then adds a per-range eigenvalue decomposition (:math:`\mathcal{O}(N_d \cdot N_{ch}^3)`) plus a clamped Newton iteration per ``(range, az, el)`` grid point (capped at eight iterations by default). This makes it the most expensive of the four processors. On the configuration the RSS computation time test measures, 12 virtual channels and 25 azimuth angles, this corresponds to **~5 ×** the per-frame cost of Conventional.

API reference
^^^^^^^^^^^^^

.. autoclass:: acconeer.exptool.a2.algo.heatmap.robust_capon.HeatmapProcessor
   :members:
   :undoc-members:

.. autoclass:: acconeer.exptool.a2.algo.heatmap.robust_capon.HeatmapConfig
   :members:
   :undoc-members:
