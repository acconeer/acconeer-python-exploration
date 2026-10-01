# Copyright (c) Acconeer AB, 2026
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

import attrs
import bs4
import platformdirs
import requests

from ._interface import Artifact, ArtifactRepository, LoginRequiredError
from ._utils import try_get_obfuscated_email_from_cookiejar, version_from_filename


DEFAULT_BASE_URL = "https://developer.acconeer.com"

_ARTIFACT_DEVICE_NAMES = {
    Artifact.XC120_EXPLORATION_SERVER: "xc120",
    Artifact.XM125_EXPLORATION_SERVER: "xm125",
    Artifact.XM126_EXPLORATION_SERVER: "xm126",
}

ET_DIR = Path(platformdirs.user_data_dir(appname="acconeer_exptool", appauthor="Acconeer AB"))
CODENAME = "plugoneer"
COOKIE_DIR = ET_DIR / CODENAME / "cookies"
COOKIE_FILEPATH = COOKIE_DIR / "developer_page.pickle"

log = logging.getLogger(__name__)


def _login_url(base_url: str) -> str:
    return f"{base_url}/log-in/"


def _a121_sw_url(base_url: str) -> str:
    return f"{base_url}/home/a121-docs-software/"


def _strip_trailing_slash(base_url: str) -> str:
    return base_url.rstrip("/")


def _load_saved_cookies() -> Optional[requests.cookies.RequestsCookieJar]:
    if not os.path.exists(COOKIE_FILEPATH):
        return None

    with open(COOKIE_FILEPATH, "rb") as handle:
        cookie_jar = pickle.load(handle)

    # The pickled file is only ever written by _save_cookies() below.
    assert isinstance(cookie_jar, requests.cookies.RequestsCookieJar)
    cookie_jar.clear_expired_cookies()
    return cookie_jar if cookie_jar.get_dict() else None


def _save_cookies(cookies: requests.cookies.RequestsCookieJar) -> None:
    COOKIE_DIR.mkdir(parents=True, exist_ok=True)
    with open(COOKIE_FILEPATH, "wb") as handle:
        pickle.dump(cookies, handle)
    log.debug("Login saved")


def _clear_saved_cookies() -> None:
    if os.path.exists(COOKIE_FILEPATH):
        os.remove(COOKIE_FILEPATH)
        log.debug("Login session removed")
    else:
        log.debug("No previous session saved")


@attrs.mutable
class DevSiteRepository(ArtifactRepository):
    """Fetches content from the Acconeer developer site.

    Defaults to the real production site; point ``base_url`` at a local
    test server to exercise this class against a fake backend instead.
    """

    cookies: Optional[requests.cookies.RequestsCookieJar]
    base_url: str = attrs.field(default=DEFAULT_BASE_URL, converter=_strip_trailing_slash)

    @classmethod
    def from_saved_login(cls, base_url: str = DEFAULT_BASE_URL) -> DevSiteRepository:
        """Constructs a repository from a previously-remembered login, if any.

        The saved cookie jar isn't scoped by ``base_url``: it always holds
        whichever session was last remembered via ``login(remember_me=True)``.
        """
        return cls(cookies=_load_saved_cookies(), base_url=base_url)

    def get_user_representation(self) -> str | None:
        if self.cookies is None:
            return None
        else:
            return try_get_obfuscated_email_from_cookiejar(cookiejar=self.cookies)

    def login(self, email: str, password: str, remember_me: bool = False) -> None:
        url = _login_url(self.base_url)
        wordpress_profile_builder_options = {
            "rememberme": "forever",
            "wp-submit": "Log+In",
            "wppb_login": "true",
            "wppb_request_url": url,
            "wppb_redirect_priority": "normal",
            "wppb_referer_url": self.base_url,
            "_wp_http_referer": "/log-in/",
            "wppb_redirect_check": "true",
        }

        with requests.Session() as session:
            login_page_get_resp = session.get(url)
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
                url,
                data={**credentials, **wordpress_profile_builder_options},
                allow_redirects=False,
            )

            # https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Location
            redirection_url = login_post_resp.headers["Location"]

            if "loginerror" in redirection_url:
                log.warning("Wrong email or password")
                self.cookies = None
                return

            cookies = login_post_resp.cookies
            if len(cookies) == 0:
                self.cookies = None
                return

            self.cookies = cookies
            if remember_me:
                _save_cookies(cookies)

    def forget_login(self) -> None:
        self.cookies = None
        _clear_saved_cookies()

    def has_logged_in_previously(self) -> bool:
        return self.cookies is not None

    def download(self, artifact: Artifact, path: str) -> Tuple[str, str]:
        with requests.Session() as session:
            if self.cookies is not None:
                session.cookies.update(self.cookies)

            response = session.get(url=self.base_url)
            verified = (
                response.url != _login_url(self.base_url)
                and response.headers.get("Expires") is not None
            )
            if not verified:
                msg = "Login has expired or was never established."
                raise LoginRequiredError(msg)

            device = _ARTIFACT_DEVICE_NAMES[artifact]

            page_device_map = {"xc120": "xe121"}

            page_device = page_device_map.get(device, device)

            response = session.get(url=_a121_sw_url(self.base_url))

            soup = bs4.BeautifulSoup(response.content, "html.parser")
            link = soup.findAll("a", {"href": lambda l: l and page_device in l})

            if not link:
                msg = f"No download found for device '{device}'"
                raise Exception(msg)

            response = session.get(url=link[0]["href"])
            soup = bs4.BeautifulSoup(response.content, "html.parser")

            zip_url_tags = soup.findAll(
                "a", {"href": lambda l: l and device in l and "exploration_server" in l}
            )
            if not zip_url_tags:
                msg = f"No image found for device '{device}'"
                raise Exception(msg)
            zip_url = zip_url_tags[0]["href"]
            assert isinstance(zip_url, str), "Expected a single href, not a multi-valued attribute"

            log.debug("File to download: {}".format(zip_url))

            tc = "tc_accepted=1&tc_submit=Download"
            headers = {"Content-Type": "application/x-www-form-urlencoded"}

            r = session.post(zip_url, data=tc, allow_redirects=False, headers=headers)

        email_msg = EmailMessage()
        content_disposition = r.headers["Content-Disposition"]
        # EmailMessage.__setitem__ does magic things here
        email_msg["Content-Disposition"] = content_disposition
        filename = email_msg.get_filename()
        if filename is None:
            msg = f"Response from POST to {zip_url} did not contain a filename."
            raise Exception(msg)

        version = version_from_filename(filename)

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
