# Copyright (c) Acconeer AB, 2026
# All rights reserved

from __future__ import annotations

import pytest

from PySide6.QtWidgets import QApplication, QFrame, QLabel, QPushButton

from acconeer.exptool.app.new.ui.components.group_box import GroupBox


@pytest.mark.usefixtures("qapplication")
def test_group_box_places_its_heading_on_the_first_resize() -> None:
    button = QPushButton("Save")
    button.setFixedHeight(40)
    box = GroupBox.vertical("Heading", right_header=button)
    box.layout().addWidget(QLabel("Content"))

    box.resize(300, 200)
    box.show()
    QApplication.processEvents()
    first = box.layout().parentWidget().geometry()
    headers = box.findChildren(QFrame, "GroupBoxQFrameHeader")

    # A second resize used to move the content, as only then had the
    # headers their size.
    box.resize(300, 201)
    QApplication.processEvents()

    assert box.layout().parentWidget().y() == first.y()
    assert all(header.geometry().top() >= 0 for header in headers)
