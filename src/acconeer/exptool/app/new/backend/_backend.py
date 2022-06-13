from __future__ import annotations

import logging
import multiprocessing as mp
import queue
from typing import Any, Dict, Optional, Tuple, Type, Union

from ._backend_plugin import BackendPlugin
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

        self._process.join(timeout=3)

        if self._process.exitcode is None:
            log.warning("Backend process join timed out, killing...")

            self._process.kill()
            self._process.join(timeout=1)

        if self._process.exitcode is None:
            raise RuntimeError

        self._process.close()

    def put_task(self, task: Task) -> None:
        self._send(("task", task))

    def set_idle_task(self, task: Task) -> None:
        log.debug(f"Backend is setting idle task {task} ...")
        self._send(("set_idle_task", task))

    def clear_idle_task(self):
        log.debug("Backend cleared its idle task ...")
        self._send(("set_idle_task", None))

    def load_plugin(self, plugin: Type[BackendPlugin]) -> None:
        self.put_task(("load_plugin", {"plugin": plugin}))

    def unload_plugin(self) -> None:
        self.put_task(("unload_plugin", {}))

    def _send(self, command: Command) -> None:
        self._send_queue.put(command)

    def recv(self, timeout: Optional[float] = None) -> Message:
        return self._recv_queue.get(timeout=timeout)


def process_program(
    recv_queue: mp.Queue[Command],
    send_queue: mp.Queue[Message],
    stop_event: mp._EventType,
) -> None:
    try:
        model = Model(task_callback=send_queue.put)
        idle_task = None

        while not stop_event.is_set():
            if idle_task is None:
                log.debug("Backend is waiting patiently for a new command ...")
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
            elif cmd == "task":
                if not isinstance(arg, tuple):
                    log.warn(
                        f"'task' argument is malformed: {arg}. "
                        + "Should be a tuple[str, dict[str, Any]]."
                    )
                    continue
                model.execute_task(task=arg)
            elif cmd == "set_idle_task":
                idle_task = arg
            else:
                raise RuntimeError

            log.debug("Backend successfully processed the command:")
            log.debug(f"  {msg}")
    finally:
        recv_queue.close()
        send_queue.close()
