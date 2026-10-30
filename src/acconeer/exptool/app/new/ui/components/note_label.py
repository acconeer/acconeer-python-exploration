# Copyright (c) Acconeer AB, 2026
# All rights reserved

from __future__ import annotations

from PySide6 import QtCore
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QWidget

from acconeer.exptool._core.entities.validation_result import Criticality
from acconeer.exptool.app.new.ui import icons, palette


_ICON_SIZE_PX = 16
# Opacity of the background tint, in the criticality's color.
_TINT_ALPHA = 28


class NoteLabel(QFrame):
    """A message about a setting, such as a validation error: an icon and the
    message in plain text, on a tint of its criticality's color with a bar
    of it on the left. Hidden without a message."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName(type(self).__name__)

        self._icon = QLabel(self)
        self._icon.setFixedSize(_ICON_SIZE_PX, _ICON_SIZE_PX)
        self._text = QLabel(self)
        self._text.setWordWrap(True)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(6)
        layout.addWidget(self._icon, 0, QtCore.Qt.AlignmentFlag.AlignTop)
        layout.addWidget(self._text, 1)

        self.hide()

    def set_note(self, message: str | None, criticality: Criticality | None = None) -> None:
        """Show ``message``, or hide if there is none."""
        if not message:
            self.hide()
            return

        colors = palette.current()
        if criticality == Criticality.ERROR:
            color, icon = colors.error, icons.ERROR
        elif criticality == Criticality.WARNING:
            color, icon = colors.warning, icons.WARNING
        else:
            color, icon = colors.text_light, icons.INFO

        self._icon.setPixmap(icon(color=color.hex).pixmap(_ICON_SIZE_PX, _ICON_SIZE_PX))
        self._text.setText(message)
        name = self.objectName()
        self.setStyleSheet(
            f"#{name} {{ background-color: {color.with_alpha(_TINT_ALPHA).css};"
            f" border: none; border-left: 3px solid {color.css}; border-radius: 3px; }}"
            f" #{name} QLabel {{ background: transparent; color: {colors.text.css}; }}"
        )
        self.show()

    def text(self) -> str:
        return self._text.text()
