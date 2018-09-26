import multiprocessing as mp
import queue
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation
from time import sleep


class PlotProcess(mp.Process):
    def __init__(self, fig_updater, interval=10):
        self.queue = mp.Queue()
        self.lock = mp.Lock()
        self.exit_event = mp.Event()

        args = (self.queue, self.lock, self.exit_event, fig_updater, interval)
        super().__init__(target=PlotProcessProgram, args=args, daemon=True)

    def start(self):
        super().start()
        sleep(0.5)  # make sure the process has time to start before returning

    def put_data(self, data):
        self.lock.acquire()
        while not self.queue.empty():  # clear queue
            self.queue.get()
        if self.exit_event.is_set() or not self.is_alive():
            raise PlotProccessDiedException()
        self.queue.put(data)
        self.lock.release()

    def close(self):
        if self.is_alive():
            self.exit_event.set()
            self.join()

        # note:
        #  - queue must be empty prior to joining
        #  - is_alive will join if process is dead


class PlotProcessProgram:
    def __init__(self, queue, lock, exit_event, fig_updater, interval):
        self.queue = queue
        self.lock = lock
        self.exit_event = exit_event
        self.fig_updater = fig_updater

        self.artists = []
        self.first = True
        self.fig = plt.figure()
        self.fig_updater.setup(self.fig)
        self.anim = FuncAnimation(self.fig, self.anim_func, interval=interval, blit=True)

        try:
            plt.show()
        except AttributeError:
            pass
        finally:
            self.close()

    def get_data(self):
        data = None
        exit_flag = False
        self.lock.acquire()
        if self.exit_event.is_set():
            exit_flag = True
        else:
            try:
                data = self.queue.get(block=False)
            except queue.Empty:
                pass
        self.lock.release()
        return data, exit_flag

    def anim_func(self, frame):
        data, exit_flag = self.get_data()

        if exit_flag:
            plt.close()
            return []

        if data is not None:
            if self.first:
                self.first = False
                self.artists = self.fig_updater.first(data)
            else:
                self.fig_updater.update(data)

        return self.artists

    def close(self):
        self.lock.acquire()
        self.exit_event.set()
        while not self.queue.empty():
            self.queue.get()
        self.lock.release()


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
        self.line = self.ax.plot(x, y, animated=True)[0]
        return [self.line]

    def update(self, data):
        x, y = data
        self.line.set_ydata(y)


# Example usage:
if __name__ == "__main__":
    from time import time
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
