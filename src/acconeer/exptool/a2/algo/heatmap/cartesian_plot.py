# Copyright (c) Acconeer AB, 2026
# All rights reserved

from __future__ import annotations

import typing as t

import numpy as np
import numpy.typing as npt

from PySide6.QtCore import QPointF, QRectF, Signal
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QPainter, QPicture
from PySide6.QtWidgets import QGraphicsItem

import pyqtgraph as pg

from acconeer.exptool import a2
from acconeer.exptool.a2.algo._utils import BASE_STEP_LENGTH_M
from acconeer.exptool.utils import spherical_to_cartesian


CART_AZ_LINES_INTERVAL = 15
NUM_CART_DISTANCE_LABELS = 9

BOUND_BOX_MARGIN_FACTOR = 0.2
MIN_BOUND_BOX_MARGIN = 0.05

# Grid labels are recorded into a QPicture at this em size and scaled by the painter at
# playback. Keep it a size FreeType can actually rasterize: a 1 px em combined with a large
# painter scale makes Qt request a degenerate glyph and crash in the FT rasterizer.
LABEL_FONT_PIXEL_SIZE = 64
# Skip labels whose em size in device pixels lands outside this range. Below the lower bound
# they are illegible; above it the glyph raster overflows.
MIN_LABEL_DEVICE_EM = 1.0
MAX_LABEL_DEVICE_EM = 512.0


