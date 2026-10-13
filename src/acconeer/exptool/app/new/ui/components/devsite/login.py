# Copyright (c) Acconeer AB, 2026
# All rights reserved
from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtGui import QDesktopServices, QShowEvent
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from acconeer.exptool._artifact_repository import ArtifactRepository
from acconeer.exptool.app.new.ui import icons
from acconeer.exptool.app.new.ui.background_task import BGTask
from acconeer.exptool.app.new.ui.components.devsite._utils import (
    get_internet_related_error_message,
)
from acconeer.exptool.app.new.ui.utils import FeedbackStyleSheet, Spacer


DEVSITE_REGISTER_URL = "https://developer.acconeer.com/register/"


class LoginFormWidget(QWidget):
    _LOGIN_BUTTON_DEFAULT_TEXT = "Log in"
    _LOGIN_BUTTON_PENDING_TEXT = "Logging in ..."
    _FEEDBACK_DEFAULT_TEXT = "Log in using your developer.acconeer.com account below"

    _COOKIE_POLICY_LINK = "<a href='https://acconeer.com/cookie-policy-eu/'>Cookie Policy</a>"
    _PRIVACY_STATEMENT_LINK = (
        "<a href='https://developer.acconeer.com/privacy-policy/'>Privacy Statement</a>"
    )
    _REMEMBER_ME_TERMS_HTML = (
        "<i>"
        + (
            "<br>".join(
                [
                    '"Remember me" will save your credentials for next time.',
                    "By checking the box you agree to",
                    f"Acconeer's {_COOKIE_POLICY_LINK} and {_PRIVACY_STATEMENT_LINK}.",
                ]
            )
        )
        + "</i>"
    )

    login_succeeded = Signal()

    def __init__(self, repository: ArtifactRepository) -> None:
        super().__init__()
        self._repository = repository
        self._login_pending = False

        self.feedback_lbl = QLineEdit(self._FEEDBACK_DEFAULT_TEXT)
        self.feedback_lbl.setReadOnly(True)
        self.feedback_lbl.setStyleSheet(FeedbackStyleSheet.NICE)

        self.email_line_edit = QLineEdit()
        self.email_line_edit.setPlaceholderText("example@domain.com")
        self.email_line_edit.textChanged.connect(self._update_login_button_enabledness)

        self.password_line_edit = QLineEdit()
        self.password_line_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_line_edit.setPlaceholderText("*" * 12)
        self.password_line_edit.textChanged.connect(self._update_login_button_enabledness)

        self.peek_button = QToolButton()
        self.peek_button.setIcon(icons.EYE_OPEN())
        self.peek_button.setCheckable(True)
        self.peek_button.setChecked(False)
        self.peek_button.toggled.connect(self._handle_peek_state_change)

        password_and_peek_layout = QHBoxLayout()
        password_and_peek_layout.addWidget(self.password_line_edit)
        password_and_peek_layout.addWidget(self.peek_button)

        self.remember_me_checkbox = QCheckBox()
        self.remember_me_checkbox.setText("Remember me")
        self.remember_me_checkbox.setChecked(False)
        remember_me_terms_label = QLabel(self._REMEMBER_ME_TERMS_HTML)
        remember_me_terms_label.setStyleSheet(f"QLabel {{ color: {icons.TEXT_LIGHTGREY}; }}")

        self.register_btn = QPushButton(
            "Don't have an account? Register on developer.acconeer.com!"
        )
        self.register_btn.setIcon(icons.EXTERNAL_LINK())
        self.register_btn.clicked.connect(lambda: QDesktopServices.openUrl(DEVSITE_REGISTER_URL))

        self.login_button = QPushButton(self._LOGIN_BUTTON_DEFAULT_TEXT)
        self.login_button.setEnabled(False)
        self.login_button.clicked.connect(self._put_login_bg_task)

        layout = QFormLayout()

        layout.addRow(self.feedback_lbl)
        layout.addRow("Email", self.email_line_edit)
        layout.addRow("Password", password_and_peek_layout)
        layout.addRow(self.remember_me_checkbox, remember_me_terms_label)

        layout.addRow(self.login_button)

        layout.addRow(Spacer())
        layout.addRow(self.register_btn)

        self.setLayout(layout)

    def has_logged_in(self) -> bool:
        return self._repository.has_logged_in_previously()

    def showEvent(self, event: QShowEvent) -> None:
        # The login can be forgotten while this widget is hidden.
        if not self._login_pending and not self.has_logged_in():
            self.login_button.setText(self._LOGIN_BUTTON_DEFAULT_TEXT)
        super().showEvent(event)

    def _update_login_button_enabledness(self) -> None:
        if self._login_pending:
            return

        should_be_enabled = (
            self.email_line_edit.text() != "" and self.password_line_edit.text() != ""
        )
        self.login_button.setEnabled(should_be_enabled)

    def _put_login_bg_task(self) -> None:
        self._login_pending = True
        self.login_button.setText(self._LOGIN_BUTTON_PENDING_TEXT)
        self.login_button.setEnabled(False)
        BGTask.create_task(
            self._repository.login,
            args=(
                self.email_line_edit.text(),
                self.password_line_edit.text(),
                self.remember_me_checkbox.isChecked(),
            ),
            return_cb=self._handle_login_return,
            exception_cb=self._handle_login_exception,
        )

    def _handle_login_exception(self, exception: Exception) -> None:
        self._login_pending = False
        if not self.isVisible():
            return

        self.login_button.setEnabled(True)

        error_msg = get_internet_related_error_message(exception)
        self.set_feedback(error_msg, FeedbackStyleSheet.ERROR)
        self.login_button.setText(self._LOGIN_BUTTON_DEFAULT_TEXT)

    def _handle_login_return(self, _login_result: None) -> None:
        self._login_pending = False
        # The user can close the form while the login is in flight; the
        # login then goes unreported.
        if not self.isVisible():
            return

        self.login_button.setEnabled(True)

        if self.has_logged_in():
            user_rep = self._repository.get_user_representation()
            self.login_button.setText(
                "Logged in" if user_rep is None else f"Logged in as {user_rep}"
            )
            self.set_feedback(self._FEEDBACK_DEFAULT_TEXT, FeedbackStyleSheet.NICE)
            self.login_succeeded.emit()
        else:
            self.set_feedback(
                "Wrong email or password. Please try again.", FeedbackStyleSheet.ERROR
            )
            self.login_button.setText(self._LOGIN_BUTTON_DEFAULT_TEXT)

    def _handle_peek_state_change(self, peek_checked: bool) -> None:
        if peek_checked:
            self.password_line_edit.setEchoMode(QLineEdit.EchoMode.Normal)
            self.peek_button.setIcon(icons.EYE_CLOSED())
        else:
            self.password_line_edit.setEchoMode(QLineEdit.EchoMode.Password)
            self.peek_button.setIcon(icons.EYE_OPEN())

    def set_feedback(self, message: str, style: FeedbackStyleSheet) -> None:
        self.feedback_lbl.setText(message)
        self.feedback_lbl.setStyleSheet(style)


class LoginDialog(QDialog):
    """Asks the user to log in to ``repository``.

    Check ``repository.has_logged_in_previously()`` first; a remembered
    login needs no dialog.
    """

    def __init__(self, repository: ArtifactRepository, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Log in")

        self.login_widget = LoginFormWidget(repository)
        self.login_widget.login_succeeded.connect(self.accept)

        self._cancel_button = QPushButton("Cancel")
        self._cancel_button.clicked.connect(self.reject)

        button_layout = QHBoxLayout()
        button_layout.addStretch()
        button_layout.addWidget(self._cancel_button)

        layout = QVBoxLayout()
        layout.addWidget(self.login_widget)
        layout.addLayout(button_layout)
        self.setLayout(layout)
