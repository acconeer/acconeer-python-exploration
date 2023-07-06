# Copyright (c) Acconeer AB, 2023
# All rights reserved

from __future__ import annotations

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


@te.runtime_checkable
class JsonPresentable(te.Protocol):
    def to_json(self) -> str:
        ...

    @classmethod
    def from_json(self, json: str) -> JsonPresentable:
        ...


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


class JsonSaveLoadButtons(QWidget):
    _ICON_SIZE = QSize(20, 20)
    _BUTTON_SIZE = QSize(35, 25)
    _ICON_TRANSIENT_CHECKMARK_DURATION_MS = 2000
    _FILE_DIALOG_FILTER = "JSON (*.json)"

    def __init__(
        self,
        getter: t.Callable[[], t.Optional[JsonPresentable]],
        setter: t.Callable[[JsonPresentable], t.Any],
        encoder: t.Callable[[JsonPresentable], str],
        decoder: t.Callable[[str], JsonPresentable],
        extra_presenter: PresenterFunc,
        parent: t.Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent=parent)

        self._getter = getter
        self._setter = setter
        self._encoder = encoder
        self._decoder = decoder
        self._extra_presenter = extra_presenter

        self._save = QPushButton(SAVE(), "")
        self._save.setFixedSize(self._BUTTON_SIZE)
        self._save.setIconSize(self._ICON_SIZE)
        self._save.setToolTip("Save the current config to file")
        self._save.clicked.connect(
            self._except_errors(
                self._save_to_selected_file,
                header="Could not save config to file.",
            )
        )

        self._load = QPushButton(FOLDER_OPEN(), "")
        self._load.setFixedSize(self._BUTTON_SIZE)
        self._load.setIconSize(self._ICON_SIZE)
        self._load.setToolTip("Load a config from file")
        self._load.clicked.connect(
            self._except_errors(
                self._load_and_set_selected_file,
                header="Could not load config from file.",
            )
        )

        self.setLayout(QHBoxLayout())
        self.layout().setContentsMargins(5, 5, 5, 8)
        self.layout().addWidget(self._save)
        self.layout().addWidget(self._load)

    @classmethod
    def from_editor_and_config_type(
        cls,
        editor: DataEditor[t.Optional[JsonPresentable]],
        config_type: t.Type[JsonPresentable],
        extra_presenter: PresenterFunc = lambda i, t: None,
    ) -> JsonSaveLoadButtons:
        """
        Creates a JsonSaveLoadButtons instance with a built-in JSON preview

        :param editor: The editor to bind the save/load buttons to
        :param config_type: The type (class) of the config
        :param extra_presenter:
            A PresenterFunc hooks into preview presentation creation.
            This function should always return None if its arguments aren't handled.
        """
        buttons = cls(
            editor.get_data,
            editor.sig_update.emit,
            config_type.to_json,
            config_type.from_json,
            extra_presenter,
        )
        editor.sig_update.connect(lambda model: buttons._save.setEnabled(model is not None))
        return buttons

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
            filter=self._FILE_DIALOG_FILTER,
            parent=self,
        )

        if filename:
            Path(filename).with_suffix(".json").write_text(self._encoder(model))
            self._show_transient_checkmark(self._save)

    def _load_and_set_selected_file(self) -> None:
        filename, _ = QFileDialog.getOpenFileName(
            self,
            caption="Load from file",
            filter=self._FILE_DIALOG_FILTER,
            options=QFileDialog.Option.DontUseNativeDialog,
        )

        if filename:
            self._setter(self._decoder(Path(filename).read_text()))
            self._show_transient_checkmark(self._load)

    @classmethod
    def _show_transient_checkmark(cls, button: QPushButton) -> None:
        original_icon = button.icon()
        button.setIcon(CHECKMARK())
        QTimer.singleShot(
            cls._ICON_TRANSIENT_CHECKMARK_DURATION_MS, lambda: button.setIcon(original_icon)
        )

    def _except_errors(self, f: t.Callable[..., t.Any], header: str) -> t.Callable[..., t.Any]:
        def wrapper(*args: t.Any, **kwargs: t.Any) -> t.Any:
            try:
                return f(*args, **kwargs)
            except Exception as e:
                ExceptionWidget(
                    parent=self,
                    exc=HandledException(
                        header + "\n" + f"The following exception was raised: {e!r}\n"
                    ),
                    traceback_str=traceback.format_exc(),
                ).exec()

        return wrapper
