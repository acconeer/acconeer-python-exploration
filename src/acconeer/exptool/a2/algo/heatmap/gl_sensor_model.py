# Copyright (c) Acconeer AB, 2026
# All rights reserved

from __future__ import annotations

import numpy as np
import numpy.typing as npt

import pyqtgraph as pg
import pyqtgraph.opengl as gl

from acconeer.exptool.app.new.ui import palette


# Sensor box in the sensor frame (metres, before _SCALE): centred on the
# origin in x and z, front face at y=0 facing the boresight (+y).
_SCALE = 3.0
HALF_WIDTH_M = 0.05
_DEPTH_M = 0.01
Z_BOTTOM_M = -0.025
Z_TOP_M = 0.025

PIN_RADIUS_M = 0.006
_PIN_INSET_M = 0.01
_PIN_SEGMENTS = 24
# Just in front of the front face, so the disk is not hidden by it.
_PIN_Y_M = 0.0005
PIN_CENTER_M = np.array([-HALF_WIDTH_M + _PIN_INSET_M, _PIN_Y_M, Z_BOTTOM_M + _PIN_INSET_M])


def _body_mesh() -> gl.MeshData:
    x, y = HALF_WIDTH_M, -_DEPTH_M
    top, bottom = Z_TOP_M, Z_BOTTOM_M
    vertices = np.array(
        [
            [x, 0, top],
            [-x, 0, top],
            [-x, 0, bottom],
            [x, 0, bottom],
            [x, y, top],
            [-x, y, top],
            [-x, y, bottom],
            [x, y, bottom],
        ]
    )
    faces = np.array(
        [
            [0, 1, 2],
            [0, 2, 3],
            [4, 5, 6],
            [4, 6, 7],
            [0, 1, 5],
            [0, 5, 4],
            [2, 3, 7],
            [2, 7, 6],
            [0, 3, 7],
            [0, 7, 4],
            [1, 2, 6],
            [1, 6, 5],
        ]
    )
    return gl.MeshData(vertexes=_SCALE * vertices, faces=faces)


def _pin_mesh() -> gl.MeshData:
    angles = np.linspace(0.0, 2 * np.pi, _PIN_SEGMENTS, endpoint=False)
    rim = PIN_CENTER_M + PIN_RADIUS_M * np.stack(
        (np.cos(angles), np.zeros_like(angles), np.sin(angles)), axis=-1
    )
    vertices = np.vstack((PIN_CENTER_M, rim))
    faces = np.array([[0, 1 + i, 1 + (i + 1) % _PIN_SEGMENTS] for i in range(_PIN_SEGMENTS)])
    return gl.MeshData(vertexes=_SCALE * vertices, faces=faces)


class GLSensorModel:
    """Sensor box for a 3D view, with a pin 0 marker on its front face in the
    sensor's -x/-z corner, drawn in the sensor's mounted pose."""

    def __init__(self) -> None:
        colors = palette.current()
        self._body = gl.GLMeshItem(meshdata=_body_mesh(), color=colors.sensor_body.rgbaf())
        self._pin = gl.GLMeshItem(meshdata=_pin_mesh(), color=colors.sensor_pin.rgbaf())

    @property
    def items(self) -> list[gl.GLMeshItem]:
        return [self._body, self._pin]

    def set_mount_rotation(self, rotation: npt.NDArray[np.float64]) -> None:
        """Draw a sensor-frame vertex ``p`` at ``rotation @ p``, i.e. in the
        room frame of the mount rotation (see ``build_mount_rotation_matrix``)."""
        transform = np.eye(4)
        transform[:3, :3] = rotation
        for item in self.items:
            item.setTransform(pg.Transform3D(*transform.flatten()))
