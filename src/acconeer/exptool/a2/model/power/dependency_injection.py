# Copyright (c) Acconeer AB, 2023-2026
# All rights reserved
"""
This module provides a simple default value provider,
making it quick to change default values module-wide.
"""

from . import algo, lookup


DEFAULT_ALGO = algo.SparseIq()
DEFAULT_SENSOR = lookup.DEFAULT_SENSOR
