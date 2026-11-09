# Copyright (c) Acconeer AB, 2023-2026
# All rights reserved

import typing as t
from functools import cache, partial
from importlib.resources import as_file, files

import qtawesome as qta

from PySide6.QtGui import QIcon

from acconeer.exptool.app import resources
from acconeer.exptool.app.new.ui import palette


BUTTON_ICON_COLOR = palette.current().accent.hex
TEXT_GREY = palette.current().text.hex
TEXT_LIGHTGREY = palette.current().text_light.hex
WARNING_YELLOW = palette.current().warning.hex
ERROR_RED = palette.current().error.hex


@cache
def _load_lucide() -> None:
    """Load Lucide's icons, once, when the first is made, as qtawesome needs a
    running QApplication. ``hatch run icons:update`` adds icons to the font."""
    with as_file(files(resources) / "icons") as directory:
        qta.load_font("lucide", "lucide.ttf", "lucide.json", directory=str(directory))


def _lucide(*names: str, **options: t.Any) -> QIcon:
    """The Lucide icons ``names``, drawn one over another."""
    _load_lucide()
    icon: QIcon = qta.icon(*(f"lucide.{name}" for name in names), **options)
    return icon


# "partial" is used here as the icons from qtawesome needs a running QApplication
# in order to be constructed. This makes all of the "icons" below callable.
#
# Typical usage is (notice that it is a call, since "()" is present)
#
#     QLabel(ARROW_LEFT(), ...)
#
# A nice side-effect is that the "color" of the icon can be overridden by the caller
#
#     QLabel(ARROW_LEFT(color="<my custom color>"), ...)
#
# Lucide's outline icons, the icon set of Acconeer's brand guidelines.
#
# fmt: off
ARROW_LEFT      = partial(_lucide, "arrow-left",              color=BUTTON_ICON_COLOR)
EXTERNAL_DOCS   = partial(_lucide, "book-open-text",          color=BUTTON_ICON_COLOR)
CALIBRATE       = partial(_lucide, "circle",                  color=BUTTON_ICON_COLOR)
CHART_BAR       = partial(_lucide, "chart-column",            color=BUTTON_ICON_COLOR)
CHART_LINE      = partial(_lucide, "chart-line",              color=BUTTON_ICON_COLOR)
CHECKMARK       = partial(_lucide, "check",                   color=BUTTON_ICON_COLOR)
CLOSE           = partial(_lucide, "x",                       color=BUTTON_ICON_COLOR)
COG             = partial(_lucide, "settings",                color=BUTTON_ICON_COLOR)
DOWNLOAD        = partial(_lucide, "download",                color=BUTTON_ICON_COLOR)
EDIT            = partial(_lucide, "pencil",                  color=BUTTON_ICON_COLOR)
ERROR           = partial(_lucide, "circle-x",                color=ERROR_RED)
EXTERNAL_LINK   = partial(_lucide, "external-link",           color=BUTTON_ICON_COLOR)
FLASH           = partial(_lucide, "zap",                     color=BUTTON_ICON_COLOR)
FOLDER_OPEN     = partial(_lucide, "folder-open",             color=BUTTON_ICON_COLOR)
GAUGE           = partial(_lucide, "gauge",                   color=BUTTON_ICON_COLOR)
HELP            = partial(_lucide, "circle-question-mark",    color=BUTTON_ICON_COLOR)
INFO            = partial(_lucide, "info",                    color=BUTTON_ICON_COLOR)
LINK            = partial(_lucide, "link",                    color=BUTTON_ICON_COLOR)
MEMORY          = partial(_lucide, "cpu",                     color=BUTTON_ICON_COLOR)
MIRROR          = partial(_lucide, "flip-horizontal-2",       color=BUTTON_ICON_COLOR)
MIRROR_90       = partial(_lucide, "flip-vertical-2",         color=BUTTON_ICON_COLOR)
PLAY            = partial(_lucide, "circle-play",             color=BUTTON_ICON_COLOR)
PLUS            = partial(_lucide, "circle-plus",             color=BUTTON_ICON_COLOR)
REFRESH         = partial(_lucide, "refresh-cw",              color=BUTTON_ICON_COLOR)
REMOVE          = partial(_lucide, "circle-minus",            color=BUTTON_ICON_COLOR)
RESTORE         = partial(_lucide, "rotate-ccw",              color=BUTTON_ICON_COLOR)
SAVE            = partial(_lucide, "save",                    color=BUTTON_ICON_COLOR)
RECORD          = partial(_lucide, "circle-dot",              color=BUTTON_ICON_COLOR)
ROTATE          = partial(_lucide, "rotate-cw-square",        color=BUTTON_ICON_COLOR)
STOP            = partial(_lucide, "circle-stop",             color=BUTTON_ICON_COLOR)
UNLINK          = partial(_lucide, "unlink",                  color=BUTTON_ICON_COLOR)
WARNING         = partial(_lucide, "triangle-alert",          color=WARNING_YELLOW)
EYE_OPEN        = partial(_lucide, "eye",                     color=BUTTON_ICON_COLOR)
EYE_CLOSED      = partial(_lucide, "eye-off",                 color=BUTTON_ICON_COLOR)
FULLSCREEN      = partial(_lucide, "expand",                  color=BUTTON_ICON_COLOR)
FULLSCREEN_EXIT = partial(_lucide, "shrink",                  color=BUTTON_ICON_COLOR)
# fmt: on
