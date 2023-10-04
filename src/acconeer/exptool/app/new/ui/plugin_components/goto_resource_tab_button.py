# Copyright (c) Acconeer AB, 2023
# All rights reserved

from PySide6.QtCore import QSize
from PySide6.QtWidgets import QPushButton

from acconeer.exptool.app.new.ui.icons import GAUGE


_TOOL_TIP = """
Copies the current config into a new input block in the resource tab.

Note that no changes in the resource tab are not copied back here.
""".strip()


class GotoResourceTabButton(QPushButton):
    def __init__(self) -> None:
        super().__init__("View in Resource Calculator")
        self.setIcon(GAUGE())
        self.setIconSize(QSize(24, 24))
        self.setToolTip(_TOOL_TIP)
