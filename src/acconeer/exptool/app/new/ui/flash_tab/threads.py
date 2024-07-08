# Copyright (c) Acconeer AB, 2022-2024
# All rights reserved

from __future__ import annotations

import logging
import shutil
import traceback
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Optional

from requests import Response, Session
from requests.cookies import RequestsCookieJar

from PySide6.QtCore import QThread, Signal

from acconeer.exptool._core.communication.comm_devices import CommDevice
from acconeer.exptool.app.new._exceptions import HandledException
from acconeer.exptool.flash import (
    ET_DIR,
    DevLicense,
    clear_cookies,
    download,
    flash_image,
    get_content,
    get_cookies,
    login,
)


log = logging.getLogger(__name__)


class FlashThread(QThread):
    flash_failed = Signal(Exception, str)
    flash_done = Signal()
    flash_progress = Signal(int)

    def __init__(
        self, bin_file: str, flash_device: CommDevice, device_name: Optional[str]
    ) -> None:
        super().__init__()
        self.bin_file = bin_file
        self.flash_device = flash_device
        self.device_name = device_name

    def run(self) -> None:
        def progress_callback(progress: int, end: bool = False) -> None:
            if end:
                self.flash_progress.emit(100)
            else:
                self.flash_progress.emit(progress)

        try:
            flash_image(
                self.bin_file,
                self.flash_device,
                device_name=self.device_name,
                progress_callback=progress_callback,
            )
            self.flash_done.emit()
        except Exception as e:
            log.error(str(e))
            self.flash_failed.emit(HandledException(e), traceback.format_exc())


class AuthThread(QThread):
    license_loaded = Signal(DevLicense)
    auth_failed = Signal()
    auth_done = Signal(tuple)  # (RequestsCookieJar, Tuple[bool, Session, Response]))

    def __init__(
        self,
        usr: str = "",
        pwd: str = "",
        do_login: bool = False,
        dev_license: Optional[DevLicense] = None,
    ) -> None:
        super().__init__()
        self.usr = usr
        self.pwd = pwd
        self.do_login = do_login
        self.dev_license = dev_license

    def run(self) -> None:
        login_succeeded = False

        if self.do_login:
            cookies = login(self.usr, self.pwd)
        else:
            cookies = get_cookies()

        try:
            if cookies is not None:
                content = get_content(cookies)
                login_succeeded = content[0]
            else:
                login_succeeded = False
        except Exception as e:
            log.error(str(e))

        if self.dev_license is not None:
            self.dev_license.load()
            self.license_loaded.emit(self.dev_license)

        if login_succeeded:
            self.auth_done.emit((cookies, content))
        else:
            if not self.do_login:
                clear_cookies()
            self.auth_failed.emit()


class BinDownloadThread(QThread):
    download_done = Signal(str, str)
    download_failed = Signal(str)

    def __init__(
        self,
        device: Optional[str],
        cookies: RequestsCookieJar,
        session: Session,
        response: Response,
    ) -> None:
        super().__init__()
        self.device = device
        self.cookies = cookies
        self.session = session
        self.response = response

    def run(self) -> None:
        if (
            self.device is None
            or self.cookies is None
            or self.session is None
            or self.response is None
        ):
            self.download_failed.emit("Failed to start download")
        else:
            with TemporaryDirectory() as temp_dir:
                try:
                    temp_file, version = download(
                        session=self.session,
                        cookies=self.cookies,
                        path=temp_dir,
                        device=self.device,
                    )

                    if temp_file is not None:
                        bin_file = str(ET_DIR / Path(temp_file).name)
                        shutil.move(temp_file, bin_file)
                        self.download_done.emit(bin_file, version)
                    else:
                        self.download_failed.emit(
                            f"Failed to download firmware for device {self.device}"
                        )
                except Exception as e:
                    self.download_failed.emit(str(e))
                finally:
                    self.session.close()
