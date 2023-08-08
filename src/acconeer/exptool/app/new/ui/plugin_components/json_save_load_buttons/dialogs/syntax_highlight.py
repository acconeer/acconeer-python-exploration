# Copyright (c) Acconeer AB, 2023
# All rights reserved

from __future__ import annotations

import re

import typing_extensions as te

from PySide6.QtGui import QColor, QSyntaxHighlighter, QTextCharFormat, QTextDocument


class _Rgb(te.TypedDict, total=True):
    r: int
    g: int
    b: int


class SyntaxHighlighter(QSyntaxHighlighter):
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
    def json(cls, parent: QTextDocument) -> SyntaxHighlighter:
        return cls(
            parent,
            {
                r'("[^"]*")': cls._create_char_fmt(**cls.GOLDEN_ROD),  # string literals
                r"(\d+(?:\.\d+)?),": cls._create_char_fmt(**cls.DODGER_BLUE),  # number literals
            },
        )

    @classmethod
    def rss_c(cls, parent: QTextDocument) -> SyntaxHighlighter:
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
