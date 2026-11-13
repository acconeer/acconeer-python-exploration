# Copyright (c) Acconeer AB, 2026
# All rights reserved

from __future__ import annotations

import math

import numpy as np

from PySide6 import QtCore, QtGui

from acconeer.exptool.a2.algo._detection_geometry import SensorInstallation
from acconeer.exptool.a2.algo.heatmap import gl_sensor_model as sensor_model
from acconeer.exptool.app.new.ui import palette


# Large enough to stay sharp when Qt scales the icons down.
_PX_PER_ICON_PX = 6
_WALL_INSET_PX = 12
_WALL_WIDTH_PX = 8
_SENSOR_WIDTH_PX = 24
_SENSOR_DEPTH_PX = 10
# Pulls a sensor in a corner clear of both walls.
_SENSOR_OFFSET_PX = 14
_BEAM_HALF_ANGLE_DEG = 30.0
# Opacity of the beam, in the sensor's color.
_BEAM_ALPHA = 89
# The Custom pan picture's sensor, turned a little to its left, and the
# double-headed arc around it, level, from 45 to 135 degrees
# counterclockwise from the picture's right.
_CUSTOM_PAN_DEG = 20.0
_ARC_RADIUS_PX = 69
_ARC_START_DEG = 45.0
_ARC_END_DEG = 135.0
_ARC_WIDTH_PX = 9
_ARROWHEAD_PX = 30
# Large enough to stay sharp when Qt scales the sensor's icon down.
_SENSOR_PX_PER_M = 1600.0


def _boresight(installation: SensorInstallation) -> tuple[float, float, float]:
    x, y, z = installation.sensor_to_world(np.array([0.0, 1.0, 0.0]))
    return float(x), float(y), float(z)


def _draw_room(
    pixmap: QtGui.QPixmap,
    room: QtCore.QRectF,
    walls: QtGui.QPolygonF,
    sensor_center: QtCore.QPointF,
    boresight_deg: float,
) -> None:
    """Draws the floor ``room``, the sensor's beam within it, the ``walls``
    and the sensor at ``sensor_center``, facing ``boresight_deg``
    counterclockwise from the picture's right."""
    colors = palette.current()
    painter = QtGui.QPainter(pixmap)
    painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)

    painter.setPen(QtCore.Qt.PenStyle.NoPen)
    painter.setBrush(colors.picture_floor.qcolor())
    painter.drawRect(room)

    painter.save()
    painter.setClipRect(room)
    painter.setBrush(colors.sensor_body.with_alpha(_BEAM_ALPHA).qcolor())
    beam_radius_px = 2 * max(pixmap.width(), pixmap.height())
    # drawPie takes 1/16 degrees, counterclockwise from 3 o'clock on screen.
    painter.drawPie(
        QtCore.QRectF(
            sensor_center.x() - beam_radius_px,
            sensor_center.y() - beam_radius_px,
            2 * beam_radius_px,
            2 * beam_radius_px,
        ),
        round(16 * (boresight_deg - _BEAM_HALF_ANGLE_DEG)),
        round(16 * 2 * _BEAM_HALF_ANGLE_DEG),
    )
    painter.restore()

    painter.setPen(QtGui.QPen(colors.picture_wall.qcolor(), _WALL_WIDTH_PX))
    painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
    painter.drawPolyline(walls)

    painter.setPen(QtCore.Qt.PenStyle.NoPen)
    painter.setBrush(colors.sensor_body.qcolor())
    painter.translate(sensor_center)
    # Unrotated, the sensor faces up; positive QPainter rotation is clockwise.
    painter.rotate(90.0 - boresight_deg)
    painter.drawRect(
        QtCore.QRectF(
            -_SENSOR_WIDTH_PX / 2, -_SENSOR_DEPTH_PX / 2, _SENSOR_WIDTH_PX, _SENSOR_DEPTH_PX
        )
    )
    painter.end()


def room_top_view_icon(z_rotation: float) -> QtGui.QIcon:
    """A square room seen from above, the sensor on its near wall panned by
    ``z_rotation`` degrees, with a beam along its boresight. The sensor sits
    in the middle of the wall if it faces straight in, else in the corner it
    faces away from. Needs a ``QApplication``."""
    pixmap, _ = _room_top_view(z_rotation, in_corner=True)
    return QtGui.QIcon(pixmap)


def custom_pan_icon() -> QtGui.QIcon:
    """:func:`room_top_view_icon` for a pan of any angle: the sensor in the
    middle of the wall, turned a little to its left, with a double-headed arc
    around it. Needs a ``QApplication``."""
    pixmap, sensor_center = _room_top_view(_CUSTOM_PAN_DEG, in_corner=False)
    colors = palette.current()
    painter = QtGui.QPainter(pixmap)
    painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)

    pen = QtGui.QPen(colors.picture_wall.qcolor(), _ARC_WIDTH_PX)
    # Ends square where the heads start, so that it does not blunt them.
    pen.setCapStyle(QtCore.Qt.PenCapStyle.FlatCap)
    painter.setPen(pen)
    painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
    r = _ARC_RADIUS_PX
    # drawArc takes 1/16 degrees, counterclockwise from 3 o'clock on screen.
    painter.drawArc(
        QtCore.QRectF(sensor_center.x() - r, sensor_center.y() - r, 2 * r, 2 * r),
        round(16 * _ARC_START_DEG),
        round(16 * (_ARC_END_DEG - _ARC_START_DEG)),
    )

    painter.setPen(QtCore.Qt.PenStyle.NoPen)
    painter.setBrush(colors.picture_wall.qcolor())
    # Each head points on along the arc, past its end.
    for end_deg, onward in ((_ARC_START_DEG, -1.0), (_ARC_END_DEG, 1.0)):
        end = math.radians(end_deg)
        # The arc's end, and the way on along it; the picture's y points down.
        base_x = sensor_center.x() + r * math.cos(end)
        base_y = sensor_center.y() - r * math.sin(end)
        along_x, along_y = -onward * math.sin(end), -onward * math.cos(end)
        half = _ARROWHEAD_PX / 2
        painter.drawPolygon(
            QtGui.QPolygonF(
                [
                    QtCore.QPointF(
                        base_x + _ARROWHEAD_PX * along_x, base_y + _ARROWHEAD_PX * along_y
                    ),
                    QtCore.QPointF(base_x - half * along_y, base_y + half * along_x),
                    QtCore.QPointF(base_x + half * along_y, base_y - half * along_x),
                ]
            )
        )
    painter.end()
    return QtGui.QIcon(pixmap)


