from __future__ import annotations

import logging
import multiprocessing as mp
import queue
from typing import Any, Dict, Tuple, Union

from ._message import Message
from ._model import Model
from ._types import Task


log = logging.getLogger(__name__)

CommandKwargs = Dict[str, Any]
Command = Tuple[str, Union[Task, CommandKwargs, None]]


class Backend:
    def __init__(self):
        self._recv_queue: mp.Queue[Message] = mp.Queue()
        self._send_queue: mp.Queue[Command] = mp.Queue()
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
        log.debug("Backend starting ...")
        self._process.start()

    def stop(self):
        log.debug("Backend stopping ...")
        self._stop_event.set()
        self._send(("stop", {}))
        self._process.join()
        self._process.close()

    def put_task(self, task: Task) -> None:
        self._send(("task", task))

    def set_idle_task(self, task: Task) -> None:
        log.debug(f"Backend is setting idle task {task} ...")
        self._send(("set_idle_task", task))

    def clear_idle_task(self):
        log.debug("Backend cleared its idle task ...")
        self._send(("set_idle_task", None))

    def _send(self, command: Command) -> None:
        self._send_queue.put(command)

    def recv(self) -> Any:
        return self._recv_queue.get()


def process_program(recv_queue, send_queue, stop_event):
    try:
        model = Model()
        idle_task = None

        while not stop_event.is_set():
            if idle_task is None:
                msg = recv_queue.get()
                log.debug(f"Backend received the command: {msg}")
            else:
                try:
                    msg = recv_queue.get_nowait()
                    log.debug(f"Backend received the command: {msg}")
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
