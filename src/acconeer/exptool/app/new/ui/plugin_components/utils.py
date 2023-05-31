# Copyright (c) Acconeer AB, 2022-2023
# All rights reserved

from __future__ import annotations

import enum
import typing as t

from PySide6.QtCore import QPoint, QRect
from PySide6.QtGui import QResizeEvent
from PySide6.QtWidgets import QFrame, QGridLayout, QLabel, QLayout, QVBoxLayout, QWidget


class GroupBox(QWidget):
    _HORIZONTAL_HEADER_MARGIN = 7
    _EXTRA_MARGIN_TO_AVOID_CLIPPING = 2

    class _Position(enum.Enum):
        LEFT = enum.auto()
        RIGHT = enum.auto()

    def __init__(
        self,
        left_header: t.Union[QWidget, str],
        layout_type: t.Type[QLayout],
        right_header: t.Optional[QWidget] = None,
        *,
        parent: t.Optional[QWidget] = None,
    ) -> None:
        super().__init__()
        self.setLayout(QVBoxLayout())

        self._frame = QFrame()
        self._frame.setFrameShape(QFrame.Shape.Box)
        self._frame.setLayout(layout_type())
        super().layout().addWidget(self._frame)

        if isinstance(left_header, str):
            left_header = QLabel(f"<b>{left_header}</b>")

        # Header widgets are not added to the layout as their positions are handled manually
        self._header_frames = {
            self._Position.LEFT: self._wrap_in_frame(left_header, frame_parent=self)
        }
        if right_header is not None:
            self._header_frames[self._Position.RIGHT] = self._wrap_in_frame(
                right_header, frame_parent=self
            )

    @classmethod
    def vertical(
        cls,
        left_header: t.Union[QWidget, str],
        right_header: t.Optional[QWidget] = None,
        *,
        parent: t.Optional[QWidget] = None,
    ) -> GroupBox:
        return cls(left_header, QVBoxLayout, right_header=right_header, parent=parent)

    @classmethod
    def grid(
        cls,
        left_header: t.Union[QWidget, str],
        right_header: t.Optional[QWidget] = None,
        *,
        parent: t.Optional[QWidget] = None,
    ) -> GroupBox:
        return cls(left_header, QGridLayout, right_header=None, parent=parent)

    def layout(self) -> QLayout:
        """Returns the layout of the internal QFrame"""
        return self._frame.layout()

    @staticmethod
    def _wrap_in_frame(widget: QWidget, frame_parent: t.Optional[QWidget] = None) -> QFrame:
        """
        Header widgets are wrapped in a frame to
        make sure the header widgets have an opaque background
        """
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(widget)

        frame = QFrame(parent=frame_parent)
        frame.setFrameShape(QFrame.Shape.NoFrame)
        frame.setLayout(layout)

        return frame

    def resizeEvent(self, event: QResizeEvent) -> None:
        """Handles positioning of header frame widgets manually"""
        super().resizeEvent(event)

        greatest_center_y = max(
            frame.rect().center().y() for frame in self._header_frames.values()
        )
        super().layout().setContentsMargins(0, greatest_center_y, 0, 0)

        frame_margins = self._frame.layout().contentsMargins()
        frame_margins.setTop(greatest_center_y + self._EXTRA_MARGIN_TO_AVOID_CLIPPING)
        self._frame.layout().setContentsMargins(frame_margins)
        super().layout().activate()

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
