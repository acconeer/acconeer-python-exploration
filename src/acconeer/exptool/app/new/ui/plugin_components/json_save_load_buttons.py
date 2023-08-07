# Copyright (c) Acconeer AB, 2023
# All rights reserved

from __future__ import annotations

import enum
import json
import traceback
import typing as t
from pathlib import Path

import typing_extensions as te

from PySide6.QtCore import QSize, QTimer
from PySide6.QtWidgets import QFileDialog, QHBoxLayout, QPushButton, QWidget

from acconeer.exptool.app.new._exceptions import HandledException
from acconeer.exptool.app.new.ui.icons import CHECKMARK, FOLDER_OPEN, SAVE
from acconeer.exptool.app.new.ui.misc import ExceptionWidget

from .data_editor import DataEditor
from .save_dialog import (
    PresentationType,
    PresenterFunc,
    SaveDialogWithPreview,
    set_config_presenter,
)


_ICON_SIZE = QSize(20, 20)
_BUTTON_SIZE = QSize(35, 25)
_FILE_DIALOG_FILTER = "JSON (*.json)"


@te.runtime_checkable
class JsonPresentable(te.Protocol):
    def to_json(self) -> str:
        ...

    @classmethod
    def from_json(self, json_str: str) -> JsonPresentable:
        ...


_JsonPresentableT = t.TypeVar("_JsonPresentableT", bound=JsonPresentable)


def _none_coalescing_chain(*funcs: PresenterFunc) -> PresenterFunc:
    """
    Composes a sequence of PresenterFuncs into a chain.

    The chain will call the functions in order,
    terminating at (and returning the result of)
    the first function returning a non-None value.
    """

    def _chain(instance: t.Any, t: PresentationType) -> t.Optional[str]:
        for f in funcs:
            presentation = f(instance, t)
            if presentation is not None:
                return presentation
        return None

    return _chain


def _json_presentation(instance: t.Any, t: PresentationType) -> t.Optional[str]:
    if t is PresentationType.JSON and isinstance(instance, JsonPresentable):
        return json.dumps(
            json.loads(instance.to_json()),
            indent=2,
        )

    return None


def _show_transient_checkmark(button: QPushButton, duration_ms: int = 2000) -> None:
    """Temporarily changes the icon of button to a checkmark"""
    original_icon = button.icon()
    button.setIcon(CHECKMARK())
    QTimer.singleShot(duration_ms, lambda: button.setIcon(original_icon))


def _handle_exception_with_popup(
    f: t.Callable[..., t.Any], header: str, parent: QWidget
) -> t.Callable[..., t.Any]:
    """Decorates the function "f" by displaying any raised exception in an ExceptionWidget"""

    def wrapper(*args: t.Any, **kwargs: t.Any) -> t.Any:
        try:
            return f(*args, **kwargs)
        except Exception as e:
            ExceptionWidget(
                parent=parent,
                exc=HandledException(
                    header + "\n" + f"The following exception was raised: {e!r}\n"
                ),
                traceback_str=traceback.format_exc(),
            ).exec()

    return wrapper


class _JsonLoadButton(QPushButton):
    def __init__(
        self,
        setter: t.Callable[[JsonPresentable], t.Any],
        decoder: t.Callable[[str], JsonPresentable],
        parent: t.Optional[QWidget] = None,
    ) -> None:
        super().__init__(FOLDER_OPEN(), "", parent=parent)

        self._setter = setter
        self._decoder = decoder

        self.setFixedSize(_BUTTON_SIZE)
        self.setIconSize(_ICON_SIZE)
        self.setToolTip("Load a config from file")
        self.clicked.connect(
            _handle_exception_with_popup(
                self._load_and_set_selected_file,
                header="Could not load config from file.",
                parent=self,
            )
        )

    def _load_and_set_selected_file(self) -> None:
        filename, _ = QFileDialog.getOpenFileName(
            self,
            caption="Load from file",
            filter=_FILE_DIALOG_FILTER,
            options=QFileDialog.Option.DontUseNativeDialog,
        )

        if filename:
            self._setter(self._decoder(Path(filename).read_text()))
            _show_transient_checkmark(self)


class _JsonSaveButton(QPushButton):
    def __init__(
        self,
        getter: t.Callable[[], t.Optional[_JsonPresentableT]],
        encoder: t.Callable[[_JsonPresentableT], str],
        extra_presenter: PresenterFunc,
    ) -> None:
        super().__init__(SAVE(), "")
        self._getter = getter
        self._encoder = encoder
        self._extra_presenter = extra_presenter

        self.setFixedSize(_BUTTON_SIZE)
        self.setIconSize(_ICON_SIZE)
        self.setToolTip("Save the current config to file")
        self.clicked.connect(
            _handle_exception_with_popup(
                self._save_to_selected_file,
                header="Could not save config to file.",
                parent=self,
            )
        )

    def _save_to_selected_file(self) -> None:
        model = self._getter()

        if model is None:
            raise RuntimeError

        filename = SaveDialogWithPreview.get_save_file_name(
            caption="Save to file",
            model=model,
            presenter=_none_coalescing_chain(
                _json_presentation,
                set_config_presenter,
                self._extra_presenter,
            ),
            filter=_FILE_DIALOG_FILTER,
            parent=self,
        )

        if filename:
            Path(filename).with_suffix(".json").write_text(self._encoder(model))
            _show_transient_checkmark(self)


class JsonButtonOperations(enum.Flag):
    SAVE = enum.auto()
    LOAD = enum.auto()


def create_json_save_load_buttons(
    editor: DataEditor[t.Optional[_JsonPresentableT]],
    config_type: t.Type[_JsonPresentableT],
    operations: JsonButtonOperations = JsonButtonOperations.SAVE | JsonButtonOperations.LOAD,
    extra_presenter: PresenterFunc = lambda i, t: None,
) -> QWidget:
    """
    Creates buttons for saving/loading configs to/from json.

    :param editor: The editor to bind the save/load buttons to
    :param config_type: The type (class) of the config
    :param operations:
        Defines what operations the button(s) should perform.
        This directly maps to which buttons are created.
    :param extra_presenter:
        A PresenterFunc hooks into save preview presentation creation.
        This function should always return None if its arguments aren't handled.
    """
    wrapper = QWidget()
    wrapper.setLayout(QHBoxLayout())
    wrapper.layout().setContentsMargins(5, 5, 5, 8)

    if operations & JsonButtonOperations.SAVE:
        wrapper.layout().addWidget(
            _JsonSaveButton(
                editor.get_data,
                config_type.to_json,
                extra_presenter=extra_presenter,
            )
        )
    if operations & JsonButtonOperations.LOAD:
        wrapper.layout().addWidget(_JsonLoadButton(editor.sig_update.emit, config_type.from_json))

    return wrapper
