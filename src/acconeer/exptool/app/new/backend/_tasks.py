# Copyright (c) Acconeer AB, 2023-2024
# All rights reserved

from __future__ import annotations

import types
import typing as t

import typing_extensions as te
from typing_extensions import Concatenate as C


#              name kwargs
Task = t.Tuple[str, t.Dict[str, t.Any]]

_TaskSender = t.Callable[[Task], t.Any]
_R = t.TypeVar("_R")
_T = t.TypeVar("_T")
_P = te.ParamSpec("_P")


class _TaskDescriptor(t.Generic[_P, _R]):
    def __init__(self, method: t.Callable[C[t.Any, _P], _R]) -> None:
        self._method = method
        self._task_name: t.Optional[str] = None
        setattr(self._method, "is_task", True)

    def __set_name__(self, owner: t.Type[t.Any], name: str) -> None:
        self._task_name = name

    @t.overload
    def __get__(self, obj: None, objtype: t.Any = ...) -> te.Self: ...

    @t.overload
    def __get__(self, obj: t.Any, objtype: t.Any = ...) -> t.Callable[_P, _R]: ...

    def __get__(
        self, obj: t.Optional[t.Any], objtype: t.Any = None
    ) -> t.Union[te.Self, t.Callable[_P, _R]]:
        """If called with an instance, bind and return the wrapped function"""
        if obj is None:
            return self
        else:
            bound_method = types.MethodType(self._method, obj)
            return bound_method

    def rpc(self, task_sender: _TaskSender, *args: _P.args, **kwargs: _P.kwargs) -> None:
        if self._task_name is None:
            raise RuntimeError

        if args != ():
            msg = "An RPC must be called with kwargs only."
            raise ValueError(msg)

        task_sender((self._task_name, kwargs))


def is_task(m: t.Callable[C[t.Any, _P], _R]) -> _TaskDescriptor[_P, _R]:
    """
    Task method decorator

    The decorated method gets wrapped in a descriptor and works normally on the surface:

        class Foo:
            @is_task
            def my_task(self, *, n: int) -> None:
                ...

        Foo().my_task(n=5)

    The decorator also provides a rpc member "of the method":

        class FooView:
            def on_some_event(self):
                Foo.my_task.rpc(<task_sender>, n=5)

    Which will construct and send a Task with <task_sender>.

    <task_sender> should be AppModel.put_task in most cases.
    """
    return _TaskDescriptor(m)


def _has_task_marker(obj: object) -> bool:
    return getattr(obj, "is_task", False)


def get_task(obj: t.Any, name: str) -> t.Optional[t.Callable[..., t.Any]]:
    """
    Gets the task method "<name>" of the obj.
    If obj does not have a task named "<name>", None is returned.
    """
    task_method = getattr(obj, name, None)
    if _has_task_marker(task_method):
        return task_method
    else:
        return None


def get_task_names(obj: object) -> list[str]:
    """
    Gets the names of all tasks defined on 'obj'
    """
    return [
        name
        for name in dir(obj)
        if _has_task_marker(getattr(obj, name, None)) and not name.startswith("_task_method_")
    ]
