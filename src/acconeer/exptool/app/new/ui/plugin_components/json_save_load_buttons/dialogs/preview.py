# Copyright (c) Acconeer AB, 2023
# All rights reserved

from __future__ import annotations

import enum
import functools
import typing as t

from PySide6.QtCore import Qt
from PySide6.QtGui import QFontMetricsF
from PySide6.QtWidgets import QGridLayout, QLabel, QPushButton, QTextEdit, QWidget

from .syntax_highlight import SyntaxHighlighter


class PresentationType(enum.Enum):
    """
    Enum describing a presentation type.

    A PresenterFunc accept an PresentationType instance as its second argument.
    """

    JSON = "JSON"
    C_SET_CONFIG = "C set_config"

    @property
    def button_label(self) -> str:
        return self.value


PresenterFunc = t.Callable[[t.Any, PresentationType], t.Optional[str]]


class PresentationWindow(QWidget):
    _NOTE_TEXT = "<b>Note!</b> A compact JSON string is always saved to file."
    _HIGHLIGHTERS = {
        PresentationType.JSON: SyntaxHighlighter.json,
        PresentationType.C_SET_CONFIG: SyntaxHighlighter.rss_c,
    }

    def __init__(
        self, presentations: dict[PresentationType, str], parent: t.Optional[QWidget] = None
    ) -> None:
        super().__init__(parent=parent)

        self._preview = QTextEdit(parent=self)
        self._preview.setFontFamily("monospace")
        self._preview.setReadOnly(True)
        self._preview.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        self._highlighter = SyntaxHighlighter.json(self._preview.document())

        tab_stop_distance = QFontMetricsF(self._preview.font()).horizontalAdvance(" ") * 8
        self._preview.setTabStopDistance(tab_stop_distance)
        self._preview.setText(
            presentations.get(PresentationType.JSON, "No JSON presentation available")
        )

        layout = QGridLayout()

        num_columns = len(PresentationType)
        layout.addWidget(QLabel(f"<i>{self._NOTE_TEXT}</i>"), 0, 0, 1, num_columns)
        layout.addWidget(self._preview, 1, 0, 1, num_columns)
        for idx, member in enumerate(PresentationType):
            presentation_exists = member in presentations
            button_label = member.button_label + (
                "" if presentation_exists else " (Not available)"
            )

            button = QPushButton(button_label)
            button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            button.setEnabled(presentation_exists)
            button.clicked.connect(
                functools.partial(self._preview.setText, presentations.get(member, ""))
            )
            button.clicked.connect(functools.partial(self._swap_highlighter, member))
            layout.addWidget(button, 2, idx)

        self.setLayout(layout)

    def _swap_highlighter(self, presentation_type: PresentationType) -> None:
        self._highlighter.deleteLater()
        self._highlighter = self._HIGHLIGHTERS[presentation_type](self._preview.document())
