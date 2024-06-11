# Copyright (c) Acconeer AB, 2023-2024
# All rights reserved
"""
This module defines the primitives of an event system.
The event system consists of 2 distinct types of actors;
the EventBroker and Services.

The EventBroker provides a publisher/subscriber implementation
for Services.

A consumer-Service subscribes to topics of interest
(in the variable INTERESTS) and then declares its interests to the
EventBroker by installing itself (EventBroker.install_service).

A producer-Service offers events of arbitrary type to the
EventBroker which will in turn dispatch that event to any
interested consumer Services.

Producer Services may want to put an unique identifiers
on its events so that consumers are able to tell events from
different producers apart (this allows duplicated producer services).
This is done via 'EventBroker.install_identified_service'.
"""

from __future__ import annotations

import collections
import contextlib
import itertools
import logging
import typing as t
from copy import copy

import attrs
import typing_extensions as te


log = logging.getLogger(__name__)


class Service(te.Protocol):
    INTERESTS: t.ClassVar[set[type]]
    """Defines what events this service is interested in"""

    description: t.ClassVar[str]
    """A description that explains the block"""

    window_title: str
    """The window title"""

    uninstall_function: t.Callable[[], None]
    """Uninstalls this service from the EventBroker (returned when installing)"""

    def handle_event(self, event: t.Any) -> None:
        """
        Handles an incoming event.
        'event' can be of any type defined in INTERESTS.
        """
        ...


class _IdLedger:
    def __init__(self) -> None:
        self._taken_ids: set[str] = set()

    def borrow_numbered_id(self, prefix: str) -> str:
        for serial_number in itertools.count(1):
            candidate = f"{prefix}-{serial_number}"
            if candidate not in self._taken_ids:
                self._taken_ids.add(candidate)
                return candidate

        # since itertools.count returns an infinite iterator,
        # we should never end up here.
        raise RuntimeError

    def borrow_id(self, id_: str) -> str:
        if id_ in self._taken_ids:
            return self.borrow_numbered_id(id_)
        else:
            self._taken_ids.add(id_)
            return id_

    def return_id(self, id_: str) -> None:
        self._taken_ids.remove(id_)


@attrs.frozen
class IdentifiedServiceUninstalledEvent:
    """
    This event is offered when an identified service is removed,
    allowing consumers to clean up resources related to that
    identified service.
    """

    id_: str


@attrs.frozen
class ChangeIdEvent:
    old_id: str
    new_id: str


class EventBroker:
    def __init__(self, event_log_capacity: int = 100) -> None:
        self._topic_callbacks: dict[type, list[t.Callable[[t.Any], None]]] = {}
        self._event_log: collections.deque[t.Any] = collections.deque(maxlen=event_log_capacity)
        self._id_pool = _IdLedger()

    def install_service(self, service: Service) -> None:
        """
        Installs a service, subscribing its handle_event to
        all topics in INTERESTS

        returns a function that uninstalls the passed service
        """
        for interest in service.INTERESTS:
            self._topic_callbacks.setdefault(interest, []).append(service.handle_event)

    def uninstall_service(self, service: Service) -> None:
        log.debug(f"Uninstalling service of type {type(service)}")

        for interest in service.INTERESTS:
            with contextlib.suppress(KeyError, ValueError):
                self._topic_callbacks[interest].remove(service.handle_event)

    def change_id(self, new_id: str, old_id: str) -> str:
        new_id = self._id_pool.borrow_id(new_id)

        self._id_pool.return_id(old_id)

        return new_id

    def install_identified_service(self, service: Service, prefix: str) -> str:
        """
        Installs a service that requires an id, subscribing its handle_event to
        all topics in INTERESTS

        returns a function that uninstalls the passed service and the id
        """
        service_id = self._id_pool.borrow_numbered_id(prefix)

        for interest in service.INTERESTS:
            self._topic_callbacks.setdefault(interest, []).append(service.handle_event)

        return service_id

    def uninstall_identified_service(self, service: Service, service_id: str) -> None:
        self.uninstall_service(service)

        self._id_pool.return_id(service_id)

        self.offer_event(IdentifiedServiceUninstalledEvent(service_id))

    def brief_service(self, service: Service) -> None:
        """
        Briefs the service by calling its handle_event with
        the most recent interesting events.
        """
        for event in self._event_log:
            if type(event) in service.INTERESTS:
                service.handle_event(event)

    def offer_event(self, event: t.Any) -> None:
        """
        Offer an event to interested services
        """
        log.debug(f"event with type {type(event)} was offered")
        subscribers_of_event = copy(self._topic_callbacks.get(type(event), []))

        self._event_log.append(event)

        if subscribers_of_event:
            for subscriber in subscribers_of_event:
                subscriber(event)
        else:
            log.debug(f"No subscribers of event with type {type(event)}")
