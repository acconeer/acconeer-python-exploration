.. _a212_heatmap_coherent:

Coherent Heatmap Processor
==========================

Introduction
^^^^^^^^^^^^

The coherent heatmap processor implements the classic delay-and-sum beamformer directly on the per-channel data. For each point on the ``(distance, azimuth, elevation)`` grid it computes a single complex value — the sum of the channel signals phase-aligned to that direction. The magnitude or phase of that complex value forms the heatmap that is displayed in ET; the underlying complex array is also exposed in :class:`~acconeer.exptool.a2.algo.heatmap.coherent.ProcessorResult`.

Unlike the three covariance-based processors — :doc:`Conventional <conventional>`, :doc:`Capon <capon>`, and :doc:`Robust Capon <robust_capon>` — the coherent processor does not estimate a channel covariance matrix and does not invert one. This makes it the cheapest option and the only one that preserves the phase information. Conventional beamforming is equivalent to the coherent beamforming with averaging of heatmaps over time. The difference is that conventional beamforming achieves higher numerical efficiency by averaging at the covariance level when done over many snapshots.

Typical use case
^^^^^^^^^^^^^^^^

* Pipelines downstream of the heatmap that need the complex output — for example, micro-Doppler or phase-tracking applications, such as vital sign applications.

Pros and cons
^^^^^^^^^^^^^

**Pros**

* Cheapest of the four processors; no covariance, no matrix inverse. But it is often used in phase-tracking applications where a higher heatmap update rate is desirable.
* Can image static scenes — unlike Capon it handles correlated sources.
* Provides complex output, which retains phase information.
* No covariance smoothing — responsive to fast scene changes.

**Cons**

* Angular resolution is limited by the array aperture. :term:`FWHM` :math:`\approx 10.2 ^\circ` at boresight; broadens off-boresight as the effective aperture scales with :math:`\cos\theta`.
* High side lobe levels; side lobes leak energy from strong reflectors into other directions.
* No averaging over time — higher spectrum variance.

Math and theory
^^^^^^^^^^^^^^^

Let :math:`\mathbf{x} \in \mathbb{C}^{N_{ch}}` be the channel data at a given range bin (after the optional high-pass filter, taken from the time-averaged sweep) and :math:`\mathbf{a}(\theta, \phi) \in \mathbb{C}^{N_{ch}}` the :term:`steering vector <Steering vector>` for direction :math:`(\theta, \phi)`. The delay-and-sum output is

.. math::

   y(\theta, \phi) = \mathbf{a}(\theta, \phi)^H \mathbf{x}.

The processor produces the complex array :math:`y(\theta, \phi)` for every range bin (the :attr:`~acconeer.exptool.a2.algo.heatmap.coherent.ProcessorResult.heatmap_coherent` output) and a real heatmap selected from it by :attr:`~acconeer.exptool.a2.algo.heatmap.coherent.plot_config.CoherentHeatmapPlotConfig.display_mode`: either :math:`|y|` (:attr:`~acconeer.exptool.a2.algo.heatmap.coherent.plot_config.CoherentHeatmapPlotConfig.DisplayMode.ABSOLUTE`) or :math:`\arg(y)` (:attr:`~acconeer.exptool.a2.algo.heatmap.coherent.plot_config.CoherentHeatmapPlotConfig.DisplayMode.ANGLE`).

Example spectrum plots
^^^^^^^^^^^^^^^^^^^^^^

As seen in :numref:`a212_heatmap_fig_coherent`, the sidelobes of the actual targets can mask other weaker reflectors. A peak-finding algorithm would not be able to find the three positions. The beamforming method can, however, still be used for amplitude estimation and phase extraction applications.

.. figure:: /images/processing/a212_heatmap_processing/figures/heatmap_coherent.png
    :name: a212_heatmap_fig_coherent
    :align: center

    Coherent D–Az heatmap on a recording of three corner reflectors, plotted as :math:`|y|`. The three colored markers and dashed lines mark the true reflector locations. The 1D plots show the distance and azimuth spectra cut at each of the three true peak locations. Recorded using :term:`Profile` 3.

.. figure:: /images/processing/a212_heatmap_processing/figures/el_spectrum_coherent.png
    :align: center

    Elevation spectrum of the coherent heatmap at each of the three true peak locations. Recorded using :term:`Profile` 3.

Configuration
^^^^^^^^^^^^^

Shared parameters are documented in :doc:`common`. Processor-specific fields:

:attr:`~acconeer.exptool.a2.algo.heatmap.coherent.HeatmapConfig.heatmap_mode`
    :attr:`~acconeer.exptool.a2.algo.heatmap.coherent.HeatmapConfig.HeatmapMode.MOVEMENT` enables a per-channel high-pass filter that suppresses the static scene; :attr:`~acconeer.exptool.a2.algo.heatmap.coherent.HeatmapConfig.HeatmapMode.DISTANCE` skips the filter and shows the full reflected energy.

:attr:`~acconeer.exptool.a2.algo.heatmap.coherent.HeatmapConfig.high_pass_filter_time_constant_s`
    Time constant of the high-pass filter when :attr:`~acconeer.exptool.a2.algo.heatmap.coherent.HeatmapConfig.heatmap_mode` is :attr:`~acconeer.exptool.a2.algo.heatmap.coherent.HeatmapConfig.HeatmapMode.MOVEMENT`. Ignored otherwise.

:attr:`~acconeer.exptool.a2.algo.heatmap.coherent.plot_config.CoherentHeatmapPlotConfig.display_mode`
    Lives on :class:`~acconeer.exptool.a2.algo.heatmap.coherent.plot_config.CoherentHeatmapPlotConfig` (see also the shared :doc:`common` page). Selects what the real ``heatmap`` output contains: :attr:`~acconeer.exptool.a2.algo.heatmap.coherent.plot_config.CoherentHeatmapPlotConfig.DisplayMode.ABSOLUTE` for the magnitude of the complex beamformer output, :attr:`~acconeer.exptool.a2.algo.heatmap.coherent.plot_config.CoherentHeatmapPlotConfig.DisplayMode.ANGLE` for its phase. The full complex array is always exposed separately as :attr:`~acconeer.exptool.a2.algo.heatmap.coherent.ProcessorResult.heatmap_coherent`.

Typical processing cost
^^^^^^^^^^^^^^^^^^^^^^^

Per frame the processing is dominated by the beamforming step itself, :math:`\mathcal{O}(N_d \cdot N_{ch} \cdot N_{az} \cdot N_{el})` complex multiplications and additions. No covariance matrix is calculated or inverted. This is the cheapest of the four processors. On the configuration the RSS computation time test measures, 12 virtual channels and 25 azimuth angles, it is **0.16 ×** the per-frame cost of Conventional.

On the other hand, using the coherent beamformer often implies a higher :attr:`~acconeer.exptool.a2.SensorConfig.sweeps_per_frame` or :attr:`~acconeer.exptool.a2.SessionConfig.update_rate` in order to observe phase changes over time, which adds to the total processing cost per second.

API reference
^^^^^^^^^^^^^

.. autoclass:: acconeer.exptool.a2.algo.heatmap.coherent.HeatmapProcessor
   :members:
   :undoc-members:

.. autoclass:: acconeer.exptool.a2.algo.heatmap.coherent.HeatmapConfig
   :members:
   :undoc-members:

.. autoclass:: acconeer.exptool.a2.algo.heatmap.coherent.plot_config.CoherentHeatmapPlotConfig
   :members:
   :undoc-members:

.. autoclass:: acconeer.exptool.a2.algo.heatmap.coherent.ProcessorResult
   :members:
   :undoc-members:
