# Copyright (c) Acconeer AB, 2022-2025
# All rights reserved

from __future__ import annotations

import logging
from typing import List, Optional

import bs4
import requests


DEV_LICENSE_URL = "https://developer.acconeer.com/software-license-agreement/"

DEV_LICENSE_DEFAULT_HEADER = "SOFTWARE LICENSE AGREEMENT"
DEV_LICENSE_DEFAULT_SUBHEADER = "LIMITED LICENSE AGREEMENT FOR Acconeer MATERIALS"
DEV_LICENSE_DEFAULT_CONFIRMATION_MSG = (
    "Please read carefully the terms and conditions at "
    "https://developer.acconeer.com/software-license-agreement/"
)

log = logging.getLogger(__name__)


class DevLicense:
    """Acconeer developer license abstraction"""

    def __init__(self, license_url: str = DEV_LICENSE_URL) -> None:
        self.license_url = license_url
        self.html: Optional[bs4.BeautifulSoup] = None

    def load(self) -> None:
        """Loads the license HTML document"""
        try:
            self.html = bs4.BeautifulSoup(requests.get(self.license_url).text, "html.parser")
        except Exception as e:
            log.warn(str(e))
            self.html = None

    def get_header(self) -> str:
        """Get the HTML header as a string

        :returns: HTML header.

        """
        if self.html is None:
            return DEV_LICENSE_DEFAULT_HEADER

        last_breadcrumb = self.html.find("span", {"class": "breadcrumb_last"})
        if not isinstance(last_breadcrumb, bs4.Tag):
            return DEV_LICENSE_DEFAULT_HEADER

        header_text = last_breadcrumb.string
        if header_text is None:
            return DEV_LICENSE_DEFAULT_HEADER

        return header_text

    def get_header_element(self) -> str:
        """Get the HTML header element as a string

        :returns: HTML header element.

        """
        return "<h1>" + self.get_header() + "</h1>"

    def get_subheader(self) -> str:
        """Get the HTML subheader as a string

        :returns: HTML subheader.

        """
        subheader = DEV_LICENSE_DEFAULT_SUBHEADER

        if self.html is not None:
            subheader_element = self.html.find("h3")
            if isinstance(subheader_element, bs4.Tag):
                h3_contents = subheader_element.string
                if h3_contents is not None:
                    subheader = h3_contents

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
            paragraphs = [str(p) for p in self.html.select("p") if "class=" not in str(p)]
        else:
            paragraphs.append("<p></p>")
            paragraphs.append(DEV_LICENSE_DEFAULT_CONFIRMATION_MSG)

        return paragraphs
