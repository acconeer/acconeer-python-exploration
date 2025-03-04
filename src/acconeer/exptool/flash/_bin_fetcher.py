# Copyright (c) Acconeer AB, 2022-2025
# All rights reserved

from __future__ import annotations

import logging
import os
import pickle
import shutil
import tempfile
import zipfile
from email.message import EmailMessage
from pathlib import Path
from typing import Optional, Tuple

import bs4
import platformdirs
import requests


ET_DIR = Path(platformdirs.user_data_dir(appname="acconeer_exptool", appauthor="Acconeer AB"))
CODENAME = "plugoneer"
COOKIE_DIR = ET_DIR / CODENAME / "cookies"
COOKIE_FILEPATH = COOKIE_DIR / "developer_page.pickle"
REQUEST_URL = "https://developer.acconeer.com/log-in/"
REFERER_URL = "https://developer.acconeer.com"
ACC_DEV_AJAX_URL = "https://developer.acconeer.com/wp-admin/admin-ajax.php"
A121_SW_URL = "https://developer.acconeer.com/home/a121-docs-software/"
WORDPRESS_PROFILE_BUILDER_OPTIONS = {
    "rememberme": "forever",
    "wp-submit": "Log+In",
    "wppb_login": "true",
    "wppb_request_url": REQUEST_URL,
    "wppb_redirect_priority": "normal",
    "wppb_referer_url": REFERER_URL,
    "_wp_http_referer": "/log-in/",
    "wppb_redirect_check": "true",
}

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


def login(email: str, password: str) -> Optional[requests.cookies.RequestsCookieJar]:
    with requests.Session() as session:
        login_page_get_resp = session.get(REQUEST_URL)
        soup = bs4.BeautifulSoup(login_page_get_resp.content, "html.parser")
        csrf_input_elem = soup.find("input", {"id": "CSRFToken-wppb"})
        assert isinstance(csrf_input_elem, bs4.Tag)
        token = csrf_input_elem.get("value")

        credentials = {
            "log": email,
            "pwd": password,
            "CSRFToken-wppb": token,
        }
        login_post_resp = session.post(
            REQUEST_URL,
            data={**credentials, **WORDPRESS_PROFILE_BUILDER_OPTIONS},
            allow_redirects=False,
        )

        # https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Location
        redirection_url = login_post_resp.headers["Location"]

        if "loginerror" in redirection_url:
            log.warning("Wrong email or password")
            return None

        cookies = login_post_resp.cookies
        if len(cookies) == 0:
            return None

        return cookies


def get_content(
    cookies: requests.cookies.RequestsCookieJar,
) -> Tuple[bool, requests.Session, requests.Response]:
    with requests.Session() as session:
        response = session.get(url=REFERER_URL, cookies=cookies.get_dict())

        if response.url == REQUEST_URL or response.headers.get("Expires") is None:
            return False, session, response
        elif response.headers.get("Expires") is not None:
            return True, session, response
        else:
            raise Exception


def is_redirected_to_login_page(response: requests.Response) -> bool:
    return bool(response.url == REQUEST_URL)


def download(
    session: requests.Session,
    cookies: requests.cookies.RequestsCookieJar,
    path: str,
    device: str,
) -> Tuple[str, str]:
    device = device.lower()

    page_device_map = {"xc120": "xe121"}

    page_device = page_device_map.get(device, device)

    response = session.get(url=A121_SW_URL)

    soup = bs4.BeautifulSoup(response.content, "html.parser")
    link = soup.findAll("a", {"href": lambda l: l and page_device in l})

    if not link:
        msg = f"No download found for device '{device}'"
        raise Exception(msg)

    response = session.get(url=link[0]["href"])
    soup = bs4.BeautifulSoup(response.content, "html.parser")

    zip_url = soup.findAll(
        "a", {"href": lambda l: l and device in l and "exploration_server" in l}
    )
    if not zip_url:
        msg = f"No image found for device '{device}'"
        raise Exception(msg)
    zip_url = zip_url[0]["href"]

    log.debug("File to download: {}".format(zip_url))

    tc = "tc_accepted=1&tc_submit=Download"
    headers = {"Content-Type": "application/x-www-form-urlencoded"}

    r = session.post(zip_url, data=tc, allow_redirects=False, cookies=cookies, headers=headers)

    email_msg = EmailMessage()
    content_disposition = r.headers["Content-Disposition"]
    # EmailMessage.__setitem__ does magic things here
    email_msg["Content-Disposition"] = content_disposition
    filename = email_msg.get_filename()
    if filename is None:
        msg = f"Response from POST to {zip_url} did not contain a filename."
        raise Exception(msg)

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
                        msg = "Multiple images in directory"
                        raise Exception(msg)
                    bin_path = zipObject.extract(fileName, os.path.join(path, tmp_dir))
                    bin_found = True
            if bin_found is False:
                msg = "No images found in directory"
                raise Exception(msg)

        dst_path = os.path.join(path, os.path.basename(bin_path))
        shutil.move(bin_path, dst_path)

        os.remove(filepath)

    return dst_path, version


def _get_version(bin_file: Optional[str]) -> str:
    version = "n/a"

    if bin_file is not None:
        version = Path(bin_file).stem

    return version