class CartesianHeatmapPlot(pg.GraphicsObject):
    """Heatmap data rendered via PColorMeshItem in polar-to-Cartesian coordinates."""

    sigLevelsChanged = Signal(tuple)
    sigImageChanged = Signal()

    def __init__(self) -> None:
        super().__init__()
        self._levels = (0.0, 1.0)
        self._bounding_rect = QRectF()
        self._x_corners: t.Optional[npt.NDArray[np.float64]] = None
        self._y_corners: t.Optional[npt.NDArray[np.float64]] = None
        self.az_angles: list[float] = []
        self.distances_m: list[float] = []
        self.session_config: t.Optional[a2.SessionConfig] = None
        self._az_angle_range: tuple[float, float] = (0.0, 0.0)
        self._mesh = pg.PColorMeshItem(enableAutoLevels=False)
        self._mesh.setParentItem(self)
        self._mesh.setVisible(False)

    def getLevels(self) -> tuple[float, float]:
        # duck-typing method to allow attaching a pyqtgraph.graphicsItems.ColorBarItem
        return self._levels

    def setLevels(self, levels: tuple[float, float]) -> None:
        # duck-typing method to allow attaching a pyqtgraph.graphicsItems.ColorBarItem
        if self._levels == levels:
            return
        self._levels = levels
        self._mesh.setLevels(levels)
        self.sigLevelsChanged.emit(self._levels)

    def getColorMap(self) -> t.Any:
        # duck-typing method to allow attaching a pyqtgraph.graphicsItems.ColorBarItem
        return getattr(self, "_pg_colormap", None)

    def setColorMap(self, colorMap: t.Any) -> None:
        # duck-typing method to allow attaching a pyqtgraph.graphicsItems.ColorBarItem
        self._pg_colormap = colorMap
        self._mesh.setColorMap(colorMap)

    def setLookupTable(self, lut: npt.NDArray[np.uint8]) -> None:
        self._mesh.setLookupTable([QColor(int(r), int(g), int(b), int(a)) for r, g, b, a in lut])

    def paint(self, p: QPainter, *args: t.Any) -> None:
        # QGraphicsItem.paint() is pure virtual in C++; PySide6 requires a concrete
        # implementation even when there is nothing to draw. Rendering is done by
        # the _mesh child item, which Qt paints independently.
        pass

    def boundingRect(self) -> QRectF:
        return self._bounding_rect

    def setData(
        self,
        image: npt.NDArray[np.float64],
        levels: tuple[float, float],
    ) -> None:
        if self._levels != levels:
            self._levels = levels
            self._mesh.setLevels(levels)
            self.sigLevelsChanged.emit(self._levels)
        self.sigImageChanged.emit()
        local_image = np.nan_to_num(image, nan=0.0, posinf=1e20, neginf=0.0)
        if self._x_corners is not None and self._y_corners is not None:
            self._mesh.setVisible(True)
            self._mesh.setData(self._x_corners, self._y_corners, local_image)
        self.update()

    def clearData(self) -> None:
        self._mesh.setVisible(False)
        self.update()

    def extrapolate_az(self) -> t.Any:  # TODO: don't t.Any this
        if len(self.az_angles) >= 2:
            return [self.az_angles[0]] + self.az_angles + [self.az_angles[-1]]
        # Special case of single az angle. Multiply with 2 to get correct interpolation value in later step
        return [self._az_angle_range[0] * 2] + self.az_angles + [self._az_angle_range[1] * 2]

    def extrapolate_d(self) -> t.Any:  # TODO: don't t.Any this
        if len(self.distances_m) >= 2:
            (first, second) = self.distances_m[:2]
            (penultimate, ultimate) = self.distances_m[-2:]
            return (
                [first - (second - first)]
                + self.distances_m
                + [ultimate + (ultimate - penultimate)]
            )
        if self.session_config is None:
            msg = "update_grid() must be called before rendering"
            raise RuntimeError(msg)
        return (
            [
                -self.session_config.sensor_config.subsweep.step_length * BASE_STEP_LENGTH_M / 2
                + self.distances_m[0]
            ]
            + self.distances_m
            + [
                self.session_config.sensor_config.subsweep.step_length * BASE_STEP_LENGTH_M / 2
                + self.distances_m[0]
            ]
        )

    def update_grid(
        self,
        session_config: a2.SessionConfig,
        az_angles: list[float],
        az_angle_range: tuple[float, float],
    ) -> None:
        self.prepareGeometryChange()
        self.session_config = session_config
        self._az_angle_range = az_angle_range
        self.az_angles = list(az_angles)

        distances_p: list[int] = []
        for subsweep in session_config.sensor_config.subsweeps:
            distances_p.extend(
                subsweep.start_point + np.arange(0, subsweep.num_points) * subsweep.step_length
            )
        self.distances_m = (BASE_STEP_LENGTH_M * np.array(distances_p)).tolist()

        extrapolated_az = self.extrapolate_az()
        extrapolated_d = self.extrapolate_d()

        az_arr = np.array(extrapolated_az)
        left_az_angles = (az_arr[1:-1] + az_arr[:-2]) / 2
        right_az_angles = (az_arr[1:-1] + az_arr[2:]) / 2

        d_arr = np.array(extrapolated_d)
        btm_distances_m = (d_arr[1:-1] + d_arr[:-2]) / 2
        top_distances_m = (d_arr[1:-1] + d_arr[2:]) / 2

        az_bounds = np.concatenate([[left_az_angles[0]], right_az_angles])
        d_bounds = np.concatenate([[btm_distances_m[0]], top_distances_m])
        # At el=0, (x, y) = (d·sin(az), d·cos(az)). Broadcasting az over rows
        # and d over columns gives the per-corner (x, y) grids directly.
        az_rad = (az_bounds * np.pi / 180)[:, None]
        d_grid = d_bounds[None, :]
        el_zero = np.zeros_like(az_rad)
        x_corners, y_corners, _ = spherical_to_cartesian(d_grid, az_rad, el_zero)

        num_az = len(self.az_angles)
        num_dist = len(distances_p)

        self._x_corners = x_corners
        self._y_corners = y_corners

        self._mesh.setVisible(False)
        self._mesh.setData(x_corners, y_corners, np.zeros((num_az, num_dist)))
        self._mesh.setLevels(self._levels)

        min_x, max_x = float(np.min(x_corners)), float(np.max(x_corners))
        min_y, max_y = float(np.min(y_corners)), float(np.max(y_corners))
        margin_x = max(MIN_BOUND_BOX_MARGIN, (max_x - min_x) * BOUND_BOX_MARGIN_FACTOR)
        margin_y = max(MIN_BOUND_BOX_MARGIN, (max_y - min_y) * BOUND_BOX_MARGIN_FACTOR)
        self._bounding_rect = QRectF(
            min_x - margin_x,
            min_y - margin_y,
            (max_x - min_x) + 2 * margin_x,
            (max_y - min_y) + 2 * margin_y,
        )

        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemHasNoContents, False)
        self.update()


