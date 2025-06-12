# Copyright (c) Acconeer AB, 2023-2025
# All rights reserved

from __future__ import annotations

from PySide6.QtCore import QByteArray, QPropertyAnimation, QSequentialAnimationGroup
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QGraphicsColorizeEffect,
    QWidget,
)

from acconeer.exptool.app.new.ui.icons import WARNING_YELLOW


def run_blink_animation(
    widget: QWidget,
    *,
    color: QColor = QColor(WARNING_YELLOW),
    num_blinks: int = 3,
    peak_strength: float = 0.8,
    rising_edge_ms: int = 100,
    falling_edge_ms: int = 300,
) -> None:
    c_effect = QGraphicsColorizeEffect(widget)
    c_effect.setColor(color)
    c_effect.setStrength(1.0)
    widget.setGraphicsEffect(c_effect)

    anim_group = QSequentialAnimationGroup(parent=widget)

    for _ in range(num_blinks):
        rising = QPropertyAnimation(c_effect, QByteArray(b"strength"))
        rising.setDuration(rising_edge_ms)
        rising.setStartValue(0.0)
        rising.setEndValue(peak_strength)
        anim_group.addAnimation(rising)

        falling = QPropertyAnimation(c_effect, QByteArray(b"strength"))
        falling.setDuration(falling_edge_ms)
        falling.setStartValue(peak_strength)
        falling.setEndValue(0.0)
        anim_group.addAnimation(falling)

    anim_group.start()
