# Copyright (c) Acconeer AB, 2026
# All rights reserved

import subprocess as sp


def test_library_is_importable_through_uv_run() -> None:
    sp.check_call(
        ["uv", "run", "python", "-c", "import acconeer.exptool as et; print(et.__version__)"]
    )
