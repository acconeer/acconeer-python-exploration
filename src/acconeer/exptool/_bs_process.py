# Copyright (c) Acconeer AB, 2022
# All rights reserved

import multiprocessing as mp
import queue
import signal
import time


class BSProccessDiedException(Exception):
    pass


class BSProcess:
    def __init__(self, updater):
        self._queue = mp.Queue()
        self._exit_event = mp.Event()

        args = (
            self._queue,
            self._exit_event,
            updater,
        )

        self._process = mp.Process(target=_bs_process_program, args=args, daemon=True)

    def start(self):
        self._process.start()

    def put_data(self, data):
        if self._exit_event.is_set() or self._process.exitcode is not None:
            self.close()
            raise BSProccessDiedException

        try:
            self._queue.put(data)
        except BrokenPipeError:
            self.close()
            raise BSProccessDiedException

    def close(self):
        if self._process.exitcode is None:
            self._exit_event.set()
            self._process.join(1)

        if self._process.exitcode is None:
            self._process.terminate()
            self._process.join(1)

        if self._process.exitcode is None:
            raise RuntimeError


def _bs_process_program(q, exit_event, updater):
    try:
        from blinkstick import blinkstick
    except ImportError:
        pass

    signal.signal(signal.SIGINT, signal.SIG_IGN)

    FIND_ATTEMPT_INTERVAL = 0.5
    UPDATE_INTERVAL = 1 / 30

    last_find_attempt_time = -1.0
    last_update_time = -1.0
    stick = None
    data = None
    data_index = -1

    while not exit_event.is_set():
        try:
            data = q.get(timeout=0.001)
        except queue.Empty:
            pass
        else:
            data_index += 1

        if stick is None:
            now = time.time()

            if (now - last_find_attempt_time) > FIND_ATTEMPT_INTERVAL:
                last_find_attempt_time = now

                try:
                    stick = blinkstick.find_first()
                    stick.turn_off()
                    stick.pulse(blue=100, duration=100, steps=10, repeats=2)
                except Exception:
                    stick = None

        if stick is None:
            continue

        now = time.time()

        if (now - last_update_time) < UPDATE_INTERVAL:
            continue

        last_update_time = now

        try:
            if data_index < 0:
                stick.turn_off()
            else:
                updater.update(data, data_index, now, stick)
        except blinkstick.BlinkStickException:
            stick = None

    if stick is not None:
        try:
            stick.turn_off()
        except Exception:
            pass

    try:
        while True:
            q.get(timeout=0.001)
    except Exception:
        pass


class _ExampleBSUpdater:
    def update(self, data, data_index, t, stick):
        x = float(data)
        stick.set_color(red=50 * (1 - x), index=0)
        stick.set_color(blue=50 * x, index=1)


if __name__ == "__main__":
    bs_updater = _ExampleBSUpdater()
    bs_process = BSProcess(bs_updater)
    bs_process.start()

    t0 = time.time()
    t = 0
    while t < 5:
        t = time.time() - t0
        y = t % 1.0 > 0.5

        try:
            bs_process.put_data(y)
        except BSProccessDiedException:
            exit()

        time.sleep(0.01)

    bs_process.close()
