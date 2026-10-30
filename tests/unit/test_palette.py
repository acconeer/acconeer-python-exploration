# Copyright (c) Acconeer AB, 2026
# All rights reserved

from __future__ import annotations

import pytest

from acconeer.exptool.app.new.ui.palette import Color


def test_a_color_converts_to_the_forms_qt_opengl_and_style_sheets_take() -> None:
    color = Color.from_hex("#1a73e8", a=51)

    assert color.hex == "#1a73e8"
    assert color.css == "rgba(26, 115, 232, 51)"
    assert color.rgbaf() == pytest.approx((26 / 255, 115 / 255, 232 / 255, 0.2))
    assert color.rgbaf(0.5)[3] == 0.5
    assert color.with_alpha(255).qcolor().name() == "#1a73e8"


def test_a_color_blends_over_a_background_into_one_opaque_color() -> None:
    blue_600 = Color.from_hex("#1c7396")

    assert blue_600.blend(Color.from_hex("#ffffff"), 0.3) == Color(187, 213, 224)
    assert blue_600.with_alpha(51).blend(Color(0, 0, 0), 1.0) == Color(28, 115, 150)
