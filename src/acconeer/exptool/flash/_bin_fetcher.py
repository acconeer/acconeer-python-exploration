# Copyright (c) Acconeer AB, 2022
# All rights reserved

from __future__ import annotations

import cgi
import logging
import os
import pickle
import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import Optional, Tuple

import requests

import platformdirs
from bs4 import BeautifulSoup


ET_DIR = Path(platformdirs.user_data_dir(appname="acconeer_exptool", appauthor="Acconeer AB"))
CODENAME = "plugoneer"
COOKIE_DIR = ET_DIR / CODENAME / "cookies"
COOKIE_FILEPATH = COOKIE_DIR / "developer_page.pickle"
REQUEST_URL = "https://developer.acconeer.com/log-in/"
REFERER_URL = "https://developer.acconeer.com"
ACC_DEV_LICENSE_URL = "https://developer.acconeer.com/software-license-agreement/"

BIN_FETCH_PROMPT = (
    "To fetch the latest image you need to log into your Acconeer Developer account.\n\n"
    "If you don't have an account you can create one here:\n"
    "https://developer.acconeer.com/create-account/ \n\n"
    "Lost your password? Recover it here:\n"
    "https://developer.acconeer.com/recover-password/"
)

log = logging.getLogger(__name__)


def get_cookies() -> requests.cookies.RequestsCookieJar:
    if os.path.exists(COOKIE_FILEPATH):
        with open(COOKIE_FILEPATH, "rb") as handle:
            cookie_jar = pickle.load(handle)
        cookie_jar.clear_expired_cookies()
        cookies = cookie_jar.get_dict()
        if not cookies:
            cookie_jar = None
    else:
        cookie_jar = None
    return cookie_jar


def _make_cookie_dir() -> None:
    COOKIE_DIR.mkdir(parents=True, exist_ok=True)


def save_cookies(cookies: requests.cookies.RequestsCookieJar) -> None:
    _make_cookie_dir()
    with open(COOKIE_FILEPATH, "wb") as handle:
        pickle.dump(cookies, handle)
    log.debug("Login saved")


def clear_cookies() -> None:
    if os.path.exists(COOKIE_FILEPATH):
        os.remove(COOKIE_FILEPATH)
        log.debug("Login session removed")
    else:
        log.debug("No previous session saved")


def login(email: str, password: str) -> requests.cookies.RequestsCookieJar:

    with requests.Session() as session:
        login_page = session.get(REQUEST_URL)
        soup = BeautifulSoup(login_page.content, "html.parser")
        token = soup.find("input", {"id": "CSRFToken-wppb"}).get("value")

        credentials = {
            "log": email,
            "pwd": password,
            "rememberme": "forever",
            "wp-submit": "Log+In",
            "wppb_login": "true",
            "wppb_request_url": REQUEST_URL,
            "wppb_redirect_priority": "normal",
            "wppb_referer_url": REFERER_URL,
            "CSRFToken-wppb": token,
            "_wp_http_referer": "/log-in/",
            "wppb_redirect_check": "true",
        }
        sw_page = session.post(REQUEST_URL, data=credentials, allow_redirects=False)
        cookies = sw_page.cookies

        return cookies


def get_content(
    cookies: requests.cookies.RequestsCookieJar,
) -> Tuple[bool, requests.Session, requests.Response]:

    with requests.Session() as session:
        response = session.get(url=REFERER_URL, cookies=cookies.get_dict())

        if response.url == REQUEST_URL:
            return False, session, response
        elif response.headers.get("Expires") is None:
            return False, session, response
        elif response.headers.get("Expires") is not None:
            return True, session, response
        else:
            raise Exception


def is_redirected_to_login_page(response: requests.Response) -> bool:
    return response.url == REQUEST_URL


def download(
    session: requests.Session,
    cookies: dict,
    page: requests.Response,
    path: str,
    device: str,
) -> Tuple[str, str]:

    device = device.lower().replace(" ", "_")
    soup = BeautifulSoup(page.content, "html.parser")
    form = soup.select_one('form[action*="{}"]'.format(device))
    zip_url = form.get("action")

    download_value = form.select_one('[type="submit"]').get("value")

    log.debug("File to download: {}".format(zip_url))

    tc = {"tc_accepted": "1", "tc_submit": download_value}

    r = session.post(zip_url, data=tc, allow_redirects=False, cookies=cookies.get_dict())

    _, params = cgi.parse_header(r.headers["Content-Disposition"])
    filename = params["filename"]

    version = _get_version(filename)

    filepath = os.path.join(path, filename)

    with open(filepath, "wb") as output_file:
        output_file.write(r.content)
        log.debug("Download completed at {}".format(filepath))

    log.debug("Extracting files..")

    with tempfile.TemporaryDirectory() as tmp_dir:
        bin_found = False
        with zipfile.ZipFile(filepath, "r") as zipObject:
            listOfFileNames = zipObject.namelist()
            for fileName in listOfFileNames:
                if fileName.endswith(".bin"):
                    if bin_found:
                        raise Exception("Multiple images in directory")
                    bin_path = zipObject.extract(fileName, os.path.join(path, tmp_dir))
                    bin_found = True
            if bin_found is False:
                raise Exception("No images found in directory")

        dst_path = os.path.join(path, os.path.basename(bin_path))
        shutil.move(bin_path, dst_path)

        os.remove(filepath)

    return dst_path, version


def _get_version(bin_file: Optional[str]) -> str:
    version = "n/a"

    if bin_file is not None:
        version = Path(bin_file).stem

    return version
