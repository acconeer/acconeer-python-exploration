# Copyright (c) Acconeer AB, 2022
# All rights reserved

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from PySide6.QtCore import QObject, QThread, QTimerEvent, Signal, Slot


if not TYPE_CHECKING:
    from acconeer.exptool.utils import get_serial_devices, get_usb_devices


class PortUpdater(QObject):
    sig_update = Signal(object, object)

    class Worker(QObject):
        sig_update = Signal(object, object)
        serial_devices: Any = None
        usb_devices: Any = None

        @Slot()  # type: ignore[misc]
        def start(self) -> None:
            self.timer_id = self.startTimer(500)

        @Slot()  # type: ignore[misc]
        def stop(self) -> None:
            self.killTimer(self.timer_id)

        def timerEvent(self, event: QTimerEvent) -> None:
            serial_devices = get_serial_devices()  # type: ignore[name-defined]
            usb_devices = get_usb_devices()  # type: ignore[name-defined]

            if self.serial_devices != serial_devices or self.usb_devices != usb_devices:
                self.serial_devices = serial_devices
                self.usb_devices = usb_devices
                self.sig_update.emit(serial_devices, usb_devices)

    def __init__(self, parent: QObject) -> None:
        super().__init__(parent)

        self.thread = QThread(self)
        self.worker = self.Worker()
        self.thread.started.connect(self.worker.start)
        self.thread.finished.connect(self.worker.stop)
        self.worker.sig_update.connect(self._on_update)
        self.worker.moveToThread(self.thread)
        self.signalling = False

    def start(self) -> None:
        self.thread.start()
        self.signalling = True

    def stop(self) -> None:
        self.thread.quit()
        self.thread.wait()
        self.signalling = False

    def pause(self) -> None:
        self.signalling = False

    def resume(self) -> None:
        self.signalling = True

    def _on_update(self, serial: Any, usb: Any) -> None:
        if self.signalling:
            self.sig_update.emit(serial, usb)
