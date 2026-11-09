# Copyright (c) Acconeer AB, 2026
# All rights reserved

from __future__ import annotations

import pytest

from PySide6.QtSvgWidgets import QSvgWidget
from PySide6.QtWidgets import QApplication

from acconeer.exptool.app.new.ui import icons
from acconeer.exptool.app.new.ui.stream_tab.plugin_widget import ControlPlaceholder


def test_the_app_is_set_in_inter(qapplication: QApplication) -> None:
    assert qapplication.font().family() == "Inter"


@pytest.mark.usefixtures("qapplication")
@pytest.mark.parametrize(
    "name", [name for name, value in vars(icons).items() if name.isupper() and callable(value)]
)
def test_every_icon_is_in_the_icon_font(name: str) -> None:
    assert not getattr(icons, name)().isNull()


@pytest.mark.usefixtures("qapplication")
def test_the_empty_control_area_shows_the_acconeer_symbol() -> None:
    placeholder = ControlPlaceholder()
    (symbol,) = placeholder.findChildren(QSvgWidget)

    assert symbol.renderer().isValid()
