# Copyright (c) Acconeer AB, 2022
# All rights reserved

from __future__ import annotations

import logging
import multiprocessing as mp
import queue
import time
import traceback
import uuid
from multiprocessing.synchronize import Event as mp_EventType  # NOTE! this is not mp.Event.
from typing import Any, Dict, Optional, Tuple, Union

import attrs
import psutil
from typing_extensions import Literal

from ._backend_logger import BackendLogger
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
    def __init__(self) -> None:
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

    def start(self) -> None:
        log.debug("Backend starting ...")
        self._process.start()

    def stop(self) -> None:
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
    stop_event: mp_EventType,
) -> None:
    MAX_POLL_INTERVAL = 0.5

    process = psutil.Process()
    process.cpu_percent()
    last_cpu_msg_time = time.monotonic()

    try:
        BackendLogger.set_callback(send_queue.put)
        process_log = BackendLogger.getLogger(__name__)
        model = Model(task_callback=send_queue.put)
        model_wants_to_idle = False

        while not stop_event.is_set():
            now = time.monotonic()
            if now - last_cpu_msg_time > MAX_POLL_INTERVAL:
                last_cpu_msg_time = now
                cpu_percent = round(process.cpu_percent())
                send_queue.put(
                    GeneralMessage(
                        name="cpu_percent",
                        data=cpu_percent,
                    )
                )

            msg = None

            if not model_wants_to_idle:
                try:
                    msg = recv_queue.get(timeout=MAX_POLL_INTERVAL)
                except queue.Empty:
                    continue

                process_log.debug(f"Backend received the command: {msg}")
            else:
                try:
                    msg = recv_queue.get_nowait()
                    process_log.debug(f"Backend received the command: {msg}")
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
