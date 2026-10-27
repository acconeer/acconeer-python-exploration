# Copyright (c) Acconeer AB, 2025-2026
# All rights reserved

"""Power and memory models of the A2 sensor.

Their outputs can change between releases. Code in :mod:`acconeer.exptool.a2.algo`
must not use them for anything that affects a processor or detector result or a
generated configuration; :mod:`acconeer.exptool.a2.algo._model_estimates` is its
only entry point.
"""
