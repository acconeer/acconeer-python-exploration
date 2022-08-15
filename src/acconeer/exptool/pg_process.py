# Copyright (c) Acconeer AB, 2022
# All rights reserved

import multiprocessing as mp
import queue
import signal
from time import sleep, time


class PGProcess:
    def __init__(self, updater, max_freq=60):
        self._queue = mp.Queue()
        self._exit_event = mp.Event()

        args = (
            self._queue,
            self._exit_event,
            updater,
            max_freq,
        )

        self._process = mp.Process(target=pg_process_program, args=args, daemon=True)

    def start(self):
        self._process.start()

    def put_data(self, data):
        if self._exit_event.is_set() or self._process.exitcode is not None:
            self.close()
            raise PGProccessDiedException

        try:
            self._queue.put(data)
        except BrokenPipeError:
            self.close()
            raise PGProccessDiedException

    def close(self):
        if self._process.exitcode is None:
            self._exit_event.set()
            self._process.join(1)

        if self._process.exitcode is None:
            self._process.terminate()
            self._process.join(1)

        if self._process.exitcode is None:
            raise RuntimeError


def pg_process_program(q, exit_event, updater, max_freq):
    from PySide6 import QtWidgets

    import pyqtgraph as pg

    signal.signal(signal.SIGINT, signal.SIG_IGN)

    app = QtWidgets.QApplication([])
    pg.setConfigOption("background", "w")
    pg.setConfigOption("foreground", "k")
    pg.setConfigOptions(antialias=True)
    win = pg.GraphicsLayoutWidget()
    win.closeEvent = lambda _: exit_event.set()

    updater.setup(win.ci)

    win.show()
    app.processEvents()

    while not exit_event.is_set():
        data = None
        try:
            data = q.get(timeout=0.1)
            while True:
                data = q.get(timeout=0.001)
        except queue.Empty:
            pass

        data_time = time()

        if data is not None:
            updater.update(data)

        app.processEvents()

        if max_freq and data is not None:
            sleep_time = 1 / max_freq - (time() - data_time)
            if sleep_time > 0.005:
                sleep(sleep_time)

    win.close()
    app.closeAllWindows()

    try:
        while True:
            q.get(timeout=0.001)
    except Exception:
        pass


class ExamplePGUpdater:
    def __init__(self):
        pass

    def setup(self, win):
        import pyqtgraph as pg

        win.setWindowTitle("PG updater example")
        self.plot = win.addPlot()
        self.curve = self.plot.plot(pen=pg.mkPen("k", width=3))

    def update(self, data):
        x, y = data
        self.curve.setData(x, y)


class PGProccessDiedException(Exception):
    pass


# Example usage:
if __name__ == "__main__":
    import numpy as np

    pg_updater = ExamplePGUpdater()
    pg_process = PGProcess(pg_updater)
    pg_process.start()

    x = np.linspace(0, 10, 100)
    t0 = time()
    t = 0
    while t < 10:
        t = time() - t0
        y = np.sin(x + t)

        try:
            pg_process.put_data([x, y])
        except PGProccessDiedException:
            exit()

        sleep(0.01)

    pg_process.close()
