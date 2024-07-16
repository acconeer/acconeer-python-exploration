# Copyright (c) Acconeer AB, 2023-2024
# All rights reserved
from __future__ import annotations

import json
import time
import typing as t

from .communication_protocol import CommunicationProtocol, Message
from .links import BufferedLink


_MessageT = t.TypeVar("_MessageT", bound=Message)


class MessageStreamError(Exception):
    pass


class MessageStream:
    """
    Helper object that automatically handles message parsing.

    This class takes no responsibility of the passed link.
    """

    def __init__(
        self,
        link: BufferedLink,
        protocol: type[CommunicationProtocol[t.Any]],
        message_handler: t.Callable[[Message], t.Any],
        link_error_callback: t.Callable[[Exception], t.Any],
    ) -> None:
        self._link = link
        self._error_callback = link_error_callback
        self._message_handler = message_handler

        self.protocol = protocol

        self._stream = self._get_stream()

    def send_command(self, command: bytes) -> None:
        try:
            self._link.send(command)
        except Exception as e:
            self._error_callback(e)

    def wait_for_message(
        self,
        message_type: type[_MessageT],
        timeout_s: t.Optional[float] = None,
    ) -> _MessageT:
        """Retrieves and applies messages until a message of type ``message_type`` is encountered.

        :param message_type: a subclass of ``Message``
        :param message_handler: Function that handles messages received that aren't of ``message_type``
        :param timeout_s: Limit the time spent in this function
        :raises MessageStreamError:
            if timeout_s is set and that amount of time has elapsed
            without predicate evaluating to True
        """
        deadline = None if (timeout_s is None) else time.monotonic() + timeout_s

        for message in self._stream:
            if type(message) is message_type:
                return message
            else:
                self._message_handler(message)

            if deadline is not None and time.monotonic() > deadline:
                msg = f"Deadline was reached without finding message of type {message_type.__name__!r}"
                raise MessageStreamError(msg)

        msg = "No messages to consume"
        raise MessageStreamError(msg)

    def _get_stream(self) -> t.Iterator[Message]:
        """returns an iterator of parsed messages"""
        while True:
            try:
                header_in_bytes = self._link.recv_until(self.protocol.end_sequence)
            except Exception as e:
                self._error_callback(e)

            try:
                header: dict[str, t.Any] = json.loads(header_in_bytes)
            except json.JSONDecodeError:
                self._error_callback(RuntimeError(f"Cannot decode header {header_in_bytes!r}"))

            try:
                payload_size = header["payload_size"]
            except KeyError:
                payload = bytes()
            else:
                try:
                    payload = self._link.recv(payload_size)
                except Exception as e:
                    self._error_callback(e)

            resp = self.protocol.parse_message(header, payload)
            yield resp
