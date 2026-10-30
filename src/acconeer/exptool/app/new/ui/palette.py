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

    def blend(self, background: Color, opacity: float) -> Color:
        """This color at ``opacity`` over ``background``, as one opaque color."""

        def mix(channel: int, background_channel: int) -> int:
            return round(channel * opacity + background_channel * (1 - opacity))

        return Color(
            mix(self.r, background.r), mix(self.g, background.g), mix(self.b, background.b)
        )

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


class Brand:
    """Acconeer's blue and grey scales, from the Acconeer Design Guidelines.

    The guidelines pick their steps for a dark background: on a light one,
    Blue 600 is the brightest blue that text and thin lines can take, and
    Blue 800 and up only suit large marks."""

    BLUE_50 = Color.from_hex("#071f2c")
    BLUE_100 = Color.from_hex("#092635")
    BLUE_200 = Color.from_hex("#0b2e40")
    BLUE_300 = Color.from_hex("#0e384d")
    BLUE_400 = Color.from_hex("#12445c")
    """Deep Blue."""
    BLUE_500 = Color.from_hex("#16506b")
    BLUE_600 = Color.from_hex("#1c7396")
    BLUE_700 = Color.from_hex("#2493bf")
    BLUE_800 = Color.from_hex("#3aaedb")
    """Bright Blue."""
    BLUE_900 = Color.from_hex("#57c9f4")
    BLUE_950 = Color.from_hex("#7ed5f7")

    GREY_50 = Color.from_hex("#f7f9fc")
    GREY_100 = Color.from_hex("#eceff5")
    GREY_200 = Color.from_hex("#d9dee8")
    GREY_300 = Color.from_hex("#bbc3d1")
    GREY_400 = Color.from_hex("#9da6b7")
    GREY_500 = Color.from_hex("#7f899d")
    GREY_600 = Color.from_hex("#586172")
    GREY_700 = Color.from_hex("#2b313a")
    GREY_800 = Color.from_hex("#171c22")
    GREY_900 = Color.from_hex("#0c1015")
    GREY_950 = Color.from_hex("#05080b")


_WHITE = Color.from_hex("#ffffff")
_SENSOR_RED = Color(217, 26, 26)

LIGHT = Palette(
    accent=Brand.BLUE_600,
    text=Color.from_hex("#4d5157"),
    text_light=Color.from_hex("#888f99"),
    warning=Color.from_hex("#ff9e00"),
    error=Color.from_hex("#e6635a"),
    slider_bar=Brand.BLUE_600,
    slider_groove=Brand.BLUE_600.blend(_WHITE, 0.3),
    sensor_body=_SENSOR_RED,
    sensor_pin=_WHITE,
    picture_floor=Color(230, 230, 230),
    picture_wall=Color(90, 90, 90),
)


def current() -> Palette:
    """The palette the app is drawn in."""
    return LIGHT
