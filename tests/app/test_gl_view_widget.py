# Copyright (c) Acconeer AB, 2026
# All rights reserved

from __future__ import annotations

import pytest

import pyqtgraph.opengl as gl

from acconeer.exptool.a2.algo.heatmap.gl_view_widget import GuardedGLViewWidget


pytestmark = pytest.mark.usefixtures("qapplication")


def _fail() -> None:
    msg = "pyqtgraph.opengl: Requires >= OpenGL 2.1"
    raise RuntimeError(msg)


@pytest.fixture
def paints(monkeypatch: pytest.MonkeyPatch) -> list[GuardedGLViewWidget]:
    painted: list[GuardedGLViewWidget] = []
    monkeypatch.setattr(gl.GLViewWidget, "paintGL", lambda self: painted.append(self))
    return painted


def test_a_view_that_failed_to_initialize_draws_nothing(
    monkeypatch: pytest.MonkeyPatch, paints: list[GuardedGLViewWidget]
) -> None:
    monkeypatch.setattr(gl.GLViewWidget, "initializeGL", lambda self: _fail())
    view = GuardedGLViewWidget()

    view.initializeGL()
    view.paintGL()

    assert paints == []


def test_a_view_draws_once_a_context_initializes(
    monkeypatch: pytest.MonkeyPatch, paints: list[GuardedGLViewWidget]
) -> None:
    attempts = iter([_fail, lambda: None])
    monkeypatch.setattr(gl.GLViewWidget, "initializeGL", lambda self: next(attempts)())
    view = GuardedGLViewWidget()

    view.initializeGL()
    view.initializeGL()
    view.paintGL()

    assert paints == [view]
