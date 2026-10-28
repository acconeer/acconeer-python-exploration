# Copyright (c) Acconeer AB, 2026
# All rights reserved

from __future__ import annotations

import logging
import typing as t

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

    The view stays empty until a context initializes: drawing the items into a
    context pyqtgraph rejected reads vertex data through buffers it never
    uploaded, which also segfaults the process.
    """

    def __init__(self, *args: t.Any, **kwargs: t.Any) -> None:
        self._gl_initialized = False
        super().__init__(*args, **kwargs)

    def initializeGL(self) -> None:
        self._gl_initialized = False
        try:
            super().initializeGL()
        except Exception:
            log.exception("Could not initialize OpenGL for the 3D view")
        else:
            self._gl_initialized = True

    def paintGL(self) -> None:
        if self._gl_initialized:
            super().paintGL()
