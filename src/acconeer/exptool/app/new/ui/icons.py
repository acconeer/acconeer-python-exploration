# Copyright (c) Acconeer AB, 2023
# All rights reserved

from functools import partial

import qtawesome as qta


BUTTON_ICON_COLOR = "#0081db"
WARNING_YELLOW = "#ff9e00"


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
CALIBRATE       = partial(qta.icon, "fa.circle",                 color=BUTTON_ICON_COLOR)
CHECKMARK       = partial(qta.icon, "fa5s.check",                color=BUTTON_ICON_COLOR)
COG             = partial(qta.icon, "fa5s.cog",                  color=BUTTON_ICON_COLOR)
EXTERNAL_LINK   = partial(qta.icon, "fa5s.external-link-alt",    color=BUTTON_ICON_COLOR)
FLASH           = partial(qta.icon, "mdi.flash",                 color=BUTTON_ICON_COLOR)
FOLDER_OPEN     = partial(qta.icon, "fa.folder-open",            color=BUTTON_ICON_COLOR)
HELP            = partial(qta.icon, "mdi6.help-circle",          color=BUTTON_ICON_COLOR)
LINK            = partial(qta.icon, "fa5s.link",                 color=BUTTON_ICON_COLOR)
PLAY            = partial(qta.icon, "fa5s.play-circle",          color=BUTTON_ICON_COLOR)
PLUS            = partial(qta.icon, "ei.plus-sign",              color=BUTTON_ICON_COLOR)
REFRESH         = partial(qta.icon, "fa.refresh",                color=BUTTON_ICON_COLOR)
REMOVE          = partial(qta.icon, "ei.remove-sign",            color=BUTTON_ICON_COLOR)
RESTORE         = partial(qta.icon, "mdi6.restore",              color=BUTTON_ICON_COLOR)
SAVE            = partial(qta.icon, "mdi.content-save",          color=BUTTON_ICON_COLOR)
RECORD          = partial(qta.icon, "mdi.record-circle-outline", color=BUTTON_ICON_COLOR)
STOP            = partial(qta.icon, "fa5s.stop-circle",          color=BUTTON_ICON_COLOR)
UNLINK          = partial(qta.icon, "fa5s.unlink",               color=BUTTON_ICON_COLOR)
WARNING         = partial(qta.icon, "fa.warning",                color=WARNING_YELLOW)
# fmt: on
