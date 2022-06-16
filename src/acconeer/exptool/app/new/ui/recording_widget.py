from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QFileDialog, QHBoxLayout, QPushButton, QWidget

from acconeer.exptool.app.new.app_model import AppModel


class RecordingWidget(QWidget):
    def __init__(self, app_model: AppModel, parent: QWidget) -> None:
        super().__init__(parent)

        self.setLayout(QHBoxLayout(self))
        self.layout().setContentsMargins(0, 0, 0, 0)

        self.layout().addWidget(LoadFileButton(app_model, self))
        self.layout().addWidget(SaveFileButton(app_model, self))


class LoadFileButton(QPushButton):
    def __init__(self, app_model: AppModel, parent: QWidget) -> None:
        super().__init__(parent)

        self.app_model = app_model

        self.setText("Load from file")

        self.clicked.connect(self._on_click)

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


class SaveFileButton(QPushButton):
    def __init__(self, app_model: AppModel, parent: QWidget) -> None:
        super().__init__(parent)

        self.app_model = app_model

        self.setText("Save to file")

        self.clicked.connect(self._on_click)

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
