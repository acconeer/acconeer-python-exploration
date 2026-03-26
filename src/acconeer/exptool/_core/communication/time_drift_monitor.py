# Copyright (c) Acconeer AB, 2026
# All rights reserved

import warnings

import attrs


@attrs.frozen
class TimeDriftMonitor:
    """
    Helper class for warning the user that when "wall-clock time" (time.monotonic) and
    server time[1] diverge too much.

    [1] server time is usually derived from results' ``tick`` and the server's ``ticks_per_second``.
    """

    server_reference_s: float
    wall_reference_s: float
    max_allowed_drift_s: float

    def warn_if_current_drift_is_too_high(
        self,
        server_timestamp_s: float,
        wall_timestamp_s: float,
        # stacklevel=3 assumes that this class is used directly from a Client's get_next()
        # which causes the warning to point at the user's call to get_next().
        warning_stacklevel: int = 3,
    ) -> None:
        elapsed_server_time = server_timestamp_s - self.server_reference_s
        elapsed_wall_time = wall_timestamp_s - self.wall_reference_s
        current_drift_s = abs(elapsed_wall_time - elapsed_server_time)

        if current_drift_s > self.max_allowed_drift_s:
            msg = f"Server timestamp was from {current_drift_s:.2f}s ago. Results needs to be read more often."
            warnings.warn(msg, stacklevel=warning_stacklevel)