class CartesianHeatmapPlotWithGrid(pg.GraphicsObject):
    """CartesianHeatmapPlot with polar grid lines and labels rendered on top."""

    sigLevelsChanged = Signal(tuple)
    sigImageChanged = Signal()

    def __init__(self) -> None:
        super().__init__()
        self._plot = CartesianHeatmapPlot()
        self._plot.setParentItem(self)
        self._plot.setFlag(QGraphicsItem.GraphicsItemFlag.ItemStacksBehindParent, True)
        self._plot.sigLevelsChanged.connect(self.sigLevelsChanged)
        self._plot.sigImageChanged.connect(self.sigImageChanged)
        self._grid_picture = QPicture()
        self._grid_dirty = True
        self.az_angles: list[float] = []
        self.distances_m: list[float] = []
        self._az_angle_range: tuple[float, float] = (0.0, 0.0)

    def getLevels(self) -> tuple[float, float]:
        # duck-typing method to allow attaching a pyqtgraph.graphicsItems.ColorBarItem
        return self._plot.getLevels()

    def setLevels(self, levels: tuple[float, float]) -> None:
        # duck-typing method to allow attaching a pyqtgraph.graphicsItems.ColorBarItem
        self._plot.setLevels(levels)

    def getColorMap(self) -> t.Any:
        # duck-typing method to allow attaching a pyqtgraph.graphicsItems.ColorBarItem
        return self._plot.getColorMap()

    def setColorMap(self, colorMap: t.Any) -> None:
        # duck-typing method to allow attaching a pyqtgraph.graphicsItems.ColorBarItem
        self._plot.setColorMap(colorMap)

    def setLookupTable(self, lut: npt.NDArray[np.uint8]) -> None:
        self._plot.setLookupTable(lut)

    def paint(self, p: QPainter, *args: t.Any) -> None:
        # Qt can paint before update_grid(), and an exception escaping paint() can crash PySide.
        if not self.az_angles:
            return
        if self._grid_dirty:
            self._rebuild_grid_picture(p)
        p.drawPicture(0, 0, self._grid_picture)

    def boundingRect(self) -> QRectF:
        return self._plot.boundingRect()

    def setData(
        self,
        image: npt.NDArray[np.float64],
        levels: tuple[float, float],
    ) -> None:
        self._plot.setData(image, levels)

    def clearData(self) -> None:
        self._plot.clearData()

    def update_grid(
        self,
        session_config: a2.SessionConfig,
        az_angles: list[float],
        az_angle_range: tuple[float, float],
    ) -> None:
        self.prepareGeometryChange()
        self._plot.update_grid(session_config, az_angles, az_angle_range)
        self.az_angles = self._plot.az_angles
        self.distances_m = self._plot.distances_m
        self._az_angle_range = az_angle_range
        self._grid_dirty = True
        self.update()

    def _rebuild_grid_picture(self, p_global: QPainter) -> None:
        # Create local painter for cached grid picture. QPainter's context-manager
        # protocol calls end() on exit (including on exception), so the picture's
        # recording is always closed before paint() replays it.
        with QPainter(self._grid_picture) as p:
            # Get current global transform for zoom-aware rendering and grid label rotation.
            # The global anti-rotation and anti-mirroring is only applied to the labels so that when
            # the global transform is later applied to the grid the label text appear in a reasonable
            # orientation and scale. This allows the use of QTransform as normal on the heatmap class
            # while preserving nice looking grid labels.
            transform = p_global.transform()
            m11 = transform.m11()
            m12 = transform.m12()
            m21 = transform.m21()
            m22 = transform.m22()

            scale_x = np.sqrt(m11**2 + m12**2)
            scale_y = np.sqrt(m21**2 + m22**2)
            determinant = (m11 * m22) - (m12 * m21)
            current_rotation = -np.rad2deg(np.atan2(m12, m11))
            if determinant > 0:  # if mirroring occurred correct scaling
                if current_rotation in [180, -180, 0]:
                    scale_y = -scale_y
                else:
                    scale_x = -scale_x
            # If rotation is in upper two quantiles text should be in one way. The opposite in the two lower.
            if current_rotation in [0, 90]:
                scale_y = -scale_y
                scale_x = scale_x
            else:
                scale_y = scale_y
                scale_x = -scale_x

            scale = np.sqrt(scale_y**2 + scale_x**2)

            # np.sign() yields 0.0 when a component is exactly zero, which would make the label
            # transform below singular. Snap to +-1 instead.
            mirror_x = -1.0 if scale_x < 0 else 1.0
            mirror_y = -1.0 if scale_y < 0 else 1.0

            # Set font. Scaled later
            font = QFont()
            font.setPixelSize(LABEL_FONT_PIXEL_SIZE)
            metrics = QFontMetricsF(font)
            p.setFont(font)

            # construct az grid
            extrapolated_az_angles = self._plot.extrapolate_az()
            az_angles = np.array(extrapolated_az_angles)
            right_az_angles = (az_angles[1:-1] + az_angles[2:]) / 2
            outer_angle_deg = right_az_angles[-1]
            angle_rad = np.radians(outer_angle_deg)
            # Radial direction at az θ is (sin θ, cos θ).
            cos_a, sin_a = np.cos(angle_rad), np.sin(angle_rad)

            # construct distance grid
            extrap_dist = np.array(self._plot.extrapolate_d())
            tick_distances = (extrap_dist[1:] + extrap_dist[:-1]) / 2

            sparse_indx_jump = 1
            if len(tick_distances) > NUM_CART_DISTANCE_LABELS:
                sparse_indx_jump = int(np.floor(len(tick_distances) / NUM_CART_DISTANCE_LABELS))
            sparse_tick_distances = tick_distances[0:-1:sparse_indx_jump]
            step_len = tick_distances[1] - tick_distances[0]
            label_height = metrics.height()
            font_scale = step_len * sparse_indx_jump / label_height

            # Em size the FreeType rasterizer is asked for when paint() replays the picture.
            # Out of range it either renders illegibly small or overflows the glyph raster.
            label_device_em = abs(LABEL_FONT_PIXEL_SIZE * font_scale * scale)
            draw_labels = MIN_LABEL_DEVICE_EM < label_device_em < MAX_LABEL_DEVICE_EM

            # initiate pen
            pen = pg.mkPen(cosmetic=False, width=step_len * 0.1, color="black")
            p.setPen(pen)

            # paint distance grid arc lines
            if self._plot._x_corners is not None and self._plot._y_corners is not None:
                for x_col, y_col in zip(self._plot._x_corners.T, self._plot._y_corners.T):
                    for i in range(len(x_col) - 1):
                        p.drawLine(
                            QPointF(float(x_col[i]), float(y_col[i])),
                            QPointF(float(x_col[i + 1]), float(y_col[i + 1])),
                        )

            # paint distance grid ticks and labels
            for dist in sparse_tick_distances:
                # Scene position of the tick: (d·sin(az), d·cos(az)).
                x = dist * sin_a
                y = dist * cos_a

                # Draw radial tick
                tick_len = 10.0 / scale  # length in scene units

                # CCW perpendicular to the radial direction (sin_a, cos_a).
                nx = -cos_a
                ny = sin_a

                tick_dx = (tick_len / 2) * nx
                tick_dy = (tick_len / 2) * ny

                tick_start = QPointF(x - tick_dx, y - tick_dy)
                tick_end = QPointF(x + tick_dx, y + tick_dy)
                p.drawLine(tick_start, tick_end)

                if not draw_labels:
                    continue

                angle_deg = -outer_angle_deg + 180

                # Draw rotated text
                max_dist = np.max(np.abs(tick_distances))
                if max_dist > 1.0:
                    dec_num = int(np.ceil(-np.log10(step_len)))
                    dec_num = max(dec_num, 0)
                    label = f"{dist:.{dec_num}f}m"
                else:
                    label = f"{dist * 1000:.0f}mm"

                label_width = metrics.horizontalAdvance(label)
                dx = (-tick_len - label_width / 2 * font_scale) * cos_a
                dy = (tick_len + label_width / 2 * font_scale) * sin_a
                label_pos = QPointF(x - dx, y - dy)

                p.save()
                p.translate(label_pos)
                p.scale(font_scale, font_scale)
                p.rotate(angle_deg)
                p.translate(QPointF(-mirror_x * -label_width / 2, mirror_y * -label_height / 4))
                p.scale(-mirror_x, -mirror_y)
                p.drawText(QPointF(0.0, 0.0), label)
                p.restore()

            # paint az lines and labels
            az_min = np.min(self._az_angle_range)
            az_max = np.max(self._az_angle_range)
            maximal_az_lines = np.arange(-90, 90, CART_AZ_LINES_INTERVAL)
            az_lines = [float(np.min(self.az_angles))]
            for candidate_az in maximal_az_lines:
                if az_min <= candidate_az <= az_max:
                    az_lines.append(float(candidate_az))
            az_lines.append(float(np.max(self.az_angles)))
            for az in az_lines:
                start_r = tick_distances[0]
                tick_len = 10.0 / scale  # length in scene units
                end_r = tick_distances[-1] + tick_len

                # az direction is (sin az, cos az).
                cos_a = np.cos(np.deg2rad(az))
                sin_a = np.sin(np.deg2rad(az))

                tick_start = QPointF(start_r * sin_a, start_r * cos_a)
                tick_end = QPointF(end_r * sin_a, end_r * cos_a)
                p.drawLine(tick_start, tick_end)

                if not draw_labels:
                    continue

                label = f"{az:.1f}°"
                p.save()
                label_width = metrics.horizontalAdvance(label)
                label_pos = QPointF(
                    (end_r + label_width * font_scale) * sin_a,
                    (end_r + label_width * font_scale) * cos_a,
                )
                p.translate(label_pos)
                p.scale(font_scale, font_scale)
                p.rotate(90 - az)
                p.translate(QPointF(-mirror_x * -label_width / 2, mirror_y * -label_height / 2))
                p.scale(-mirror_x, -mirror_y)
                p.drawText(QPointF(0.0, 0.0), label)
                p.restore()

        self._grid_dirty = False
