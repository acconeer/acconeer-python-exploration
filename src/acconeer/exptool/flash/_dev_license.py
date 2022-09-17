# Copyright (c) Acconeer AB, 2022
# All rights reserved

from __future__ import annotations

import logging
from typing import List

import requests

from bs4 import BeautifulSoup


DEV_LICENSE_URL = "https://developer.acconeer.com/software-license-agreement/"

DEV_LICENSE_DEFAULT_HEADER = "SOFTWARE LICENSE AGREEMENT"
DEV_LICENSE_DEFAULT_SUBHEADER = "LIMITED LICENSE AGREEMENT FOR Acconeer MATERIALS"
DEV_LICENSE_DEFAULT_CONFIRMATION_MSG = (
    "Please read carefully the terms and conditions at "
    "https://developer.acconeer.com/software-license-agreement/"
)

log = logging.getLogger(__name__)


class DevLicense:
    """Acconeer developer license abstration"""

    def __init__(self, license_url: str = DEV_LICENSE_URL) -> None:
        self.license_url = license_url
        self.html = None

    def load(self) -> None:
        """Loads the license HTML document"""
        try:
            self.html = BeautifulSoup(requests.get(self.license_url).text, "html.parser")
        except Exception as e:
            log.warn(str(e))
            self.html = None

    def get_header(self) -> str:
        """Get the HTML header as a string

        :returns: HTML header.

        """
        header = DEV_LICENSE_DEFAULT_HEADER

        if self.html is not None:
            header_element = self.html.find("h1")
            if header_element is not None:
                header = header_element.contents[0].string

        return header

    def get_header_element(self) -> str:
        """Get the HTML header element as a string

        :returns: HTML header element.

        """
        header_elem = "<h1>" + DEV_LICENSE_DEFAULT_HEADER + "</h1>"

        if self.html is not None:
            header_elem = str(self.html.find("h1"))

        return header_elem

    def get_subheader(self) -> str:
        """Get the HTML subheader as a string

        :returns: HTML subheader.

        """
        subheader = DEV_LICENSE_DEFAULT_SUBHEADER

        if self.html is not None:
            subheader_element = self.html.find("h3")
            if subheader_element is not None:
                subheader = subheader_element.contents[0].string

        return subheader

    def get_subheader_element(self) -> str:
        """Get the HTML subheader element as a string

        :returns: HTML subheader element.

        """
        subheader_elem = "<h3>" + DEV_LICENSE_DEFAULT_SUBHEADER + "</h3>"

        if self.html is not None:
            subheader_elem = str(self.html.find("h3"))

        return subheader_elem

    def get_content(self) -> List[str]:
        """Get the HTML paragraph content as a list of strings

        :returns: HTML paragraphs.

        """
        paragraphs = []

        if self.html is not None:
            for p in self.html.select("p"):
                if p is not None and p.string is not None:
                    # The "\xa0" is a non-breaking space (&nbsp;) that is not
                    # escaped by BeautifulSoup and hence filtered out here.
                    paragraphs.append(p.string.replace("\xa0", " "))
        else:
            paragraphs.append(DEV_LICENSE_DEFAULT_CONFIRMATION_MSG)

        return paragraphs

    def get_content_elements(self) -> List[str]:
        """Get the HTML paragraph elements as a list of strings

        :returns: HTML paragraphs elements.

        """
        paragraphs = []

        if self.html is not None:
            paragraphs = [str(p) for p in self.html.select("p")]
        else:
            paragraphs.append("<p></p>")
            paragraphs.append(DEV_LICENSE_DEFAULT_CONFIRMATION_MSG)

        return paragraphs
