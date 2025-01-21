# Copyright (c) Acconeer AB, 2023-2025
# All rights reserved

from __future__ import annotations

import typing as t

from PySide6.QtWidgets import QDialog, QFileDialog, QHBoxLayout, QWidget

from .preview import PresentationType, PresentationWindow, PresenterFunc


class SaveDialogWithPreview(QDialog):
    def __init__(
        self,
        dialog: QFileDialog,
        model: t.Any,
        presenter: PresenterFunc,
        parent: t.Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent=parent)

        self._dialog = dialog
        self._dialog.finished.connect(self.done)

        presentations = {p_type: presenter(model, p_type) for p_type in PresentationType}
        non_none_presentations = {
            p_type: p for p_type, p in presentations.items() if p is not None
        }
        layout = QHBoxLayout()
        layout.addWidget(self._dialog, stretch=1)
        layout.addWidget(
            PresentationWindow(non_none_presentations),
            stretch=1,
        )
        self.setLayout(layout)

    @classmethod
    def get_save_file_name(
        cls,
        model: t.Any,
        presenter: PresenterFunc,
        caption: str = "",
        filter: str = "All (*)",
        options: QFileDialog.Option = QFileDialog.Option.DontUseNativeDialog,
        parent: t.Optional[QWidget] = None,
    ) -> t.Tuple[t.Optional[str], t.Optional[str]]:
        dialog = QFileDialog(caption=caption)
        dialog.setAcceptMode(QFileDialog.AcceptMode.AcceptSave)
        dialog.setNameFilter(filter)
        dialog.setOptions(options)

        instance = cls(dialog, model, presenter, parent=parent)
        if instance.exec():
            (selected_file,) = instance._dialog.selectedFiles()
            selected_filter = instance._dialog.selectedNameFilter()
            return str(selected_file), selected_filter
        else:
            return None, None
