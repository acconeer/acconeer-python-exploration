# Copyright (c) Acconeer AB, 2026
# All rights reserved

from __future__ import annotations

import pytest

from PySide6.QtSvgWidgets import QSvgWidget
from PySide6.QtWidgets import QApplication

from acconeer.exptool.app.new.ui.stream_tab.plugin_widget import ControlPlaceholder


def test_the_app_is_set_in_inter(qapplication: QApplication) -> None:
    assert qapplication.font().family() == "Inter"


@pytest.mark.usefixtures("qapplication")
def test_the_empty_control_area_shows_the_acconeer_symbol() -> None:
    placeholder = ControlPlaceholder()
    (symbol,) = placeholder.findChildren(QSvgWidget)

    assert symbol.renderer().isValid()
