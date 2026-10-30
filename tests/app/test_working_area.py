# Copyright (c) Acconeer AB, 2026
# All rights reserved

from __future__ import annotations

from unittest.mock import Mock

import pytest

from PySide6.QtWidgets import QMainWindow

from acconeer.exptool.app.new._enums import ConnectionState, PluginGeneration, PluginState
from acconeer.exptool.app.new.ui.stream_tab.widgets import WorkingArea


pytestmark = pytest.mark.usefixtures("qapplication")


@pytest.mark.parametrize("maximized", [True, False])
def test_leaving_fullscreen_restores_the_window_as_it_was(maximized: bool) -> None:
    app_model = Mock(
        plugin=None,
        plugins=[],
        plugin_state=PluginState.UNLOADED,
        connection_state=ConnectionState.DISCONNECTED,
        plugin_generation=PluginGeneration.A2,
    )
    window = QMainWindow()
    area = WorkingArea(app_model, window)
    window.setCentralWidget(area)
    window.showMaximized() if maximized else window.showNormal()

    area._toggle_fullscreen()
    assert window.isFullScreen()

    area.exit_fullscreen()
    assert not window.isFullScreen()
    assert window.isMaximized() is maximized
    window.close()
