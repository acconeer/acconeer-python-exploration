.. _a212_heatmap_conventional:

Conventional Heatmap Processor
==============================

Introduction
^^^^^^^^^^^^

The conventional heatmap processor applies a Bartlett (conventional) beamformer to a smoothed estimate of the channel covariance matrix. For each range bin and each grid direction :math:`(\theta, \phi)` it computes the quadratic form :math:`\mathbf{a}^H R\, \mathbf{a}`, which is the estimated power received in that direction assuming the :term:`steering vector <Steering vector>` is correct. It is the natural baseline for the processing methods: more expensive than coherent delay-and-sum, cheaper than Capon, no matrix inverse required. It gives a resolution determined only by the aperture width.

Typical use case
^^^^^^^^^^^^^^^^

* General-purpose heatmap use cases where Capon's higher resolution is not needed or where power estimation is important.
* Static scene beamforming (:attr:`~acconeer.exptool.a2.algo.heatmap.coherent.HeatmapConfig.HeatmapMode.DISTANCE`).


Pros and cons
^^^^^^^^^^^^^

**Pros**

* No matrix inverse — only the covariance build and a quadratic form.
* Can image static scenes — unlike Capon it handles correlated sources.
* Very robust to :term:`steering-vector <Steering vector>` mismatch and low SNR.
* Smoothing of the covariance matrix gives lower noise than coherent delay-and-sum.

**Cons**

* Angular resolution is limited by the array aperture. :term:`FWHM` :math:`\approx 10.2 ^\circ` at boresight; broadens off-boresight as the effective aperture scales with :math:`\cos\theta`.
* High side lobe levels; side lobes leak energy from strong reflectors into other directions.


Math and theory
^^^^^^^^^^^^^^^

Let :math:`R \in \mathbb{C}^{N_{ch} \times N_{ch}}` be the smoothed estimate of the channel covariance matrix at a given range bin and :math:`\mathbf{a}(\theta, \phi)` the :term:`steering vector <Steering vector>` for direction :math:`(\theta, \phi)`. The conventional beamformer output is

.. math::

   P_{\text{conv}}(\theta, \phi)
   = \mathbf{a}(\theta, \phi)^H R\, \mathbf{a}(\theta, \phi).

The output is real-valued (since :math:`R` is Hermitian positive semi-definite) and is interpreted as the power received from direction :math:`(\theta, \phi)`.

Example spectrum plots
^^^^^^^^^^^^^^^^^^^^^^
As seen in :numref:`a212_heatmap_fig_conventional`, the sidelobes of the actual targets can mask other weaker reflectors. A peak-finding algorithm would not be able to find the three positions. The beamforming method can, however, still be used for amplitude estimation.

.. figure:: /images/processing/a212_heatmap_processing/figures/heatmap_conventional.png
    :name: a212_heatmap_fig_conventional
    :align: center

    Conventional D–Az heatmap on a recording of three corner reflectors. The three colored markers and dashed lines mark the true reflector locations. The 1D plots show the distance and azimuth spectra cut at each of the three true peak locations. Recorded using :term:`Profile` 3.

.. figure:: /images/processing/a212_heatmap_processing/figures/el_spectrum_conventional.png
    :align: center

    Elevation spectrum of the conventional heatmap at each of the three true peak locations. Recorded using :term:`Profile` 3.

Configuration
^^^^^^^^^^^^^

Shared parameters are documented in :doc:`common`. Processor-specific fields:

:attr:`~acconeer.exptool.a2.algo.heatmap.conventional.HeatmapConfig.heatmap_mode`
    :attr:`~acconeer.exptool.a2.algo.heatmap.conventional.HeatmapConfig.HeatmapMode.MOVEMENT` enables a per-channel high-pass filter that suppresses the static scene before the covariance is formed; :attr:`~acconeer.exptool.a2.algo.heatmap.conventional.HeatmapConfig.HeatmapMode.DISTANCE` skips the filter.

:attr:`~acconeer.exptool.a2.algo.heatmap.conventional.HeatmapConfig.covariance_matrix_time_constant_s`
    Time constant of the exponential smoothing applied to the per-range covariance matrices across frames. Larger values reduce noise but introduce lag on moving targets. See the :ref:`shared notes <a212_heatmap_covariance_smoothing>` for more tuning guidance.

:attr:`~acconeer.exptool.a2.algo.heatmap.conventional.HeatmapConfig.high_pass_filter_time_constant_s`
    Time constant of the high-pass filter when :attr:`~acconeer.exptool.a2.algo.heatmap.conventional.HeatmapConfig.heatmap_mode` is :attr:`~acconeer.exptool.a2.algo.heatmap.conventional.HeatmapConfig.HeatmapMode.MOVEMENT`. Ignored otherwise. See the :ref:`shared notes <a212_heatmap_iq_highpass_filter>` for more tuning guidance.

Typical processing cost
^^^^^^^^^^^^^^^^^^^^^^^

Per frame, the work is dominated by the covariance processing (:math:`\mathcal{O}(N_d \cdot N_{ch}^2)`) and the beamforming quadratic form (:math:`\mathcal{O}(N_d \cdot N_{ch}^2 \cdot N_{az} \cdot N_{el})`). No matrix inverse is needed. This is the baseline for the family — **1 ×**. The other covariance-based processors are quoted relative to this number.

API reference
^^^^^^^^^^^^^

.. autoclass:: acconeer.exptool.a2.algo.heatmap.conventional.HeatmapProcessor
   :members:
   :undoc-members:

.. autoclass:: acconeer.exptool.a2.algo.heatmap.conventional.HeatmapConfig
   :members:
   :undoc-members:
