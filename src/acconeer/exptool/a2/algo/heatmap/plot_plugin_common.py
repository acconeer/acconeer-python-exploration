# Copyright (c) Acconeer AB, 2023-2026
# All rights reserved

from __future__ import annotations

import copy
import logging
import os
import platform
import typing as t

import numpy as np
import numpy.typing as npt

from PySide6.QtCore import QSize
from PySide6.QtGui import QFont, QTransform
from PySide6.QtWidgets import QPushButton, QSizePolicy, QVBoxLayout

import pyqtgraph as pg
import pyqtgraph.opengl as gl

import acconeer.exptool as et
import acconeer.exptool.a2.algo._utils as algo_utils
from acconeer.exptool import a2
from acconeer.exptool.a2.algo.heatmap.backend_plugin_common import (
    BackendPlugin,
    HeatmapPlotOrientation,
    SharedState,
    TabState,
)
from acconeer.exptool.a2.algo.heatmap.cartesian_plot import CartesianHeatmapPlotWithGrid
from acconeer.exptool.a2.algo.heatmap.config_common import (
    HeatmapConfigCommon,
)
from acconeer.exptool.a2.algo.heatmap.gl_sensor_model import GLSensorModel
from acconeer.exptool.a2.algo.heatmap.gl_view_widget import GuardedGLViewWidget
from acconeer.exptool.a2.algo.heatmap.plot_config_common import HeatmapPlotConfig
from acconeer.exptool.a2.algo.heatmap.processor_common import (
    ProcessorResultCommon,
)
from acconeer.exptool.app.new import (
    AppModel,
    GeneralMessage,
    PlotPluginBase,
    backend,
)
from acconeer.exptool.app.new.ui import GroupBox, icons
from acconeer.exptool.app.new.ui.components import TabPGWidget


if platform.system() == "Windows":
    pg.setConfigOptions(useOpenGL=True)

log = logging.getLogger(__name__)

DEGREE_SYMBOL = "\u00b0"

SKIN = os.environ.get("ACC_SKIN", "none").lower()
TEXT_COLOR = "white" if SKIN == "tron" else "black"
BACKGROUND_COLOR = "black" if SKIN == "tron" else "white"

_ICON_SIZE = QSize(25, 25)
_BUTTON_SIZE = QSize(30, 30)

_A_SMALL_NUMBER = 1e-9


_HeatMapConfigT = t.TypeVar("_HeatMapConfigT", bound=HeatmapConfigCommon)
_PlotConfigT = t.TypeVar("_PlotConfigT", bound=HeatmapPlotConfig)


