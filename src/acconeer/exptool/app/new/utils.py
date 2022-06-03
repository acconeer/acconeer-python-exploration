from PySide6.QtWidgets import QMessageBox


def show_error_pop_up(title: str, error_msg: str) -> None:
    msg_box = QMessageBox()
    msg_box.setWindowTitle(title)
    msg_box.setText(error_msg)
    msg_box.exec()
