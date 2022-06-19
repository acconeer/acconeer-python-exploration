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

    def load_plugin(self, plugin: Type[BackendPlugin], key: str) -> None:
        self.put_task(("load_plugin", {"plugin": plugin, "key": key}))

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
        model_wants_to_idle = False

        while not stop_event.is_set():
            msg = None

            if not model_wants_to_idle:
                log.debug("Backend is waiting patiently for a new command ...")
                msg = recv_queue.get()
                log.debug(f"Backend received the command: {msg}")
            else:
                try:
                    msg = recv_queue.get_nowait()
                    log.debug(f"Backend received the command: {msg}")
                except queue.Empty:
                    pass

            if msg is None:  # Model wanted idle and nothing in queue
                model_wants_to_idle = model.idle()
                continue

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
                model_wants_to_idle = True
            else:
                raise RuntimeError
    finally:
        recv_queue.close()
        send_queue.close()
