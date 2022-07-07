from __future__ import annotations

from typing import Optional

from PySide6 import QtCore
from PySide6.QtWidgets import QGridLayout, QGroupBox, QLabel, QLineEdit, QWidget

from acconeer.exptool import a121


_WIDGET_WIDTH = 125


class PerfCalcView(QGroupBox):
    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)

        self.setTitle("Performance calculations")

        layout = QGridLayout(self)
        self.setLayout(layout)

        self.average_current = PerfCalcValueWidget(self)
        layout.addWidget(self.average_current, 0, 1)
        layout.addWidget(QLabel("Estimated avg. current", self), 0, 0)

        self.update(None)

    def update(
        self,
        session_config: Optional[a121.SessionConfig] = None,
        metadata: Optional[a121.Metadata] = None,
    ) -> None:
        try:
            self._update(session_config, metadata)
        except Exception:
            pass
        else:
            return

        self.average_current.setText("-")

    def _update(
        self,
        session_config: Optional[a121.SessionConfig] = None,
        metadata: Optional[a121.Metadata] = None,
    ) -> None:
        if session_config is None or metadata is None:
            raise ValueError

        pc = a121._PerformanceCalc(session_config, metadata)

        self.average_current.setText(f"{pc.average_current * 1e3:.0f} mA")


class PerfCalcValueWidget(QLineEdit):
    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setAlignment(QtCore.Qt.AlignRight)
        self.setFixedWidth(_WIDGET_WIDTH)
        self.setReadOnly(True)
        self.setFocusPolicy(QtCore.Qt.NoFocus)
