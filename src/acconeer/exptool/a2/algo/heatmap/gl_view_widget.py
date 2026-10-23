# Copyright (c) Acconeer AB, 2026
# All rights reserved

from __future__ import annotations

import logging

import pyqtgraph.opengl as gl


log = logging.getLogger(__name__)


class GuardedGLViewWidget(gl.GLViewWidget):
    """
    GLViewWidget whose initializeGL never raises into Qt.

    pyqtgraph's initializeGL raises when no usable GL context is available
    (e.g. QT_QPA_PLATFORM=offscreen, VMs, remote desktops). On PySide6 >= 6.10,
    an exception escaping a Python initializeGL override over-releases the
    class's paintGL function, which is later freed while still referenced and
    segfaults the process. Catching it here leaves an empty 3D view instead.
    """

    def initializeGL(self) -> None:
        try:
            super().initializeGL()
        except Exception:
            log.exception("Could not initialize OpenGL for the 3D view")
