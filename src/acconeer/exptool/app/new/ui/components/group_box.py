# Copyright (c) Acconeer AB, 2022-2025
# All rights reserved

from __future__ import annotations

import enum
import typing as t

from PySide6.QtCore import QPoint, QRect
from PySide6.QtGui import QResizeEvent
from PySide6.QtWidgets import QFrame, QGridLayout, QLabel, QLayout, QVBoxLayout, QWidget


_T = t.TypeVar("_T", bound=QLayout)


class GroupBox(QWidget, t.Generic[_T]):
    _HORIZONTAL_HEADER_MARGIN = 7
    _EXTRA_MARGIN_TO_AVOID_CLIPPING = 2

    class _Position(enum.Enum):
        LEFT = enum.auto()
        RIGHT = enum.auto()

    def __init__(
        self,
        left_header: t.Union[QWidget, str],
        layout_type: t.Type[_T],
        right_header: t.Optional[QWidget] = None,
        *,
        min_top_padding: int = 0,
        parent: t.Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._own_layout = QVBoxLayout()
        self.setLayout(self._own_layout)

        self._frame_layout = layout_type()
        self._frame = QFrame()
        self._frame.setFrameShape(QFrame.Shape.Box)
        self._frame.setLayout(self._frame_layout)
        self._own_layout.addWidget(self._frame)

        # Header widgets are not added to the layout as their positions are handled manually
        self._header_frames = {}
        self._min_top_padding = min_top_padding

        if isinstance(left_header, QWidget):
            self._header_frames[self._Position.LEFT] = self._wrap_in_frame(left_header)
        elif isinstance(left_header, str) and left_header != "":
            self._header_frames[self._Position.LEFT] = self._wrap_in_frame(
                QLabel(f"<b>{left_header}</b>"),
            )

        if right_header is not None:
            self._header_frames[self._Position.RIGHT] = self._wrap_in_frame(right_header)

    @classmethod
    def vertical(
        cls,
        left_header: t.Union[QWidget, str],
        right_header: t.Optional[QWidget] = None,
        *,
        min_top_padding: int = 0,
        parent: t.Optional[QWidget] = None,
    ) -> GroupBox[QVBoxLayout]:
        return cls(
            left_header,
            QVBoxLayout,  # type: ignore[return-value,arg-type]
            right_header=right_header,
            min_top_padding=min_top_padding,
            parent=parent,
        )

    @classmethod
    def grid(
        cls,
        left_header: t.Union[QWidget, str],
        right_header: t.Optional[QWidget] = None,
        *,
        min_top_padding: int = 0,
        parent: t.Optional[QWidget] = None,
    ) -> GroupBox[QGridLayout]:
        return cls(
            left_header,
            QGridLayout,  # type: ignore[return-value,arg-type]
            right_header=right_header,
            min_top_padding=min_top_padding,
            parent=parent,
        )

    def layout(self) -> _T:
        """Returns the layout of the internal QFrame"""
        return self._frame.layout()  # type: ignore[return-value]

    def _wrap_in_frame(self, widget: QWidget) -> QFrame:
        """
        Header widgets are wrapped in a frame to
        make sure the header widgets have an opaque background
        """
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(widget)

        frame = QFrame(parent=self)
        frame.setObjectName("GroupBoxQFrameHeader")
        frame.setStyleSheet("#GroupBoxQFrameHeader { border: none; padding: 1px; }")
        frame.setFrameShape(QFrame.Shape.NoFrame)
        frame.setLayout(layout)

        return frame

    def resizeEvent(self, event: QResizeEvent) -> None:
        """Handles positioning of header frame widgets manually"""
        super().resizeEvent(event)

        top_margin = max(
            [
                self._min_top_padding,
                *(frame.rect().center().y() for frame in self._header_frames.values()),
            ]
        )

        self._own_layout.setContentsMargins(0, top_margin, 0, 0)

        top_padding = top_margin
        frame_margins = self._frame_layout.contentsMargins()
        frame_margins.setTop(top_padding + self._EXTRA_MARGIN_TO_AVOID_CLIPPING)
        self._frame_layout.setContentsMargins(frame_margins)

        self._own_layout.activate()

        for position, frame in self._header_frames.items():
            new_rect = QRect(QPoint(), frame.sizeHint())
            new_rect.moveCenter(self._frame.pos())

            if position == self._Position.LEFT:
                new_rect.moveLeft(self._HORIZONTAL_HEADER_MARGIN)
            elif position == self._Position.RIGHT:
                new_rect.moveRight(self.width() - self._HORIZONTAL_HEADER_MARGIN)
            else:
                assert False, f"Unexpected HeaderWidgetPosition {position}"

            frame.setGeometry(new_rect)
