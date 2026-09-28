# Copyright (c) Acconeer AB, 2026
# All rights reserved

from __future__ import annotations

import multiprocessing as mp
import signal
import typing as t
from multiprocessing import connection


class SigintIgnoringProcessStartError(RuntimeError):
    """The process exited before it could ignore SIGINT."""


class SigintIgnoringProcess(mp.Process):
    """A child process that ignores SIGINT once ``start()`` returns.

    A terminal Ctrl-C signals the whole foreground process group. Ignoring
    SIGINT in the parent around the start misses forkserver children, the
    default on Linux from Python 3.14.
    """

    def __init__(self, *args: t.Any, **kwargs: t.Any) -> None:
        super().__init__(*args, **kwargs)
        self._sigint_ignored, self._sigint_ignored_sender = mp.Pipe(duplex=False)

    @t.override
    def run(self) -> None:
        signal.signal(signal.SIGINT, signal.SIG_IGN)
        self._sigint_ignored_sender.send_bytes(b"")
        super().run()

    @t.override
    def start(self) -> None:
        """Waits for the child to ignore SIGINT.

        Raises ``SigintIgnoringProcessStartError`` if the child exits first.
        """
        with self._sigint_ignored, self._sigint_ignored_sender:
            super().start()
            connection.wait([self._sigint_ignored, self.sentinel])
            # Poll even after an exit, which may follow the message. The open sender
            # keeps poll() from being true at EOF.
            if not self._sigint_ignored.poll():
                # Reaped, so that exitcode is set, which the sentinel alone doesn't ensure.
                self.join()
                msg = f"Process exited during start-up ({self.exitcode})"
                raise SigintIgnoringProcessStartError(msg)
