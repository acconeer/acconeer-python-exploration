# Copyright (c) Acconeer AB, 2022
# All rights reserved

from __future__ import annotations

import logging
import multiprocessing as mp
import queue
import traceback
import uuid
from typing import Any, Dict, Optional, Tuple, Union

import attrs
from typing_extensions import Literal

from ._message import GeneralMessage, Message
from ._model import Model


log = logging.getLogger(__name__)


@attrs.frozen
class ClosedTask:
    key: uuid.UUID = attrs.field()
    exception: Optional[Exception] = attrs.field(default=None)
    traceback_format_exc: Optional[str] = attrs.field(default=None)


TaskName = str
TaskPlugin = bool
TaskKwargs = Dict[str, Any]
Task = Tuple[TaskName, TaskKwargs, TaskPlugin]

ToBackendQueueItem = Union[
    Tuple[Literal["stop"], None],
    Tuple[Literal["task"], Tuple[uuid.UUID, Task]],
]
FromBackendQueueItem = Union[Message, ClosedTask]


class Backend:
    def __init__(self):
        self._recv_queue: mp.Queue[FromBackendQueueItem] = mp.Queue()
        self._send_queue: mp.Queue[ToBackendQueueItem] = mp.Queue()
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
        self._send(("stop", None))

        self._process.join(timeout=3)

        if self._process.exitcode is None:
            log.warning("Backend process join timed out, killing...")

            self._process.kill()
            self._process.join(timeout=1)

        if self._process.exitcode is None:
            raise RuntimeError

        self._process.close()

    def put_task(self, task: Task) -> uuid.UUID:
        key = uuid.uuid4()
        self._send(("task", (key, task)))
        return key

    def _send(self, item: ToBackendQueueItem) -> None:
        self._send_queue.put(item)

    def recv(self, timeout: Optional[float] = None) -> FromBackendQueueItem:
        return self._recv_queue.get(timeout=timeout)


def process_program(
    recv_queue: mp.Queue[ToBackendQueueItem],
    send_queue: mp.Queue[FromBackendQueueItem],
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
                try:
                    model_wants_to_idle = model.idle()
                except Exception as exc:
                    model_wants_to_idle = False
                    send_queue.put(
                        GeneralMessage(
                            name="error",
                            exception=exc,
                            traceback_format_exc=traceback.format_exc(),
                        )
                    )

                continue

            cmd, maybe_key_and_task = msg

            if cmd == "stop":
                break
            elif cmd == "task":
                assert maybe_key_and_task is not None

                key, task = maybe_key_and_task
                name, kwargs, plugin = task

                try:
                    model.execute_task(name, kwargs, plugin)
                except Exception as exc:
                    send_queue.put(ClosedTask(key, exc, traceback.format_exc()))
                else:
                    send_queue.put(ClosedTask(key))

                model_wants_to_idle = True
            else:
                raise RuntimeError
    finally:
        recv_queue.close()
        send_queue.close()
