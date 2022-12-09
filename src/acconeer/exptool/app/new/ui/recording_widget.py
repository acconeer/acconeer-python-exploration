# Copyright (c) Acconeer AB, 2022
# All rights reserved

from __future__ import annotations

from pathlib import Path
from typing import Optional

import qtawesome as qta

from PySide6 import QtCore, QtGui
from PySide6.QtWidgets import QCheckBox, QFileDialog, QHBoxLayout, QPushButton, QWidget

from acconeer.exptool.app.new.app_model import AppModel

from .misc import BUTTON_ICON_COLOR


class RecordingWidget(QWidget):
    def __init__(self, app_model: AppModel, parent: QWidget) -> None:
        super().__init__(parent)

        self.setLayout(QHBoxLayout(self))
        self.layout().setContentsMargins(0, 0, 0, 0)

        self.layout().addWidget(LoadFileButton(app_model, self))
        self.layout().addWidget(SaveFileButton(app_model, self))
        self.layout().addWidget(RecordingCheckbox(app_model, self))


class RecordingCheckbox(QCheckBox):
    def __init__(
        self,
        app_model: AppModel,
        parent: QWidget,
    ) -> None:
        super().__init__("Enable recording", parent)

        self.app_model = app_model
        app_model.sig_notify.connect(self._on_app_model_update)

        self.setToolTip("Enables recording of session to file")
        self.setFocusPolicy(QtCore.Qt.FocusPolicy.NoFocus)

        self.stateChanged.connect(self._on_state_changed)

    def _on_state_changed(self) -> None:
        self.app_model.set_recording_enabled(self.isChecked())

    def _on_app_model_update(self, app_model: AppModel) -> None:
        self.setChecked(app_model.recording_enabled)
        self.setEnabled(app_model.plugin_state.is_steady)


class FileButton(QPushButton):
    def __init__(
        self,
        app_model: AppModel,
        text: str,
        icon: QtGui.QIcon,
        shortcut: Optional[str],
        tooltip: Optional[str],
        parent: QWidget,
    ) -> None:
        super().__init__(parent)

        self.app_model = app_model

        self.setText(text)
        self.setIcon(icon)

        if shortcut is not None:
            self.setShortcut(shortcut)
            newline = "\n"
            tooltip = f"{tooltip or ''}{newline if tooltip else ''}Shortcut: {shortcut}"

        if tooltip is not None:
            self.setToolTip(tooltip)

        self.clicked.connect(self._on_click)

        self.setFocusPolicy(QtCore.Qt.FocusPolicy.NoFocus)


class LoadFileButton(FileButton):
    def __init__(self, app_model: AppModel, parent: QWidget) -> None:
        super().__init__(
            app_model,
            "Load from file",
            qta.icon("fa.folder-open", color=BUTTON_ICON_COLOR),
            "Ctrl+o",
            "Load a previously recorded and saved session and play it back",
            parent,
        )
        app_model.sig_notify.connect(self._on_app_model_update)

    def _on_app_model_update(self, app_model: AppModel) -> None:
        self.setEnabled(app_model.plugin_state.is_steady)

    def _on_click(self) -> None:
        filename, _ = QFileDialog.getOpenFileName(
            self,
            caption="Load from file",
            filter=_file_suffix_to_filter(".h5", ".npz"),
            options=QFileDialog.DontUseNativeDialog,
        )

        if not filename:
            return

        self.app_model.load_from_file(Path(filename))


class SaveFileButton(FileButton):
    def __init__(self, app_model: AppModel, parent: QWidget) -> None:
        super().__init__(
            app_model,
            "Save to file",
            qta.icon("mdi.content-save", color=BUTTON_ICON_COLOR),
            "Ctrl+s",
            "Save the current session",
            parent,
        )
        app_model.sig_notify.connect(self._on_app_model_update)

    def _on_app_model_update(self, app_model: AppModel) -> None:
        self.setEnabled(app_model.saveable_file is not None and app_model.plugin_state.is_steady)

    def _on_click(self) -> None:
        if self.app_model.saveable_file is None:
            raise RuntimeError

        filename, _ = QFileDialog.getSaveFileName(
            self,
            caption="Save to file",
            filter=_file_suffix_to_filter(self.app_model.saveable_file.suffix),
            options=QFileDialog.DontUseNativeDialog,
        )

        if not filename:
            return

        path = Path(filename)

        if path.suffix != self.app_model.saveable_file.suffix:
            path = path.with_name(path.name + self.app_model.saveable_file.suffix)

        self.app_model.save_to_file(path)


def _file_suffix_to_filter(*exts: str) -> str:
    NAMES = {
        ".h5": "HDF5",
        ".npz": "NumPy",
    }
    return ";;".join([f"{NAMES.get(ext, '')} (*{ext})" for ext in exts])