def _room_top_view(z_rotation: float, *, in_corner: bool) -> tuple[QtGui.QPixmap, QtCore.QPointF]:
    """The picture of :func:`room_top_view_icon`, the sensor in a corner only
    if ``in_corner``, and where the sensor is in it."""
    size_px = 32 * _PX_PER_ICON_PX
    pixmap = QtGui.QPixmap(size_px, size_px)
    pixmap.fill(QtCore.Qt.GlobalColor.transparent)

    room = QtCore.QRectF(
        _WALL_INSET_PX, _WALL_INSET_PX, size_px - 2 * _WALL_INSET_PX, size_px - 2 * _WALL_INSET_PX
    )
    # The height does not move the boresight, only the floor.
    boresight_x, boresight_y, _ = _boresight(
        SensorInstallation(z_rotation=z_rotation, mount_height_m=0.0)
    )
    if not in_corner or np.isclose(boresight_x, 0.0):
        wall_x_px = room.center().x()
    elif boresight_x > 0.0:
        wall_x_px = room.left()
    else:
        wall_x_px = room.right()
    # The picture's y points down, the world's up.
    sensor_center = QtCore.QPointF(
        wall_x_px + _SENSOR_OFFSET_PX * boresight_x,
        room.bottom() - _SENSOR_OFFSET_PX * boresight_y,
    )
    walls = QtGui.QPolygonF(
        [room.topLeft(), room.topRight(), room.bottomRight(), room.bottomLeft(), room.topLeft()]
    )

    _draw_room(
        pixmap, room, walls, sensor_center, np.rad2deg(np.arctan2(boresight_y, boresight_x))
    )
    return pixmap, sensor_center


def wall_side_view_icon(x_rotation: float) -> QtGui.QIcon:
    """A room seen from the side, the sensor on the wall to the left tilted
    by ``x_rotation`` degrees, with a beam along its boresight. Needs a
    ``QApplication``."""
    width_px = 48 * _PX_PER_ICON_PX
    height_px = 32 * _PX_PER_ICON_PX
    pixmap = QtGui.QPixmap(width_px, height_px)
    pixmap.fill(QtCore.Qt.GlobalColor.transparent)

    # Open to the top and the right.
    room = QtCore.QRectF(_WALL_INSET_PX, 0, width_px - _WALL_INSET_PX, height_px - _WALL_INSET_PX)
    # The height does not move the boresight, only the floor.
    _, boresight_y, boresight_z = _boresight(
        SensorInstallation(x_rotation=x_rotation, mount_height_m=0.0)
    )
    # The picture's y points down, the world's up.
    sensor_center = QtCore.QPointF(
        room.left() + _SENSOR_OFFSET_PX * boresight_y,
        0.4 * height_px - _SENSOR_OFFSET_PX * boresight_z,
    )
    walls = QtGui.QPolygonF([room.topLeft(), room.bottomLeft(), room.bottomRight()])

    _draw_room(
        pixmap, room, walls, sensor_center, np.rad2deg(np.arctan2(boresight_z, boresight_y))
    )
    return QtGui.QIcon(pixmap)


def sensor_front_icon(y_rotation: float) -> QtGui.QIcon:
    """The sensor box of the 3D view's sensor model, rolled by ``y_rotation``
    (0 or 180 degrees), as seen from in front of it: its pin 0 marker is
    bottom right when upright, top left when upside down. Needs a
    ``QApplication``."""
    width_px = round(2 * sensor_model.HALF_WIDTH_M * _SENSOR_PX_PER_M)
    height_px = round((sensor_model.Z_TOP_M - sensor_model.Z_BOTTOM_M) * _SENSOR_PX_PER_M)
    pixmap = QtGui.QPixmap(width_px, height_px)
    pixmap.fill(QtCore.Qt.GlobalColor.transparent)

    # The height does not move a sensor-frame point, only the floor.
    installation = SensorInstallation(y_rotation=y_rotation, mount_height_m=0.0)
    pin_x_m, _, pin_z_m = installation.sensor_to_world(sensor_model.PIN_CENTER_M)
    # Facing the sensor, its +x points left and its +z up.
    pin_center = QtCore.QPointF(
        (sensor_model.HALF_WIDTH_M - pin_x_m) * _SENSOR_PX_PER_M,
        (sensor_model.Z_TOP_M - pin_z_m) * _SENSOR_PX_PER_M,
    )
    pin_radius_px = sensor_model.PIN_RADIUS_M * _SENSOR_PX_PER_M

    painter = QtGui.QPainter(pixmap)
    painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
    painter.setPen(QtCore.Qt.PenStyle.NoPen)
    colors = palette.current()
    painter.setBrush(colors.sensor_body.qcolor())
    painter.drawRect(0, 0, width_px, height_px)
    painter.setBrush(colors.sensor_pin.qcolor())
    painter.drawEllipse(pin_center, pin_radius_px, pin_radius_px)
    painter.end()

    return QtGui.QIcon(pixmap)
