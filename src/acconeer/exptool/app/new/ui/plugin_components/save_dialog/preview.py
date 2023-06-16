# Copyright (c) Acconeer AB, 2023
# All rights reserved

from __future__ import annotations

import enum
import functools
import re
import typing as t

import typing_extensions as te

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFontMetricsF, QSyntaxHighlighter, QTextCharFormat, QTextDocument
from PySide6.QtWidgets import QGridLayout, QLabel, QPushButton, QTextEdit, QWidget


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


class _Rgb(te.TypedDict, total=True):
    r: int
    g: int
    b: int


class _SyntaxHighlighter(QSyntaxHighlighter):
    GOLDEN_ROD: _Rgb = dict(r=218, g=165, b=32)
    PURPLE: _Rgb = dict(r=160, g=32, b=240)
    FOREST_GREEN: _Rgb = dict(r=34, g=139, b=34)
    DODGER_BLUE: _Rgb = dict(r=30, g=144, b=255)
    FIREBRICK: _Rgb = dict(r=178, g=34, b=34)
    SIENNA: _Rgb = dict(r=160, g=82, b=45)
    GRAY: _Rgb = dict(r=100, g=100, b=100)

    def __init__(self, parent: QTextDocument, highlights: dict[str, QTextCharFormat]) -> None:
        super().__init__(parent)
        self._highlights = highlights

    def highlightBlock(self, text: str) -> None:
        for pattern, fmt in self._highlights.items():
            for match in re.finditer(pattern, text):
                # The first capturing group in the regex will be styled
                try:
                    match_length = match.end(1) - match.start(1)
                    self.setFormat(match.start(1), match_length, fmt)
                except IndexError:
                    pass

    @staticmethod
    def _create_char_fmt(
        *,
        r: int = 0,
        g: int = 0,
        b: int = 0,
        italic: bool = False,
        weight: int = 400,
    ) -> QTextCharFormat:
        fmt = QTextCharFormat()
        fmt.setForeground(QColor(r, g, b))
        fmt.setFontItalic(italic)
        fmt.setFontWeight(weight)
        return fmt

    @classmethod
    def json(cls, parent: QTextDocument) -> _SyntaxHighlighter:
        return cls(
            parent,
            {
                r'("[^"]*")': cls._create_char_fmt(**cls.GOLDEN_ROD),  # string literals
                r"(\d+(?:\.\d+)?),": cls._create_char_fmt(**cls.DODGER_BLUE),  # number literals
            },
        )

    @classmethod
    def rss_c(cls, parent: QTextDocument) -> _SyntaxHighlighter:
        snake_case = "[a-z]+(?:_[a-z]+)*"
        type_regex = f"{snake_case}_t "
        acc_type_regex = f"acc_{type_regex}"
        return cls(
            parent,
            {
                # anything snake_case
                rf"({snake_case})": cls._create_char_fmt(**cls.SIENNA),
                # keywords
                r"(static)": cls._create_char_fmt(**cls.PURPLE),
                # types
                rf"(void|{type_regex}|{acc_type_regex})": cls._create_char_fmt(**cls.FOREST_GREEN),
                # function call & -definition
                rf"(set_config|acc_{snake_case}_set)\(": cls._create_char_fmt(b=255, weight=500),
                # int literals
                r"(\d+U?)": cls._create_char_fmt(**cls.DODGER_BLUE),
                # floating literals
                r"(\d+\.\d+f?)": cls._create_char_fmt(**cls.DODGER_BLUE),
                # bool literals
                "(true|false)": cls._create_char_fmt(r=0, g=0, b=0),
                # acconeer enum members/constants
                r"(ACC[_A-Z0-9]*)": cls._create_char_fmt(**cls.GOLDEN_ROD),
                # single line comments
                r"(//.*)": cls._create_char_fmt(**cls.FIREBRICK, italic=True),
                # parameter ignores
                rf"(\(void\){snake_case};)": cls._create_char_fmt(**cls.GRAY, italic=True),
            },
        )


class PresentationWindow(QWidget):
    _NOTE_TEXT = "<b>Note!</b> A compact JSON string is always saved to file."
    _HIGHLIGHTERS = {
        PresentationType.JSON: _SyntaxHighlighter.json,
        PresentationType.C_SET_CONFIG: _SyntaxHighlighter.rss_c,
    }

    def __init__(
        self, presentations: dict[PresentationType, str], parent: t.Optional[QWidget] = None
    ) -> None:
        super().__init__(parent=parent)

        self._preview = QTextEdit(parent=self)
        self._preview.setFontFamily("monospace")
        self._preview.setReadOnly(True)
        self._preview.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        self._highlighter = _SyntaxHighlighter.json(self._preview.document())

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
