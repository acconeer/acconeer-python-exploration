# Copyright (c) Acconeer AB, 2024
# All rights reserved
from __future__ import annotations

import functools
import logging
import typing as t

from PySide6.QtWidgets import QWidget

from acconeer.exptool.app.new.app_model.app_model import AppModel
from acconeer.exptool.app.new.ui.misc import ExceptionWidget


_LOG = logging.getLogger(__name__)


class _UiMethodDecoratingMeta(type):
    """Metaclasses are to classes what classes are to instances.

    - A class defines how the instance should be created
    - A metaclass defines how the class should be created

    A metaclass is used to implement ``abc.ABC``, which checks that subclasses implement
    all methods previously marked with ``@abc.abstractmethod``.

    This metaclass wraps all callable members (i.e. defined methods) in
    subclasses with the ExceptionWidget context manager, making any Exception originating
    from plugins' ViewPlugin or PlotPlugin show as a pop-up instead of in the terminal.
    """

    @staticmethod
    def __try_unload_plugin_and_reraise(f: t.Callable[..., t.Any]) -> t.Callable[..., t.Any]:
        @functools.wraps(f)
        def wrapper(instance: t.Any, *args: t.Any, **kwargs: t.Any) -> t.Any:
            try:
                if isinstance(f, staticmethod):
                    return f(*args, **kwargs)
                else:
                    return f(instance, *args, **kwargs)
            except Exception as e:
                if isinstance(instance, UiPluginBase):
                    instance.panic()
                else:
                    _LOG.error(
                        f"First argument of {f} was not an instance of UiPluginBase (was {type(instance)}), cannot unload plugin."
                    )
                raise e

        return wrapper

    @staticmethod
    def __popup_on_exception(f: t.Callable[..., t.Any]) -> t.Callable[..., t.Any]:
        @functools.wraps(f)
        def wrapper(*args: t.Any, **kwargs: t.Any) -> t.Any:
            with ExceptionWidget.context():
                return f(*args, **kwargs)

        return wrapper

    def __new__(cls, name: str, bases: tuple[type, ...], dct: dict[str, t.Any]) -> t.Any:
        return super().__new__(
            cls,
            name,
            bases,
            {
                name: (
                    cls.__popup_on_exception(
                        cls.__try_unload_plugin_and_reraise(
                            member,
                        ),
                    )
                    if callable(member)
                    else member
                )
                for name, member in dct.items()
            },
        )


# Jumping through loops to make above metaclass work with PySide
# T.y.
# https://stackoverflow.com/a/13183077 &
# A. Voitier @ https://bugreports.qt.io/browse/PYSIDE-1767

_QWidgetMeta = type(QWidget)


class _ShibokenObjectTypeFence(_QWidgetMeta): ...  # type: ignore[misc, valid-type]


class _UiPluginMeta(_ShibokenObjectTypeFence, _UiMethodDecoratingMeta, _QWidgetMeta): ...  # type: ignore[misc, valid-type]


class UiPluginBase(QWidget, metaclass=_UiPluginMeta):
    def __init__(self, app_model: AppModel) -> None:
        super().__init__()
        self.__app_model = app_model

    def panic(self) -> None:
        """Signals the AppModel to unload the current plugin (i.e. self)"""
        _LOG.error("Plugin panicked.")
        self.__app_model._unload_current_plugin()
