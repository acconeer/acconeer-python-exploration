# Copyright (c) Acconeer AB, 2022
# All rights reserved

import multiprocessing as mp
import queue
import signal
import sys
from time import sleep, time

import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation


class PlotProcess:
    def __init__(self, fig_updater, interval=10):
        self._queue = mp.Queue()
        self._exit_event = mp.Event()

        args = (
            self._queue,
            self._exit_event,
            fig_updater,
            interval / 1000.0,
        )

        self._process = mp.Process(target=plot_process_program, args=args, daemon=True)

    def start(self):
        self._process.start()

    def put_data(self, data):
        if self._process.exitcode is not None:
            self.close()
            raise PlotProccessDiedException

        try:
            self._queue.put(data)
        except BrokenPipeError:
            self.close()
            raise PlotProccessDiedException

    def close(self):
        if self._process.exitcode is None:
            self._exit_event.set()
            self._process.join(1)

        if self._process.exitcode is None:
            self._process.terminate()
            self._process.join(1)

        if self._process.exitcode is None:
            raise RuntimeError


def plot_process_program(q, exit_event, fig_updater, interval):
    signal.signal(signal.SIGINT, signal.SIG_IGN)

    last_t = None
    artists = []
    fig = plt.figure()

    def anim_func(frame):
        nonlocal artists, last_t

        if exit_event.is_set():
            sys.exit()

        if last_t:
            now = time()
            sleep_t = (last_t + interval - 0.001) - now
            if sleep_t > 0.001:
                sleep(sleep_t)
        last_t = time()

        data = None
        while True:
            try:
                data = q.get(timeout=0.001)
            except queue.Empty:
                break

        if data is not None:
            if not artists:
                artists = fig_updater.first(data)
            else:
                fig_updater.update(data)

        return artists

    fig_updater.setup(fig)
    anim = FuncAnimation(fig, anim_func, interval=0, blit=True)  # noqa: F841

    try:
        plt.show()
    except AttributeError:
        pass


class PlotProccessDiedException(Exception):
    pass


class FigureUpdater:
    def setup(self, fig):
        self.fig = fig

    def first(self, data):
        return []  # iterable of artists

    def update(self, data):
        pass


class ExampleFigureUpdater(FigureUpdater):
    def setup(self, fig):
        self.fig = fig
        self.ax = fig.subplots()
        self.ax.set_xlabel("t")
        self.ax.set_ylabel("sin(t)")

    def first(self, data):
        x, y = data
        self.line = self.ax.plot(x, y)[0]
        return [self.line]

    def update(self, data):
        x, y = data
        self.line.set_ydata(y)


# Example usage:
if __name__ == "__main__":
    import numpy as np

    fu = ExampleFigureUpdater()
    pp = PlotProcess(fu)
    pp.start()

    x = np.linspace(0, 10, 100)
    t0 = time()
    t = 0
    while t < 10:
        t = time() - t0
        y = np.sin(x + t)

        try:
            pp.put_data([x, y])
        except PlotProccessDiedException:
            exit()

        sleep(0.001)  # not necessary

    pp.close()
