from __future__ import annotations

import multiprocessing as mp
import queue
from typing import Any, Tuple

from ._model import Model


class Backend:
    def __init__(self):
        self._recv_queue: mp.Queue = mp.Queue()
        self._send_queue: mp.Queue = mp.Queue()
        self._stop_event = mp.Event()
        self._process = mp.Process(
            target=process_program,
            args=(
                self._send_queue,
                self._recv_queue,
                self._stop_event,
            ),
            daemon=True,
        )

    def start(self):
        self._process.start()

    def stop(self):
        self._stop_event.set()
        self._send(("stop", None))
        self._process.join()
        self._process.close()

    def put_task(self, task):
        self._send(("task", task))

    def set_idle_task(self, task):
        self._send(("set_idle_task", task))

    def clear_idle_task(self):
        self._send(("set_idle_task", None))

    def _send(self, message: Tuple[str, Any]) -> None:
        self._send_queue.put(message)

    def recv(self) -> Any:
        return self._recv_queue.get()


def process_program(recv_queue, send_queue, stop_event):
    try:
        model = Model()
        idle_task = None

        while not stop_event.is_set():
            if idle_task is None:
                msg = recv_queue.get()
            else:
                try:
                    msg = recv_queue.get_nowait()
                except queue.Empty:
                    msg = ("task", idle_task)

            cmd, arg = msg

            if cmd == "stop":
                break

            if cmd == "task":
                model.execute_task(arg)
            elif cmd == "set_idle_task":
                idle_task = arg
            else:
                raise RuntimeError
    finally:
        recv_queue.close()
        send_queue.close()