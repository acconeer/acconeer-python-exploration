# Copyright (c) Acconeer AB, 2026
# All rights reserved
from __future__ import annotations

import typing as t

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal


_T = t.TypeVar("_T")


def _reraise(e: Exception) -> None:
    raise e


class BGTask(QRunnable):
    class Signals(QObject):
        sig_return = Signal(object)  # _T
        sig_exception = Signal(Exception)

    @classmethod
    def create_task(
        cls,
        f: t.Callable[..., _T],
        args: tuple[t.Any, ...],
        return_cb: t.Callable[[_T], t.Any],
        exception_cb: t.Callable[[Exception], t.Any] = _reraise,
    ) -> None:
        signals = BGTask.Signals()
        signals.sig_return.connect(return_cb)
        signals.sig_exception.connect(exception_cb)

        QThreadPool.globalInstance().start(BGTask(f, args, signals))

    def __init__(self, f: t.Callable[..., _T], args: tuple[t.Any, ...], signals: Signals) -> None:
        super().__init__()
        self.signals = signals
        self.f = f
        self.args = args

    def run(self) -> None:
        try:
            res = self.f(*self.args)
        except Exception as e:
            self.signals.sig_exception.emit(e)
        else:
            self.signals.sig_return.emit(res)
