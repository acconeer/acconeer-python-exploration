# Copyright (c) Acconeer AB, 2026
# All rights reserved

INSTALL_MISSING_APP_EXTRA_INSTRUCTIONS = """\
################################################################################
It looks like ET's application dependencies aren't installed in
this Python environment.

Install the [app] extra and run ET again with one of the commands:
 -  uvx:
    uvx 'acconeer-exptool[app]'
 -  uv:
    uv run --with 'acconeer-exptool[app]' -m acconeer.exptool.app
    uv run --with '.[app]' -m acconeer.exptool.app
 -  pip:
    pip install 'acconeer-exptool[app]'
    pip install '.[app]'
################################################################################
"""
