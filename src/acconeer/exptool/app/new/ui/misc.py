# Copyright (c) Acconeer AB, 2022-2026
# All rights reserved

from __future__ import annotations

import contextlib
import logging
import sys
import traceback
from typing import Any, ClassVar, Iterator, Optional

import pyperclip

from PySide6 import QtGui
from PySide6.QtWidgets import QFrame, QHBoxLayout, QMessageBox, QPushButton, QWidget

from acconeer.exptool.app.new._exceptions import HandledException


_LOG = logging.getLogger(__name__)


def get_installed_packages_via_pip() -> Optional[list[str]]:
    """Tries to extract information about installed packages"""
    try:
        try:
            from pip._internal.operations.freeze import freeze
        except ImportError:
            from pip.operations.freeze import freeze  # type: ignore

        return list(freeze())
    except Exception:
        return None


class ExceptionWidget(QMessageBox):
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

        self.setIcon(QMessageBox.Icon.Warning)
        self.setStandardButtons(QMessageBox.StandardButton.Ok)

        self.setWindowTitle(title)
        self.setText(str(exc))

        try:
            raise exc
        except HandledException:
            pass
        except Exception:
            self.setInformativeText("<b>Unhandled error - please file a bug</b>")

        # Monospaced detailed text.
        self.setStyleSheet("QTextEdit { font-family: monospace; font-size: 9pt; }")

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

        installed_packages = get_installed_packages_via_pip()
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

        if detailed_text:
            self.setDetailedText(detailed_text)
            copy_button = QPushButton(self)
            copy_button.setText("Copy details")
            self.addButton(copy_button, QMessageBox.ButtonRole.ActionRole)
            copy_button.clicked.disconnect()
            copy_button.clicked.connect(self._on_copy_clicked)

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

    def resizeEvent(self, event: QtGui.QResizeEvent) -> None:
        super().resizeEvent(event)
        self.setMinimumWidth(600)

    def _on_copy_clicked(self) -> None:
        detailed_text = self.detailedText()
        if detailed_text:
            pyperclip.copy(detailed_text)

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:
        self.close()


class VerticalSeparator(QWidget):
    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)

        frame = QFrame(self)
        frame.setFrameShape(QFrame.Shape.VLine)
        layout.addWidget(frame)

        self.setLayout(layout)
