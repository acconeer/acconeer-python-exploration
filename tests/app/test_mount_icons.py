# Copyright (c) Acconeer AB, 2026
# All rights reserved

from __future__ import annotations

import pytest

from PySide6 import QtGui

from acconeer.exptool.a2.algo._mount_icons import (
    custom_pan_icon,
    room_top_view_icon,
    sensor_front_icon,
    wall_side_view_icon,
)


@pytest.mark.usefixtures("qapplication")
@pytest.mark.parametrize(
    ("z_rotation", "lit", "dark"),
    [
        # Points as fractions of the icon's width and height, from its top left.
        (0.0, [(0.5, 0.4)], [(0.1, 0.4), (0.9, 0.4)]),
        # Positive pan turns the boresight toward -x, so from the right corner.
        (45.0, [(0.4, 0.4)], [(0.9, 0.15), (0.1, 0.85)]),
        (-45.0, [(0.6, 0.4)], [(0.1, 0.15), (0.9, 0.85)]),
    ],
)
def test_room_top_view_icon_beams_along_the_boresight(
    z_rotation: float, lit: list[tuple[float, float]], dark: list[tuple[float, float]]
) -> None:
    image = room_top_view_icon(z_rotation).pixmap(96, 96).toImage()

    assert all(_is_lit(image, x, y) for x, y in lit)
    assert not any(_is_lit(image, x, y) for x, y in dark)


@pytest.mark.usefixtures("qapplication")
def test_custom_pan_icon_turns_the_sensor_in_the_middle_of_the_wall_under_an_arc() -> None:
    image = custom_pan_icon().pixmap(96, 96).toImage()

    # Up and a little to the left from the middle, not from a corner.
    assert _is_lit(image, 0.35, 0.25)
    assert not _is_lit(image, 0.9, 0.3)
    # The arc's top, above the sensor, in the walls' color.
    arc = image.pixelColor(round(0.47 * (image.width() - 1)), round(0.51 * (image.height() - 1)))
    assert arc.red() < 140 and abs(arc.red() - arc.green()) < 20


@pytest.mark.usefixtures("qapplication")
@pytest.mark.parametrize(
    ("x_rotation", "lit", "dark"),
    [
        # The sensor sits on the left wall, 0.4 of the height from the top.
        (0.0, [(0.6, 0.4)], [(0.38, 0.08), (0.38, 0.72)]),
        # Positive tilt turns the boresight up.
        (30.0, [(0.38, 0.14)], [(0.6, 0.6)]),
        (-30.0, [(0.38, 0.66)], [(0.6, 0.2)]),
    ],
)
def test_wall_side_view_icon_beams_along_the_boresight(
    x_rotation: float, lit: list[tuple[float, float]], dark: list[tuple[float, float]]
) -> None:
    image = wall_side_view_icon(x_rotation).pixmap(144, 96).toImage()

    assert all(_is_lit(image, x, y) for x, y in lit)
    assert not any(_is_lit(image, x, y) for x, y in dark)


@pytest.mark.usefixtures("qapplication")
@pytest.mark.parametrize(
    ("y_rotation", "pin_corner"),
    [(0.0, "bottom right"), (180.0, "top left")],
)
def test_sensor_front_icon_shows_the_pin_marker_in_its_corner(
    y_rotation: float, pin_corner: str
) -> None:
    image = sensor_front_icon(y_rotation).pixmap(160, 80).toImage()
    # Where the pin 0 marker would sit, one inset in from each corner.
    corners = {
        "top left": (16, 16),
        "top right": (image.width() - 17, 16),
        "bottom left": (16, image.height() - 17),
        "bottom right": (image.width() - 17, image.height() - 17),
    }

    white = {
        name for name, (x, y) in corners.items() if image.pixelColor(x, y) == QtGui.QColor("white")
    }

    assert white == {pin_corner}


def _is_lit(image: QtGui.QImage, x: float, y: float) -> bool:
    """Whether the beam covers the point ``x``, ``y``, as fractions of the
    image's width and height, from its top left."""
    color = image.pixelColor(round(x * (image.width() - 1)), round(y * (image.height() - 1)))
    # The beam tints the grey floor red.
    return color.red() - color.green() > 40
