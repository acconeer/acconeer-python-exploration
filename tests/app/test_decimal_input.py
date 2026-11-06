# Copyright (c) Acconeer AB, 2026
# All rights reserved

from __future__ import annotations

import pytest

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QWidget

from acconeer.exptool.app.new.ui.components.pidgets.pidgets import _PidgetDoubleSpinBox


pytestmark = pytest.mark.usefixtures("qapplication")


@pytest.mark.parametrize(
    ("typed", "modifier"),
    [
        ("1.5", Qt.KeyboardModifier.NoModifier),
        ("1,5", Qt.KeyboardModifier.NoModifier),
        ("1,5", Qt.KeyboardModifier.KeypadModifier),
    ],
)
def test_a_decimal_field_takes_a_comma_as_the_decimal_point(
    typed: str, modifier: Qt.KeyboardModifier
) -> None:
    parent = QWidget()
    field = _PidgetDoubleSpinBox(parent, limits=(0, 100), decimals=2)

    field.lineEdit().selectAll()
    QTest.keyClicks(field, typed, modifier)
    QTest.keyClick(field, Qt.Key.Key_Return)

    assert field.value() == 1.5
    assert field.text() == "1.50"
