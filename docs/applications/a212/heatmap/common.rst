.. _a212_heatmap_common:

Shared Heatmap Configuration
============================

All four heatmap processors share two configuration bases: :class:`~acconeer.exptool.a2.algo.heatmap.config_common.HeatmapConfigCommon` holds the algorithmic parameters used by every processor, and :class:`~acconeer.exptool.a2.algo.heatmap.plot_config_common.HeatmapPlotConfig` holds the display-time parameters used by Exploration Tool when rendering the heatmap. Each processor adds a small number of extra fields specific to its algorithm, documented on the per-processor pages.

Heatmap Config Common
^^^^^^^^^^^^^^^^^^^^^

:attr:`~acconeer.exptool.a2.algo.heatmap.config_common.HeatmapConfigCommon.antenna_array`
    The antenna layout on the package. Utilized when calculating the :term:`steering vectors <Steering vector>` for the active channels.

:attr:`~acconeer.exptool.a2.algo.heatmap.config_common.HeatmapConfigCommon.az_angle_range` / :attr:`~acconeer.exptool.a2.algo.heatmap.config_common.HeatmapConfigCommon.el_angle_range`
    Angular range (in degrees) covered by the heatmap, given as ``(min, max)`` tuples.

:attr:`~acconeer.exptool.a2.algo.heatmap.config_common.HeatmapConfigCommon.num_az_angles` / :attr:`~acconeer.exptool.a2.algo.heatmap.config_common.HeatmapConfigCommon.num_el_angles`
    Number of grid points the corresponding angular range is divided into. Increasing the number of angles makes the heatmap grid finer but also increases the per-frame beamforming processing cost.

Heatmap Plot Config
^^^^^^^^^^^^^^^^^^^

The plot config carries display-time parameters that affect how the heatmap is rendered but do not change the underlying heatmap data. Variant-specific plot configs (for example :class:`~acconeer.exptool.a2.algo.heatmap.coherent.plot_config.CoherentHeatmapPlotConfig`) subclass this base.

:attr:`~acconeer.exptool.a2.algo.heatmap.plot_config_common.HeatmapPlotConfig.normalized_heat_cutoff`
    Threshold for "heat points", expressed as a fraction of the maximum heat in the current heatmap. A value of ``0.5`` discards points with less than 50 % of the maximum.

:attr:`~acconeer.exptool.a2.algo.heatmap.plot_config_common.HeatmapPlotConfig.max_2d_heat`
    Optional ceiling for the magnitude shown in the heatmap; values above this saturate. Leave as ``None`` to use auto-scaling.

:attr:`~acconeer.exptool.a2.algo.heatmap.plot_config_common.HeatmapPlotConfig.log_scale_output`
    If ``True``, the heatmap values are presented on a log scale. Useful when the dynamic range of the scene is wide.

API reference
^^^^^^^^^^^^^

.. autoclass:: acconeer.exptool.a2.algo.heatmap.config_common.HeatmapConfigCommon
   :members:
   :undoc-members:

.. autoclass:: acconeer.exptool.a2.algo.heatmap.plot_config_common.HeatmapPlotConfig
   :members:
   :undoc-members:
