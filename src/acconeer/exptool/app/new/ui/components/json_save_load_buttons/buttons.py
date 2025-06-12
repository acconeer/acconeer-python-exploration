# Copyright (c) Acconeer AB, 2023-2025
# All rights reserved

from __future__ import annotations

import enum
import json
import traceback
import typing as t
from pathlib import Path

import typing_extensions as te

from PySide6.QtCore import QSize, QTimer
from PySide6.QtWidgets import QHBoxLayout, QPushButton, QWidget

from acconeer.exptool.app.new._exceptions import HandledException
from acconeer.exptool.app.new.ui.components.data_editor import DataEditor
from acconeer.exptool.app.new.ui.icons import CHECKMARK, FOLDER_OPEN, SAVE
from acconeer.exptool.app.new.ui.misc import ExceptionWidget

from .dialogs import (
    LoadDialogWithJsonEditor,
    PresentationType,
    PresenterFunc,
    SaveDialogWithPreview,
    set_config_presenter,
)


_ICON_SIZE = QSize(20, 20)
_BUTTON_SIZE = QSize(35, 25)
_SAVE_FILE_DIALOG_FILTER = "JSON (*.json);;CSV (*.csv)"
_LOAD_FILE_DIALOG_FILTER = "JSON (*.json)"


@te.runtime_checkable
class JsonPresentable(te.Protocol):
    def to_json(self) -> str: ...

    @classmethod
    def from_json(cls, json_str: str) -> te.Self: ...


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
        setter: t.Callable[[_JsonPresentableT], t.Any],
        decoder: t.Callable[[str], _JsonPresentableT],
        parent: t.Optional[QWidget] = None,
    ) -> None:
        super().__init__(FOLDER_OPEN(), "", parent=parent)

        self._setter = setter
        self._decoder = decoder

        self.setFixedSize(_BUTTON_SIZE)
        self.setIconSize(_ICON_SIZE)
        self.setToolTip("Load a config from file/clipboard")
        self.clicked.connect(
            _handle_exception_with_popup(
                self._load_and_set_selected_file,
                header="Could not load config from file/clipboard",
                parent=self,
            )
        )

    def _load_and_set_selected_file(self) -> None:
        contents = LoadDialogWithJsonEditor.get_load_contents(
            caption="Load from file",
            filter=_LOAD_FILE_DIALOG_FILTER,
            parent=self,
        )

        if contents:
            self._setter(self._decoder(contents))
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

        filename, file_filter = SaveDialogWithPreview.get_save_file_name(
            caption="Save to file",
            model=model,
            presenter=_none_coalescing_chain(
                _json_presentation,
                set_config_presenter,
                self._extra_presenter,
            ),
            filter=_SAVE_FILE_DIALOG_FILTER,
            parent=self,
        )

        if filename and file_filter:
            if "json" in file_filter:
                Path(filename).with_suffix(".json").write_text(self._encoder(model))
            elif "csv" in file_filter:
                Path(filename).with_suffix(".csv").write_text(
                    _dict_to_csv(_flatten_dict(json.loads(self._encoder(model))))
                )
            else:
                msg = f"Unknown file type {file_filter}"
                raise TypeError(msg)
            _show_transient_checkmark(self)


def _dict_to_csv(data: t.Dict[t.Any, t.Any]) -> str:
    output_str = ""

    for key, value in data.items():
        output_str += f"{key},{value}\n"

    return output_str


def _flatten_dict(
    data: t.Dict[str, t.Any], root: t.Optional[t.Dict[str, t.Any]] = None, parent_key: str = ""
) -> t.Dict[str, t.Any]:
    if root is None:
        root = dict()

    for key, value in data.items():
        src_key = parent_key + "_" + key if parent_key else key
        if isinstance(value, dict):
            _flatten_dict(value, root, src_key)
        elif isinstance(value, list):
            for i, v in enumerate(value):
                if src_key == "groups":
                    # In SessionConfig groups are a list of dicts with a single key,
                    # which corresponds to the number of the group.
                    # So no need to enumerate these keys.
                    sub_key = src_key
                else:
                    sub_key = src_key + "_" + str(i)

                if isinstance(v, dict):
                    _flatten_dict(v, root, sub_key)
                else:
                    root[sub_key] = v if v is not None else "None"
        else:
            root[src_key] = value if value is not None else "None"

    return root


def create_json_save_load_buttons(
    editor: DataEditor[t.Optional[_JsonPresentableT]],
    encoder: t.Optional[t.Callable[[_JsonPresentableT], str]] = None,
    decoder: t.Optional[t.Callable[[str], _JsonPresentableT]] = None,
    extra_presenter: PresenterFunc = lambda i, t: None,
) -> QWidget:
    """
    Creates buttons for saving/loading configs to/from json.

    :param editor: The editor to bind the save/load buttons to
    :param encoder:
        A function that formats the model as a json string.
        If omitted or None, the Save button will not be created.
    :param decoder:
        A function that parses a json string produced by encoder
        If omitted or None, the Load button will not be created.
    :param extra_presenter:
        A PresenterFunc hooks into save preview presentation creation.
        This function should always return None if its arguments aren't handled.
    """
    wrapper = QWidget()
    wrapper_layout = QHBoxLayout()
    wrapper.setLayout(wrapper_layout)
    wrapper_layout.setContentsMargins(5, 5, 5, 8)

    if encoder is not None:
        wrapper_layout.addWidget(
            _JsonSaveButton(
                editor.get_data,
                encoder,
                extra_presenter=extra_presenter,
            )
        )

    def setter(data: _JsonPresentableT) -> t.Any:
        editor.set_data(data)
        editor.sig_update.emit(data)

    if decoder is not None:
        wrapper_layout.addWidget(_JsonLoadButton(setter, decoder))

    return wrapper


class JsonButtonOperations(enum.Flag):
    SAVE = enum.auto()
    LOAD = enum.auto()


def create_json_save_load_buttons_from_type(
    editor: DataEditor[t.Optional[_JsonPresentableT]],
    config_type: t.Type[_JsonPresentableT],
    operations: JsonButtonOperations = JsonButtonOperations.SAVE | JsonButtonOperations.LOAD,
    extra_presenter: PresenterFunc = lambda i, t: None,
) -> t.Optional[QWidget]:
    """
    Utility variation of "create_json_save_load_buttons".

    :param config_type: The type (class) of the config
    :param operations:
        Defines what operations the button(s) should perform.
        This directly maps to which buttons are created.
        If no operations are specified, None will be returned.

    See create_json_save_load_buttons for the other parameters.
    """
    if operations == JsonButtonOperations(0):
        return None
    else:
        return create_json_save_load_buttons(
            editor,
            encoder=config_type.to_json if (operations & JsonButtonOperations.SAVE) else None,
            decoder=config_type.from_json if (operations & JsonButtonOperations.LOAD) else None,
            extra_presenter=extra_presenter,
        )
