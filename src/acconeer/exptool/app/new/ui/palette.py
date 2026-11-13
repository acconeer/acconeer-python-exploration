# Copyright (c) Acconeer AB, 2026
# All rights reserved

"""The app's named colors.

Widgets take their colors from :func:`current` when they are
built, instead of spelling them out, so that a restyle, or another theme, is
a change to this module only.
"""

from __future__ import annotations

import attrs

from PySide6.QtGui import QColor


@attrs.frozen
class Color:
    """An 8-bit RGBA color, in the forms that Qt, pyqtgraph, OpenGL items and
    style sheets take."""

    r: int
    g: int
    b: int
    a: int = 255

    @classmethod
    def from_hex(cls, hex_rgb: str, a: int = 255) -> Color:
        """The color ``#rrggbb``, at opacity ``a``."""
        value = int(hex_rgb.removeprefix("#"), 16)
        return cls(value >> 16, (value >> 8) & 0xFF, value & 0xFF, a)

    def with_alpha(self, a: int) -> Color:
        return attrs.evolve(self, a=a)

    @property
    def hex(self) -> str:
        """``#rrggbb``, without the opacity."""
        return f"#{self.r:02x}{self.g:02x}{self.b:02x}"

    @property
    def css(self) -> str:
        """``rgba(r, g, b, a)``, for a style sheet."""
        return f"rgba({self.r}, {self.g}, {self.b}, {self.a})"

    @property
    def rgbf(self) -> tuple[float, float, float]:
        """The color, without the opacity, in [0, 1], for an OpenGL item."""
        return (self.r / 255, self.g / 255, self.b / 255)

    def rgbaf(self, alpha: float | None = None) -> tuple[float, float, float, float]:
        """The color in [0, 1], for an OpenGL item, at opacity ``alpha``, or
        its own."""
        return (*self.rgbf, self.a / 255 if alpha is None else alpha)

    def qcolor(self) -> QColor:
        return QColor(self.r, self.g, self.b, self.a)


@attrs.frozen(kw_only=True)
class Palette:
    """The colors of one theme, by the role they play."""

    accent: Color
    """Icons, and other things to click."""
    text: Color
    """Text and icons that should not stand out, such as a docs link."""
    text_light: Color
    """Fine print."""
    warning: Color
    error: Color

    slider_bar: Color
    """The part of a range slider between its handles."""
    slider_groove: Color
    """The rest of a range slider."""

    sensor_body: Color
    """The sensor in the 3D view and in the pictures of its mounting."""
    sensor_pin: Color
    """The sensor's pin 0 marker."""
    picture_floor: Color
    picture_wall: Color
    """The room in the pictures of the sensor's mounting."""


_WHITE = Color.from_hex("#ffffff")
_GOOGLE_BLUE = Color.from_hex("#1a73e8")
_SENSOR_RED = Color(217, 26, 26)

LIGHT = Palette(
    accent=Color.from_hex("#0081db"),
    text=Color.from_hex("#4d5157"),
    text_light=Color.from_hex("#888f99"),
    warning=Color.from_hex("#ff9e00"),
    error=Color.from_hex("#e6635a"),
    slider_bar=_GOOGLE_BLUE,
    slider_groove=Color.from_hex("#abc6f6"),
    sensor_body=_SENSOR_RED,
    sensor_pin=_WHITE,
    picture_floor=Color(230, 230, 230),
    picture_wall=Color(90, 90, 90),
)


def current() -> Palette:
    """The palette the app is drawn in."""
    return LIGHT
