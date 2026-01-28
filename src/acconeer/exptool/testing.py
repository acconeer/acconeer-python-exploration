# Copyright (c) Acconeer AB, 2026
# All rights reserved
import os


def is_running_in_ci() -> bool:
    """
    Return true if running in CI (i.e. Jenkins)
    More exactly: return True if env. var. "CI" is set to something truthy.
    """
    return bool(os.getenv("CI"))
