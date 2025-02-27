# Copyright (c) Acconeer AB, 2023-2025
# All rights reserved

from functools import partial

import qtawesome as qta


BUTTON_ICON_COLOR = "#0081db"
TEXT_GREY = "#4d5157"
TEXT_LIGHTGREY = "#888f99"
WARNING_YELLOW = "#ff9e00"
ERROR_RED = "#e6635a"


# "partial" is used here as the icons from qtawesome needs a running QApplication
# in order to be constructed. This makes all of the "icons" below callable.
#
# Typical usage is (notice that it is a call, since "()" is present)
#
#     QLabel(ARROW_LEFT_BOLD(), ...)
#
# A nice side-effect is that the "color" of the icon can be overridden by the caller
#
#     QLabel(ARROW_LEFT_BOLD(color="<my custom color>"), ...)
#
# fmt: off
ARROW_LEFT_BOLD = partial(qta.icon, "ph.arrow-left-bold",        color=BUTTON_ICON_COLOR)
CALIBRATE       = partial(qta.icon, "fa5s.circle",               color=BUTTON_ICON_COLOR)
CHART_BAR       = partial(qta.icon, "fa5.chart-bar",             color=BUTTON_ICON_COLOR)
CHART_LINE      = partial(qta.icon, "ri.line-chart-fill",        color=BUTTON_ICON_COLOR)
CHECKMARK       = partial(qta.icon, "fa5s.check",                color=BUTTON_ICON_COLOR)
CLOSE           = partial(qta.icon, "mdi.close",                 color=BUTTON_ICON_COLOR)
COG             = partial(qta.icon, "fa5s.cog",                  color=BUTTON_ICON_COLOR)
EDIT            = partial(qta.icon, "fa5s.edit",                 color=BUTTON_ICON_COLOR)
EXTERNAL_LINK   = partial(qta.icon, "fa5s.external-link-alt",    color=BUTTON_ICON_COLOR)
FLASH           = partial(qta.icon, "mdi.flash",                 color=BUTTON_ICON_COLOR)
FOLDER_OPEN     = partial(qta.icon, "fa5s.folder-open",          color=BUTTON_ICON_COLOR)
GAUGE           = partial(qta.icon, "mdi.gauge-full",            color=BUTTON_ICON_COLOR)
HELP            = partial(qta.icon, "mdi6.help-circle",          color=BUTTON_ICON_COLOR)
INFO            = partial(qta.icon, "fa5s.info-circle",          color=BUTTON_ICON_COLOR)
LINK            = partial(qta.icon, "fa5s.link",                 color=BUTTON_ICON_COLOR)
MEMORY          = partial(qta.icon, "fa5s.memory",               color=BUTTON_ICON_COLOR)
PLAY            = partial(qta.icon, "fa5s.play-circle",          color=BUTTON_ICON_COLOR)
PLUS            = partial(qta.icon, "ei.plus-sign",              color=BUTTON_ICON_COLOR)
REFRESH         = partial(qta.icon, "ei.refresh",                color=BUTTON_ICON_COLOR)
REMOVE          = partial(qta.icon, "ei.remove-sign",            color=BUTTON_ICON_COLOR)
RESTORE         = partial(qta.icon, "mdi6.restore",              color=BUTTON_ICON_COLOR)
SAVE            = partial(qta.icon, "mdi.content-save",          color=BUTTON_ICON_COLOR)
RECORD          = partial(qta.icon, "mdi.record-circle-outline", color=BUTTON_ICON_COLOR)
STOP            = partial(qta.icon, "fa5s.stop-circle",          color=BUTTON_ICON_COLOR)
UNLINK          = partial(qta.icon, "fa5s.unlink",               color=BUTTON_ICON_COLOR)
WARNING         = partial(qta.icon, "ph.warning-fill",           color=WARNING_YELLOW)
EYE_OPEN        = partial(qta.icon, "fa5s.eye",                  color=BUTTON_ICON_COLOR)
EYE_CLOSED      = partial(qta.icon, "fa5s.eye-slash",            color=BUTTON_ICON_COLOR)
# fmt: on
