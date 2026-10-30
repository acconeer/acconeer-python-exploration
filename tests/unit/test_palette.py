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
