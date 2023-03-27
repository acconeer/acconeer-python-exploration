# Copyright (c) Acconeer AB, 2023
# All rights reserved

"""
Pidget- & PidgetGroup hooks

This module defines closures and higher order functions that
allows declarative definition of Pidget- & PidgetGroup hooks.

It's still possible to use any function that adheres to respective type.

The definitions of these hooks are placed in ``pidget_groups.py`` and
``pidgets.py``, respectively.

.. code-block:: python
    PidgetGroupHook = t.Callable[
        [QWidget, t.Mapping[str, Pidget]], None
    ]
    PidgetHook = Callable[
        ["Pidget", Mapping[str, "Pidget"]], None
    ]

A ``PidgetGroupHook`` is a function that accepts a ``QWidget`` instance
and a ``Mapping[str, Pidget]`` and returns nothing.
The ``QWidget`` instance is the container widget returned by the
``get_container`` function of the ``PidgetGroup``.

.. code-block:: python
    def my_hook(pg: QWidget, mapping: Mapping[str, Pidget]) -> None:
        print(pg)  # pg will be the "a" variable below

    a = PidgetGroup(
        hooks=my_hook,
        # or hooks=[my_hook]
        # or hooks=(my_hook,)
    )

The second argument of a ``PidgetGroupHook`` is the ``PidgetMapping`` kept
internally in ``AttrsConfigEditor``;

.. code-block:: python
    def my_hook(pg: QWidget, mapping: Mapping[str, Pidget]) -> None:
        print(mapping)
        # mapping will be:
        # {
        #     # Note: these are the actual pidgets!
        #     "int_parameter": IntPidget()
        #     "float_parameter": FloatPidget()
        # }
        #

    mapping: PidgetGroupFactoryMapping = {
        PidgetGroup(hooks=my_hook): {
            "int_parameter": IntPidgetFactory(...),
            "float_parameter": FloatPidgetFactory(...),
        }
    }

P.S. The functionality is analogous in ``PidgetHook``, but the
actual ``Pidget`` the hook is attached to is the first argument of the hook.


This means that the hook has access to any pidget in a ``AttrsConfigEditor``,
allowing for interesting combinations!
"""
from __future__ import annotations

import typing as t

from PySide6.QtWidgets import QWidget

from .pidget_groups import PidgetGroupHook
from .pidgets import Pidget, PidgetHook


PidgetMapping = t.Mapping[str, Pidget]
GeneralHook = t.Union[PidgetHook, PidgetGroupHook]

PidgetMappingPredicate = t.Callable[[PidgetMapping], bool]


def parameter_equals(aspect: str, value: t.Any) -> PidgetMappingPredicate:
    """Checks whether the parameter of the pidget assigned to aspect is equal to value"""

    def inner(mapping: PidgetMapping) -> bool:
        return bool(mapping[aspect].get_parameter() == value)

    return inner


def parameter_is(aspect: str, value: t.Any) -> PidgetMappingPredicate:
    """Checks whether the parameter of the pidget assigned to aspect "is" passed value
    Should be used with singletons like "True", "False", "None", etc.
    """

    def inner(mapping: PidgetMapping) -> bool:
        return mapping[aspect].get_parameter() is value

    return inner


def parameter_within(aspect: str, range: t.Tuple[float, float]) -> PidgetMappingPredicate:
    """Checks whether the parameter of the pidget assigned to aspect is in range"""

    def inner(mapping: PidgetMapping) -> bool:
        lower, higher = range
        return bool(lower < mapping[aspect].get_parameter() < higher)

    return inner


def enable_if(predicate: PidgetMappingPredicate) -> GeneralHook:
    """Enables the instance this hook is assigned to if the predicate evaluates to "True" """

    def inner(inst: QWidget, mapping: PidgetMapping) -> None:
        inst.setEnabled(predicate(mapping))

    return inner


def disable_if(predicate: PidgetMappingPredicate) -> GeneralHook:
    """Negation of "enable_if" """

    def inner(inst: QWidget, mapping: PidgetMapping) -> None:
        inst.setEnabled(not predicate(mapping))

    return inner
