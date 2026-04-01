# Copyright (c) Acconeer AB, 2022-2026
# All rights reserved

from __future__ import annotations

import contextlib
import importlib.metadata
import logging
import sys
import traceback
from typing import Any, ClassVar, Iterator, Optional

import pyperclip

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QStyle,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from acconeer.exptool.app.new._exceptions import HandledException


_LOG = logging.getLogger(__name__)


def get_installed_packages() -> Optional[list[str]]:
    """Return installed packages in 'name==version' format."""
    try:
        packages = []
        for dist in importlib.metadata.distributions():
            name = dist.metadata.get("Name")
            version = dist.version

            if name:  # safety check
                packages.append(f"{name}=={version}")

        return packages

    except Exception:
        _LOG.exception("Failed to get installed packages")
        return None


class ExceptionWidget(QDialog):
    MAX_NUM_EXCEPTION_POPUPS: ClassVar[int] = 20
    num_exception_popups: ClassVar[int] = 0

    def __init__(
        self,
        parent: Optional[QWidget],
        *,
        exc: Exception,
        traceback_str: Optional[str] = None,
        title: str = "Error",
    ) -> None:
        super().__init__(parent)

        self._traceback_str = traceback_str

        self.setWindowTitle(title)
        self.setSizeGripEnabled(True)

        outer = QVBoxLayout(self)

        top_row = QHBoxLayout()
        icon_label = QLabel()
        icon = self.style().standardIcon(QStyle.StandardPixmap.SP_MessageBoxWarning)
        icon_label.setPixmap(icon.pixmap(48, 48))
        icon_label.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        top_row.addWidget(icon_label)

        text_col = QVBoxLayout()
        main_label = QLabel(str(exc))
        main_label.setWordWrap(True)
        text_col.addWidget(main_label)

        try:
            raise exc
        except HandledException:
            pass
        except Exception:
            info_label = QLabel("<b>Unhandled error - please file a bug</b>")
            text_col.addWidget(info_label)

        top_row.addLayout(text_col)
        outer.addLayout(top_row)

        detailed_text = (
            "Checklist before reporting a bug\n"
            + "================================\n"
            + "- [ ] I have read the 'Common Issues' without finding a solution\n"
            + "      (See https://docs.acconeer.com/en/latest/exploration_tool/faq.html)\n"
            + "- [ ] This issue occured in the latest release of Exploration Tool\n"
            + "      (See https://pypi.org/project/acconeer-exptool/)\n"
            + "- [ ] I have double-checked that the section 'Installed Packages' contains\n"
            + "      rows on the format '<package name>==<version>'\n"
            + "\n\n"
        )
        detailed_text += f"Python version\n==============\n{sys.version}\n\n\n"

        installed_packages = get_installed_packages()
        detailed_text += "Installed Packages\n" + "==================\n"
        if installed_packages is None:
            detailed_text += (
                "Please supply the output of 'pip freeze'\n"
                + "(Could not extract information about installed packages)."
            )
        else:
            detailed_text += "\n".join(installed_packages)
        detailed_text += "\n\n\n"

        if traceback_str:
            detailed_text += "Traceback\n" + "=========\n" + traceback_str

        self._detail_edit = QTextEdit()
        self._detail_edit.setReadOnly(True)
        self._detail_edit.setPlainText(detailed_text)
        self._detail_edit.setFontFamily("monospace")
        self._detail_edit.setMinimumHeight(220)
        self._detail_edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._detail_edit.hide()
        outer.addWidget(self._detail_edit)

        button_row = QHBoxLayout()
        self._toggle_button = QPushButton("Show Details...")
        self._toggle_button.clicked.connect(self._toggle_details)
        button_row.addWidget(self._toggle_button)

        copy_button = QPushButton("Copy details")
        copy_button.clicked.connect(self._on_copy_clicked)
        button_row.addWidget(copy_button)

        button_row.addStretch()

        ok_buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        ok_buttons.accepted.connect(self.accept)
        button_row.addWidget(ok_buttons)

        outer.addLayout(button_row)

    def _toggle_details(self) -> None:
        visible = not self._detail_edit.isVisible()
        self._detail_edit.setVisible(visible)
        self._toggle_button.setText("Hide Details..." if visible else "Show Details...")
        if visible:
            self.resize(700, 600)
        else:
            self.adjustSize()

    def _should_show_error_popup(self) -> bool:
        if type(self).num_exception_popups < type(self).MAX_NUM_EXCEPTION_POPUPS:
            type(self).num_exception_popups += 1
            return True
        else:
            msg = "!!! {cls_name} has displayed the maximum of {n_err} errors. Dumping traceback: !!!".format(
                cls_name=type(self).__name__,
                n_err=type(self).MAX_NUM_EXCEPTION_POPUPS,
            )
            print()
            print(msg)
            print(self._traceback_str)

            return False

    def open(self, *args: Any, **kwargs: Any) -> Any:
        if self._should_show_error_popup():
            return super().open(*args, **kwargs)

    def exec(self, *args: Any, **kwargs: Any) -> Any:
        if self._should_show_error_popup():
            return super().exec(*args, **kwargs)

    @classmethod
    @contextlib.contextmanager
    def context(cls) -> Iterator[None]:
        try:
            yield
        except Exception as e:
            _LOG.debug("Exception raised in MainThread:", exc_info=True)
            cls(parent=None, exc=e, traceback_str=traceback.format_exc()).exec()

    def _on_copy_clicked(self) -> None:
        pyperclip.copy(self._detail_edit.toPlainText())


class VerticalSeparator(QWidget):
    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)

        frame = QFrame(self)
        frame.setFrameShape(QFrame.Shape.VLine)
        layout.addWidget(frame)

        self.setLayout(layout)