class PlotPlugin(PlotPluginBase, t.Generic[_HeatMapConfigT, _PlotConfigT]):
    INTERIM_AZ_START = -65
    INTERIM_AZ_SPAN = 130
    INTERIM_EL_START = -45
    INTERIM_EL_SPAN = 90

    def __init__(self, app_model: AppModel) -> None:
        super().__init__(app_model)
        self._plot_job: t.Optional[tuple[a2.GroupResult, ProcessorResultCommon]] = None
        self._config: t.Optional[a2.SessionConfig] = None
        # setup widget buttons
        self._rotate_button = QPushButton()
        self._rotate_button.setToolTip("Rotate plot counterclockwise")
        self._rotate_button.setIcon(icons.ROTATE())
        self._rotate_button.setFixedSize(_BUTTON_SIZE)
        self._rotate_button.setIconSize(_ICON_SIZE)
        self._rotate_button.clicked.connect(self._rotate_heatmap_plot)

        self._inv_x_button = QPushButton()
        self._inv_x_button.setToolTip("Mirror x-axis")
        self._inv_x_button.setIcon(icons.MIRROR())
        self._inv_x_button.setFixedSize(_BUTTON_SIZE)
        self._inv_x_button.setIconSize(_ICON_SIZE)
        self._inv_x_button.setFlat(True)
        self._inv_x_button.setCheckable(True)
        self._inv_x_button.clicked.connect(self._inv_x_heatmap_plot)

        self._inv_y_button = QPushButton()
        self._inv_y_button.setToolTip("Mirror y-axis")
        self._inv_y_button.setIcon(icons.MIRROR_90())
        self._inv_y_button.setFixedSize(_BUTTON_SIZE)
        self._inv_y_button.setIconSize(_ICON_SIZE)
        self._inv_y_button.setFlat(True)
        self._inv_y_button.setCheckable(True)
        self._inv_y_button.clicked.connect(self._inv_y_heatmap_plot)

        self.heatmap_plot_orientation: HeatmapPlotOrientation = HeatmapPlotOrientation(
            rotation=0, inv_x=False, inv_y=False
        )

        reset_orientation_button = QPushButton()
        reset_orientation_button.setToolTip("Reset plot orientation")
        reset_orientation_button.setIcon(icons.RESTORE(color=icons.TEXT_GREY))
        reset_orientation_button.setFixedSize(_BUTTON_SIZE)
        reset_orientation_button.setIconSize(_ICON_SIZE)
        reset_orientation_button.clicked.connect(self._reset_orientation)

        plot_button_group_box = GroupBox.horizontal("Plot orientation")
        plot_button_group_box.setMaximumWidth(200)
        plot_button_group_box.layout().addWidget(self._rotate_button)
        plot_button_group_box.layout().addWidget(self._inv_x_button)
        plot_button_group_box.layout().addWidget(self._inv_y_button)
        plot_button_group_box.layout().addWidget(reset_orientation_button)

        self.tab_widget = TabPGWidget(right_controls=plot_button_group_box)

        # 2D heatmap plot: polar
        self.polar_heatmap_image_item = pg.ImageItem()
        self.polar_heatmap_image_item.setLookupTable(et.utils.pg_mpl_cmap("viridis"))

        self.polar_heatmap_layout = pg.GraphicsLayoutWidget()

        self.polar_heatmap_plot_item = self.polar_heatmap_layout.addPlot(row=0, col=0)
        self.polar_heatmap_colorbar = self.polar_heatmap_plot_item.addColorBar(
            self.polar_heatmap_image_item, colorMap="viridis", interactive=False
        )

        self.polar_heatmap_colorbar.vb.setMouseEnabled(x=False, y=False)
        self.polar_heatmap_colorbar.vb.mouseDragEvent = lambda ev: None
        self.polar_heatmap_colorbar.vb.mouseClickEvent = lambda ev: None
        self.polar_heatmap_colorbar.vb.wheelEvent = lambda ev: None

        # Define axis scale behavior.
        axis = self.polar_heatmap_colorbar.axis
        axis.enableAutoSIPrefix(False)

        def sci_tick_strings(values: list[float], scale: float, spacing: float) -> list[str]:
            """
            Behavior for colorbar axis (which displays max value for the heatmap)
            """
            naive_strings = [f"{v:.2f}".rstrip("0").rstrip(".") for v in values]
            naive_lengths = np.max([len(s) for s in naive_strings])
            if naive_lengths > 7:
                disp_strings = [f"{v:.1e}" for v in values]
            else:
                disp_strings = naive_strings
            return disp_strings

        axis.tickStrings = sci_tick_strings
        font = QFont()
        font.setPixelSize(10)  # Hardcoded font size
        axis.setStyle(tickFont=font)

        self.polar_heatmap_plot_item.addItem(self.polar_heatmap_image_item)

        # 2D heatmap plot: cartesian
        self.cart_heatmap_plot = CartesianHeatmapPlotWithGrid()
        self.cart_heatmap_layout = pg.GraphicsLayoutWidget()

        self.cart_heatmap_plot_item = self.cart_heatmap_layout.addPlot(row=0, col=0)
        self.cart_heatmap_plot_item.setAspectLocked(True, ratio=1)
        self.cart_heatmap_colorbar = self.cart_heatmap_plot_item.addColorBar(
            self.cart_heatmap_plot, colorMap="viridis", interactive=False
        )

        self.cart_heatmap_colorbar.vb.setMouseEnabled(x=False, y=False)
        self.cart_heatmap_colorbar.vb.mouseDragEvent = lambda ev: None
        self.cart_heatmap_colorbar.vb.mouseClickEvent = lambda ev: None
        self.cart_heatmap_colorbar.vb.wheelEvent = lambda ev: None

        # Define axis scale behavior.
        axis = self.cart_heatmap_colorbar.axis
        axis.tickStrings = sci_tick_strings
        font = QFont()
        font.setPixelSize(10)  # Hardcoded font size
        axis.setStyle(tickFont=font)
        self.cart_heatmap_plot_item.addItem(self.cart_heatmap_plot)

        # 3D view plot
        self.heatmap_scatter_plot_item = gl.GLScatterPlotItem()
        self.heatmap_scatter_plot_item.setGLOptions("translucent")

        self.sensor_model = GLSensorModel()
        self.sensor_text_item = gl.GLTextItem(
            pos=np.zeros((3,)),
            color=TEXT_COLOR,
            text="Sensor",
            font=QFont("Helvetica", 7),  # default, but smaller
        )

        self.heatmap_gl_widget = GuardedGLViewWidget()
        self.heatmap_gl_widget.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self.heatmap_gl_widget.setBackgroundColor(BACKGROUND_COLOR)
        self.heatmap_gl_widget.addItem(self.heatmap_scatter_plot_item)
        for item in self.sensor_model.items:
            self.heatmap_gl_widget.addItem(item)
        self.axis_item = gl.GLAxisItem()
        self.axis_item.setSize(1, 1, 1)

        self.x_axis_text_item = gl.GLTextItem(
            pos=np.array([1, 0, 0]),
            text="+x",
            font=QFont("Helvetica", 7),  # default, but smaller
            color=TEXT_COLOR,
        )

        self.y_axis_text_item = gl.GLTextItem(
            pos=np.array([0, 1, 0]),
            text="+y",
            font=QFont("Helvetica", 7),  # default, but smaller
            color=TEXT_COLOR,
        )

        self.z_axis_text_item = gl.GLTextItem(
            pos=np.array([0, 0, 1]),
            text="+z",
            font=QFont("Helvetica", 7),  # default, but smaller
            color=TEXT_COLOR,
        )

        self.heatmap_gl_widget.addItem(self.axis_item)
        self.heatmap_gl_widget.addItem(self.x_axis_text_item)
        self.heatmap_gl_widget.addItem(self.y_axis_text_item)
        self.heatmap_gl_widget.addItem(self.z_axis_text_item)

        self.setup_spherical_coordinates(
            self.heatmap_gl_widget,
            self.INTERIM_AZ_START,
            self.INTERIM_AZ_SPAN,
            self.INTERIM_EL_START,
            self.INTERIM_EL_SPAN,
            min_range=0.5,
            max_range=1.0,
        )

        # add plots to tab widget
        self.tab_widget.newTab(
            self.cart_heatmap_layout,
            "2D Heatmap",
            lambda: BackendPlugin.update_tab_display.rpc(
                app_model.put_task, tab=TabState.HEATMAP_CARTESIAN
            ),
        )
        self.tab_widget.newTab(
            self.polar_heatmap_layout,
            "2D Heatmap Polar",
            lambda: BackendPlugin.update_tab_display.rpc(
                app_model.put_task, tab=TabState.HEATMAP_POLAR
            ),
        )
        self.tab_widget.newTab(
            self.heatmap_gl_widget,
            "3D view",
            lambda: BackendPlugin.update_tab_display.rpc(app_model.put_task, tab=TabState.ANGULAR),
        )

        self.tab_widget._button_group.idToggled.connect(
            lambda button_id, checked: plot_button_group_box.setEnabled(button_id <= 1 and checked)
        )

        layout = QVBoxLayout()
        layout.addWidget(self.tab_widget)
        self.setLayout(layout)

    def set_color_map(self, color_map_name: str) -> None:
        self.polar_heatmap_image_item.setLookupTable(et.utils.pg_mpl_cmap(color_map_name))
        self.polar_heatmap_colorbar.setColorMap(
            pg.colormap.get(color_map_name, source="matplotlib")
        )
        self.cart_heatmap_plot.setLookupTable(et.utils.pg_mpl_cmap(color_map_name))
        self.cart_heatmap_colorbar.setColorMap(
            pg.colormap.get(color_map_name, source="matplotlib")
        )

    @classmethod
    def setup_spherical_coordinates(
        cls,
        view_widget: gl.GLViewWidget,
        az_start_deg: float,
        az_span_deg: float,
        el_start_deg: float,
        el_span_deg: float,
        max_range: float,
        min_range: float,
        circle_arc_segments: int = 100,
    ) -> None:
        az_end_deg = az_start_deg + az_span_deg
        az_midpoint = (az_start_deg + az_end_deg) / 2.0
        el_end_deg = el_start_deg + el_span_deg
        degree = "\u00b0"

        line_color = (0.5, 0.5, 0.5, 0.75)

        for el_line_angle in [el_start_deg, el_end_deg]:
            for az_line_angle in [az_start_deg, az_end_deg, az_midpoint]:
                start_pos = np.array(
                    et.utils.spherical_to_cartesian(
                        min_range,
                        np.radians(az_line_angle),
                        np.radians(el_line_angle),
                    )
                )
                end_pos = np.array(
                    et.utils.spherical_to_cartesian(
                        max_range,
                        np.radians(az_line_angle),
                        np.radians(el_line_angle),
                    )
                )

                outgoing_line = gl.GLLinePlotItem(
                    pos=np.array([start_pos, end_pos]), color=line_color
                )
                outgoing_line.setGLOptions("opaque")
                view_widget.addItem(outgoing_line)

                view_widget.addItem(
                    gl.GLTextItem(
                        pos=1.1 * end_pos,
                        text=(
                            "az, el = "
                            + f"{az_line_angle:.2f}{degree}, {el_line_angle:.2f}{degree} "
                            + f"{max_range:.2f} m"
                        ),
                        font=QFont("Helvetica", 7),  # default, but smaller
                        color=TEXT_COLOR,
                    )
                )
                view_widget.addItem(
                    gl.GLTextItem(
                        pos=1.1 * start_pos,
                        text=f"{min_range:.2f} m",
                        font=QFont("Helvetica", 7),  # default, but smaller
                        color=TEXT_COLOR,
                    )
                )

        circle_arc_az_angles = np.linspace(
            np.radians(az_start_deg),
            np.radians(az_end_deg),
            num=circle_arc_segments,
            endpoint=True,
        ).reshape(-1, 1)
        az_start = np.full_like(circle_arc_az_angles, np.radians(az_start_deg))
        az_endb = np.full_like(circle_arc_az_angles, np.radians(az_end_deg))

        circle_arc_el_angles = np.linspace(
            np.radians(el_start_deg),
            np.radians(el_end_deg),
            num=circle_arc_segments,
            endpoint=True,
        ).reshape(-1, 1)
        el_start = np.full_like(circle_arc_el_angles, np.radians(el_start_deg))
        el_end = np.full_like(circle_arc_el_angles, np.radians(el_end_deg))

        circle_arcs_angles = np.block(
            [
                [circle_arc_az_angles, el_start],
                [az_endb, circle_arc_el_angles],
                [circle_arc_az_angles[::-1], el_end],
                [az_start, circle_arc_el_angles[::-1]],
            ]
        )

        circle_arc_points_end = np.zeros((len(circle_arcs_angles), 3))
        for idx, (az_angle, el_angle) in enumerate(circle_arcs_angles):
            circle_arc_points_end[idx, :] = et.utils.spherical_to_cartesian(
                max_range, az_angle, el_angle
            )

        circle_arc_points_start = np.zeros((len(circle_arcs_angles), 3))
        for idx, (az_angle, el_angle) in enumerate(circle_arcs_angles):
            circle_arc_points_start[idx, :] = et.utils.spherical_to_cartesian(
                min_range, az_angle, el_angle
            )

        circle_arc_points_az_zero = np.hstack(
            (np.zeros_like(circle_arc_el_angles), circle_arc_el_angles)
        )

        circle_arc_zero_start = np.zeros((len(circle_arc_points_az_zero), 3))
        circle_arc_zero_end = np.zeros((len(circle_arc_points_az_zero), 3))
        for idx, (az_angle, el_angle) in enumerate(circle_arc_points_az_zero):
            circle_arc_zero_start[idx, :] = et.utils.spherical_to_cartesian(
                min_range, az_angle, el_angle
            )
            circle_arc_zero_end[idx, :] = et.utils.spherical_to_cartesian(
                max_range, az_angle, el_angle
            )

        lines = [
            gl.GLLinePlotItem(pos=circle_arc_points_end, color=line_color),
            gl.GLLinePlotItem(pos=circle_arc_points_start, color=line_color),
            gl.GLLinePlotItem(pos=circle_arc_zero_end, color=line_color),
            gl.GLLinePlotItem(pos=circle_arc_zero_start, color=line_color),
        ]
        for line in lines:
            line.setGLOptions("opaque")
            view_widget.addItem(line)

    def on_backend_state_update(
        self, state: t.Optional[SharedState[_HeatMapConfigT, _PlotConfigT]]
    ) -> None:
        if state is None:
            return

        config_changed = (
            self._config != state.session_config or self.heatmap_config != state.heatmap_config
        )
        if config_changed:
            self._config = state.session_config
            self.heatmap_config: _HeatMapConfigT = state.heatmap_config
            self.cart_heatmap_plot.update_grid(
                state.session_config,
                state.heatmap_config.az_angles.tolist(),
                state.heatmap_config.az_angle_range,
            )
            self.cart_heatmap_plot_item.autoRange()

        (min_range, max_range) = algo_utils.get_measured_range(state.session_config)

        # 2D Heatmap plot stuff
        self.heatmap_2d_plot_smooth_max = et.utils.SmoothMax(
            state.session_config.update_rate, tau_decay=0.1, tau_grow=0.1
        )
        self.heatmap_2d_plot_smooth_negative_min = et.utils.SmoothMax(
            state.session_config.update_rate, tau_decay=0.1, tau_grow=0.1
        )

        # 2D polar Heatmap plot stuff
        self.polar_heatmap_plot_item.clear()
        self.polar_heatmap_plot_item.addItem(self.polar_heatmap_image_item)

        # 2D cartesian Heatmap plot stuff
        self.cart_heatmap_plot_item.clear()
        self.cart_heatmap_plot_item.addItem(self.cart_heatmap_plot)

        orientation_changed = self.heatmap_plot_orientation != state.heatmap_plot_orientation
        if orientation_changed:
            self.heatmap_plot_orientation = state.heatmap_plot_orientation
            self._inv_x_button.setChecked(self.heatmap_plot_orientation.inv_x)
            self._inv_y_button.setChecked(self.heatmap_plot_orientation.inv_y)
            self._rotate_button.setIcon(
                icons.ROTATE(rotated=-self.heatmap_plot_orientation.rotation)
            )
            self.cart_heatmap_plot.update_grid(
                state.session_config,
                state.heatmap_config.az_angles.tolist(),
                state.heatmap_config.az_angle_range,
            )
            self.cart_heatmap_plot_item.autoRange()

        if config_changed or orientation_changed:
            self._set_2d_transforms(self.heatmap_plot_orientation)

        # 3D view plot stuff
        self.heatmap_gl_widget.clear()
        self.heatmap_gl_widget.addItem(self.heatmap_scatter_plot_item)
        self.heatmap_gl_widget.addItem(self.axis_item)
        self.heatmap_gl_widget.addItem(self.x_axis_text_item)
        self.heatmap_gl_widget.addItem(self.y_axis_text_item)
        self.heatmap_gl_widget.addItem(self.z_axis_text_item)
        for item in self.sensor_model.items:
            self.heatmap_gl_widget.addItem(item)
        self.heatmap_gl_widget.addItem(self.sensor_text_item)
        self.setup_spherical_coordinates(
            self.heatmap_gl_widget,
            self.heatmap_config.az_start,
            self.heatmap_config.az_span,
            self.heatmap_config.el_start,
            self.heatmap_config.el_span,
            max_range=max_range,
            min_range=min_range,
        )

        self.normalized_heat_cutoff = state.plot_config.normalized_heat_cutoff

        self.max_2d_heat = state.plot_config.max_2d_heat

        self.log_scale_output = state.plot_config.log_scale_output

    def handle_message(self, message: GeneralMessage) -> None:
        if isinstance(message, backend.PlotMessage):
            self._plot_job = message.result
        else:
            raise NotImplementedError

    def draw(self) -> None:
        if self._plot_job is None:
            return

        assert self._config is not None

        (_, proc_result) = self._plot_job
        self._plot_job = None
        if proc_result.heatmap is not None:
            heatmap_to_draw = np.nan_to_num(proc_result.heatmap, nan=0.0, posinf=1e20, neginf=0.0)
            if not self.polar_heatmap_layout.isHidden():
                self._set_heatmap_2d_data(
                    heatmap_to_draw, plot_fn=self.polar_heatmap_image_item.updateImage
                )
            if not self.cart_heatmap_layout.isHidden():
                self._set_heatmap_2d_data(heatmap_to_draw, plot_fn=self.cart_heatmap_plot.setData)
            if not self.heatmap_gl_widget.isHidden():
                self._plot_angular_heatmap_data(
                    heatmap_to_draw, plot_fn=self.heatmap_scatter_plot_item.setData
                )

    def _set_heatmap_2d_data(
        self,
        heatmap_to_draw: npt.NDArray[np.float64],
        plot_fn: t.Callable[..., t.Any],
    ) -> None:
        if self._config is None:
            return

        heatmap = heatmap_to_draw
        mid_el_ind = self.heatmap_config.num_el_angles // 2
        only_mid_el = np.nan_to_num(heatmap[:, :, mid_el_ind].T, nan=0.0, posinf=1e20, neginf=0.0)
        if self.log_scale_output:
            # Add a small number to prevent log_10(0)=-inf
            only_mid_el = np.clip(only_mid_el, a_min=0.0, a_max=None)
            only_mid_el = 10 * np.log10(only_mid_el + _A_SMALL_NUMBER)

        if self.max_2d_heat is not None:
            max_heat = self.max_2d_heat
        else:
            max_heat_in_map = max(max(heats) for heats in only_mid_el)
            max_heat = self.heatmap_2d_plot_smooth_max.update(max_heat_in_map)

        # Handling for non-positive-valued heatmaps:
        # If we encouter a negative minimum value, assume the values can range
        # from [min, max] instead of [0, max].
        min_heat_in_map = only_mid_el.min()
        if min_heat_in_map < 0:
            if self.max_2d_heat is not None:
                min_heat = -self.max_2d_heat
            else:
                min_heat = -self.heatmap_2d_plot_smooth_negative_min.update(-min_heat_in_map)
        else:
            min_heat = 0

        self.polar_heatmap_colorbar.setLevels((min_heat, max_heat))
        self.cart_heatmap_colorbar.setLevels((min_heat, max_heat))

        image = copy.copy(only_mid_el)  # plot_fn will segfault unless we copy

        plot_fn(image, levels=(min_heat * 1.05, max_heat * 1.05))

    def _rotate_heatmap_plot(self) -> None:
        BackendPlugin.heatmap_plot_rotate.rpc(self.app_model.put_task)

    def _inv_x_heatmap_plot(self) -> None:
        BackendPlugin.heatmap_plot_invert_x.rpc(self.app_model.put_task)

    def _inv_y_heatmap_plot(self) -> None:
        BackendPlugin.heatmap_plot_invert_y.rpc(self.app_model.put_task)

    def _reset_orientation(self) -> None:
        BackendPlugin.heatmap_plot_reset.rpc(self.app_model.put_task)

    def _set_2d_transforms(self, heatmap_plot_orientation: HeatmapPlotOrientation) -> None:
        """
        Sets the heatmap image transform

        The controls in the GUI (modelled in HeatmapPlotOrientation) are "Rotate", "Invert-X", & "Invert-Y".
        Since rotations also invert axes (i.e. a rotation of 180deg will invert both the x- & y axis) it's easier
        to decompose the "Rotate" into "Swap-Axis", "Rotation-Inverts-X", & "Rotation-Inverts-Y" according to the
        table:

            ^                   rotation  = 0
            |
          r |                   swap axis = False
            |                   r. inv. x = False
            +---------->        r. inv. y = False
                 az


                       ^        rotation  = 90
                       |
                       | az     swap axis = True
                       |        r. inv. x = True
            <----------+        r. inv. y = False
                 r


                 az
            <----------+        rotation  = 180
                       |
                       | r      swap axis = False
                       |        r. inv. x = True
                       V        r. inv. y = True

                 r
            +---------->        rotation  = 270
            |
         az |                   swap axis = True
            |                   r. inv. x = False
            V                   r. inv. y = True

        Resulting in the transformation components
        "Swap-Axis", "Rotation-Inverts-X", "Rotation-Inverts-Y", "Invert-X", & "Invert-Y".

        Plotting an Image means that some of these aspects transformations are taken into
        account automatically with the data coordinates of the plots, but some are not taken into account
        and we have to manually compensate for those here.
        """
        assert self._config is not None

        start_point = self._config.sensor_config.subsweep.start_point
        step_length = self._config.sensor_config.subsweep.step_length
        num_points = self._config.sensor_config.subsweep.num_points
        num_az_angles = len(self.heatmap_config.az_angles)
        az_midpoint = (self.heatmap_config.az_start + self.heatmap_config.az_end) / 2.0
        az_span = self.heatmap_config.az_span

        self._setup_axis(heatmap_plot_orientation)

        start_point_m = start_point * algo_utils.BASE_STEP_LENGTH_M
        measure_span_m = ((num_points - 1) * step_length) * algo_utils.BASE_STEP_LENGTH_M

        axes_swapped = heatmap_plot_orientation.rotation in [90, 270]
        if axes_swapped:
            x_displacement = start_point_m
            x_scale = measure_span_m

            y_displacement = az_midpoint
            y_scale = az_span
        else:
            x_displacement = az_midpoint
            x_scale = az_span

            y_displacement = start_point_m
            y_scale = measure_span_m

        x_counter_inverted = heatmap_plot_orientation.rotation in [90, 180]
        y_counter_inverted = heatmap_plot_orientation.rotation in [180, 270]

        # polar transform
        polar_transform = (
            QTransform()
            # 7. displace image to fix offset
            .translate(x_displacement, y_displacement)
            # 6. rescale to align to axes (correct distances between distances and angles)
            .scale(x_scale, y_scale)
            # 5. move image so distance-axis occupies [0, 1] again
            #    (do this so next translate makes sense)
            .translate(
                0.5 if axes_swapped else 0.0,
                0.5 if not axes_swapped else 0.0,
            )
            # 4. counter axis inversion
            .scale(
                -1.0 if x_counter_inverted else 1.0,
                -1.0 if y_counter_inverted else 1.0,
            )
            # 3. rotate
            .rotate(heatmap_plot_orientation.rotation)
            # 2. center image on origo
            .translate(-0.5, -0.5)
            # 1. scale down for image to span from (0, 0) to (1, 1)
            .scale(1.0 / num_az_angles, 1.0 / num_points)
        )

        self.polar_heatmap_image_item.setTransform(polar_transform)

        # cartesian transform
        cart_transform = (
            QTransform()
            .scale(
                -1.0 if x_counter_inverted else 1.0,
                -1.0 if y_counter_inverted else 1.0,
            )
            .rotate(heatmap_plot_orientation.rotation)
        )
        self.cart_heatmap_plot.setTransform(cart_transform)
        self.cart_heatmap_plot_item.autoRange()

    def _setup_axis(self, heatmap_plot_orientation: HeatmapPlotOrientation) -> None:
        invert_x = False
        invert_y = False

        self.cart_heatmap_plot_item.getAxis("left").setLabel("Y", units="m")
        self.cart_heatmap_plot_item.getAxis("bottom").setLabel("X", units="m")
        if heatmap_plot_orientation.rotation % 180 == 0:
            self.polar_heatmap_plot_item.getAxis("left").setLabel("Distance", units="m")
            self.polar_heatmap_plot_item.getAxis("bottom").setLabel(
                "az angle", units=DEGREE_SYMBOL
            )

            if heatmap_plot_orientation.rotation == 180:
                invert_x = not heatmap_plot_orientation.inv_x
                invert_y = not heatmap_plot_orientation.inv_y
            else:  # heatmap_plot_orientation.rotation == 0
                invert_x = heatmap_plot_orientation.inv_x
                invert_y = heatmap_plot_orientation.inv_y

        else:
            self.polar_heatmap_plot_item.getAxis("bottom").setLabel("Distance", units="m")
            self.polar_heatmap_plot_item.getAxis("left").setLabel("az angle", units=DEGREE_SYMBOL)

            if heatmap_plot_orientation.rotation == 90:
                invert_x = not heatmap_plot_orientation.inv_x
                invert_y = heatmap_plot_orientation.inv_y
            else:  # heatmap_plot_orientation.rotation == 270
                invert_x = heatmap_plot_orientation.inv_x
                invert_y = not heatmap_plot_orientation.inv_y

        self.polar_heatmap_plot_item.invertX(b=invert_x)
        self.polar_heatmap_plot_item.invertY(b=invert_y)
        self.cart_heatmap_plot_item.invertX(b=invert_x)
        self.cart_heatmap_plot_item.invertY(b=invert_y)

    def _plot_angular_heatmap_data(
        self,
        heatmap_to_draw: npt.NDArray[np.float64],
        plot_fn: t.Callable[..., t.Any],
    ) -> None:
        if self.heatmap_gl_widget.isHidden():
            return

        if self._config is None:
            return

        max_heat = np.max(heatmap_to_draw)
        points = np.zeros((heatmap_to_draw.size, 4))
        num_valid_points = 0

        for i, az in enumerate(self.heatmap_config.az_angles):
            for j, el in enumerate(self.heatmap_config.el_angles):
                heats = heatmap_to_draw[:, i, j]
                normalized_heats = heats / max_heat

                for distance_idx, heat in enumerate(normalized_heats):
                    if heat < self.normalized_heat_cutoff:
                        continue

                    distance = (
                        self._config.sensor_config.subsweep.start_point
                        + distance_idx * self._config.sensor_config.subsweep.step_length
                    ) * algo_utils.BASE_STEP_LENGTH_M
                    x, y, z = et.utils.spherical_to_cartesian(
                        distance, np.radians(az), np.radians(el)
                    )
                    points[num_valid_points, 0] = x
                    points[num_valid_points, 1] = y
                    points[num_valid_points, 2] = z
                    points[num_valid_points, 3] = heat
                    num_valid_points += 1

        button_color = int(icons.BUTTON_ICON_COLOR[1:], base=16)
        button_red = button_color >> 16
        button_green = (button_color >> 8) & 0xFF
        button_blue = button_color & 0xFF
        color = (button_red / 255, button_green / 255, button_blue / 255)
        color_array = np.hstack(
            (
                np.broadcast_to(color, shape=(len(points), 3)),
                points[:, 3, np.newaxis] ** 2,
            )
        )
        plot_fn(
            pos=points[:num_valid_points, 0:3],
            color=color_array,
            size=10,
            pxMode=True,
        )
