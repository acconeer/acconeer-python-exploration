from __future__ import annotations

import platform
from typing import TYPE_CHECKING, Any

from PySide6.QtCore import QObject, QThread, QTimerEvent, Signal, Slot


if not TYPE_CHECKING:
    from acconeer.exptool.utils import get_tagged_serial_ports, get_usb_devices


class PortUpdater(QObject):
    sig_serial_update = Signal(object)
    sig_usb_update = Signal(object)

    class Worker(QObject):
        sig_serial_update = Signal(object)
        sig_usb_update = Signal(object)

        @Slot()
        def start(self):
            self.timer_id = self.startTimer(500)

        @Slot()
        def stop(self):
            self.killTimer(self.timer_id)

        def timerEvent(self, event: QTimerEvent) -> None:
            tagged_ports = get_tagged_serial_ports()  # type: ignore[name-defined]
            self.sig_serial_update.emit(tagged_ports)
            if platform.system().lower() == "windows":
                usb_devices = get_usb_devices()  # type: ignore[name-defined]
                self.sig_usb_update.emit(usb_devices)

    def __init__(self, parent: QObject) -> None:
        super().__init__(parent)

        self.thread = QThread(self)
        self.worker = self.Worker()
        self.thread.started.connect(self.worker.start)
        self.thread.finished.connect(self.worker.stop)
        self.worker.sig_serial_update.connect(self._on_serial_update)
        self.worker.sig_usb_update.connect(self._on_usb_update)
        self.worker.moveToThread(self.thread)

    def start(self) -> None:
        self.thread.start()

    def stop(self) -> None:
        self.thread.quit()
        self.thread.wait()

    def _on_serial_update(self, obj: Any) -> None:
        self.sig_serial_update.emit(obj)

    def _on_usb_update(self, obj: Any) -> None:
        self.sig_usb_update.emit(obj)
