# Copyright (c) Acconeer AB, 2026
# All rights reserved

import multiprocessing as mp
from collections.abc import Sequence


def avoid_fork(preload: Sequence[str]) -> None:
    """Starts child processes with forkserver, where Python before 3.14 defaults to fork.

    A forked child gets copies of the locks other threads held, still locked.
    The forkserver imports ``preload`` once for all children. Call once, before
    any child process starts.
    """
    # The first method is the default.
    if mp.get_all_start_methods()[0] in {"fork", "forkserver"}:
        mp.set_start_method("forkserver")
        mp.set_forkserver_preload(list(preload))
