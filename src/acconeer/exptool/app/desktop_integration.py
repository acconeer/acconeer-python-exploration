# Copyright (c) Acconeer AB, 2026
# All rights reserved
from __future__ import annotations

import ctypes
import logging
import os
import re
import subprocess
import sys
from importlib.resources import as_file, files
from pathlib import Path

from PySide6 import QtCore, QtGui
from PySide6.QtWidgets import QApplication, QWidget

from acconeer.exptool.app import resources


_LOG = logging.getLogger(__name__)

# Used both as the Qt "desktop file name" (Wayland/X11 app id) and as the
# installed .desktop file's basename, so they always match up.
DESKTOP_FILE_ID = "com.acconeer.exptool"

# Win32 indices of a window class's icons, and system metrics of their sizes.
_GCLP_HICON = -14
_GCLP_HICONSM = -34
_SM_CXICON = 11
_SM_CXSMICON = 49


def _quote_exec_arg(arg: str) -> str:
    # Minimal Desktop Entry Specification quoting (not shell quoting).
    if not re.search(r"""[ \t\n"'\\><~|&;$*?#()`]""", arg):
        return arg
    return '"{}"'.format(arg.replace("\\", "\\\\").replace('"', '\\"'))


def _desktop_entry(icon_path: Path) -> str:
    # An absolute path is required: desktop-file consumers (this is what
    # GNOME Shell's window/app-tracking, i.e. the Wayland taskbar/dash icon,
    # relies on) resolve "Exec" via a PATH lookup and silently ignore any
    # entry whose command isn't found on it -- which a bare "acconeer-exptool"
    # usually isn't, since these consumers don't run inside a venv/pipx shim.
    exec_line = f"{_quote_exec_arg(sys.executable)} -m acconeer.exptool.app.new"
    # Icon= as an absolute path (rather than an icon *name* looked up via the
    # hicolor icon theme) so nothing else needs to agree on/rescan an icon
    # theme directory for it to resolve.
    return f"""\
[Desktop Entry]
Type=Application
Name=Acconeer Exploration Tool
Comment=Acconeer Exploration Tool
Exec={exec_line}
Icon={icon_path}
Path={Path.home()}
Terminal=false
Categories=Development;Science;
StartupWMClass={DESKTOP_FILE_ID}
"""


def set_app_id() -> None:
    """
    Sets the application's XDG "app id" (Qt's "desktop file name").

    Must be called before the QApplication is constructed: Qt registers the
    app id with the XDG desktop portal at construction, and the portal
    rejects a second registration made when the id changes afterwards.

    Raises RuntimeError if a QApplication already exists.
    """
    if QApplication.instance() is not None:
        msg = "set_app_id must be called before the QApplication is constructed"
        raise RuntimeError(msg)
    if sys.platform.startswith("linux"):
        QApplication.setDesktopFileName(DESKTOP_FILE_ID)


def ensure_wayland_integration(app: QApplication) -> QtGui.QIcon:
    """
    Sets up the application's icon, including what's needed for it to show up
    correctly under Wayland.

    Wayland compositors identify application windows by their XDG "app id"
    (Qt's "desktop file name"), not by QWindow::icon, and look up the actual
    icon to display via a matching installed .desktop file. Without a
    matching .desktop file, Wayland falls back to a generic icon regardless
    of what setWindowIcon is given. This installs one (and its icon) for the
    current user if it isn't already there. The app id itself is set by
    set_app_id, before the QApplication is constructed.
    """
    icon = _square_icon()
    app.setWindowIcon(icon)

    if sys.platform.startswith("linux"):
        _ensure_desktop_entry_installed(icon)

    return icon


def set_window_class_icon(window: QWidget, icon: QtGui.QIcon) -> None:
    """
    Gives the native window class of ``window``, which the app's windows
    share, ``icon``. Does nothing outside Windows.

    The Windows taskbar asks a newly shown window for its icon, and falls
    back to its window class's icon if the window doesn't answer in time, as
    it doesn't while the app is busy starting up. Qt takes the class icon
    from the executable, which for python.exe is a generic one.
    """
    if sys.platform != "win32":
        return
    user32 = ctypes.windll.user32
    user32.SetClassLongPtrW.restype = ctypes.c_void_p
    user32.SetClassLongPtrW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p]
    hwnd = int(window.winId())
    for index, size_metric in ((_GCLP_HICON, _SM_CXICON), (_GCLP_HICONSM, _SM_CXSMICON)):
        size = user32.GetSystemMetrics(size_metric)
        user32.SetClassLongPtrW(hwnd, index, icon.pixmap(size, size).toImage().toHICON())


def _square_icon(size: int = 256) -> QtGui.QIcon:
    with as_file(files(resources) / "icon.png") as path:
        pixmap = QtGui.QPixmap(str(path))

    max_side = max(pixmap.width(), pixmap.height())
    square_pixmap = QtGui.QPixmap(max_side, max_side)
    square_pixmap.fill(QtGui.QColor(0, 0, 0, 0))

    painter = QtGui.QPainter(square_pixmap)
    painter.drawPixmap(
        (max_side - pixmap.width()) // 2,
        (max_side - pixmap.height()) // 2,
        pixmap,
    )
    painter.end()

    scaled_pixmap = square_pixmap.scaled(
        size,
        size,
        aspectMode=QtCore.Qt.AspectRatioMode.KeepAspectRatio,
        mode=QtCore.Qt.TransformationMode.SmoothTransformation,
    )
    return QtGui.QIcon(scaled_pixmap)


def _ensure_desktop_entry_installed(icon: QtGui.QIcon) -> None:
    try:
        data_home = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
        applications_dir = data_home / "applications"
        icon_path = data_home / "icons" / "hicolor" / "256x256" / "apps" / f"{DESKTOP_FILE_ID}.png"
        desktop_file = applications_dir / f"{DESKTOP_FILE_ID}.desktop"

        if not icon_path.exists():
            icon_path.parent.mkdir(parents=True, exist_ok=True)
            # Format is inferred from the ".png" suffix; passing it
            # explicitly hits a str/bytes mismatch between PySide6's
            # runtime overload resolution and its type stubs.
            icon.pixmap(256, 256).toImage().save(str(icon_path))

        desired_entry = _desktop_entry(icon_path)
        existing_entry = desktop_file.read_text() if desktop_file.exists() else None
        if existing_entry != desired_entry:
            applications_dir.mkdir(parents=True, exist_ok=True)
            desktop_file.write_text(desired_entry)
            try:
                subprocess.run(
                    ["update-desktop-database", str(applications_dir)],
                    check=False,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            except FileNotFoundError:
                pass
    except OSError:
        _LOG.debug("Could not install a .desktop file/icon for Wayland", exc_info=True)
