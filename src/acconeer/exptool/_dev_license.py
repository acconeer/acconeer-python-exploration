# Copyright (c) Acconeer AB, 2022-2026
# All rights reserved

from __future__ import annotations

import logging

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
        self.html: bs4.BeautifulSoup | None = None

    def load(self) -> None:
        """Loads the license HTML document"""
        try:
            response = requests.get(self.license_url, timeout=10)
            response.raise_for_status()
            self.html = bs4.BeautifulSoup(response.text, "html.parser")
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
            subheader_element = self.html.find("h3")
            if isinstance(subheader_element, bs4.Tag):
                subheader_elem = str(subheader_element)

        return subheader_elem

    def _content_tags(self) -> list[tuple[bs4.Tag, str]]:
        """Headings and paragraphs of the agreement, with their text, in reading order.

        Scoped to <main> so that site navigation ("Products", "Contact", ...)
        sharing the page's heading tags isn't picked up as license content.
        Some of the agreement's own sections (e.g. "11. APPLICABLE LAW") have
        no heading tag at all and are a <p> that's entirely bold instead;
        those still pass the same "p" selector and need no special-casing.
        Text comes from .get_text(), not .string: several headings split
        their text across more than one <strong> run, which leaves .string
        as None even though the heading has real text.
        """
        if self.html is None:
            return []

        main = self.html.find("main")
        root = main if isinstance(main, bs4.Tag) else self.html

        tags_with_text = [(tag, tag.get_text()) for tag in root.select("h2, h3, h4, p")]
        return [(tag, text) for tag, text in tags_with_text if text]

    def get_content(self) -> list[str]:
        """Get the HTML paragraph content as a list of strings

        :returns: HTML paragraphs.

        """
        if self.html is None:
            return [DEV_LICENSE_DEFAULT_CONFIRMATION_MSG]

        # The "\xa0" is a non-breaking space (&nbsp;) that is not
        # escaped by BeautifulSoup and hence filtered out here.
        return [text.replace("\xa0", " ") for _tag, text in self._content_tags()]

    def get_content_elements(self) -> list[str]:
        """Get the HTML paragraph elements as a list of strings

        :returns: HTML paragraphs elements.

        """
        if self.html is None:
            return ["<p></p>", DEV_LICENSE_DEFAULT_CONFIRMATION_MSG]

        return [str(tag) for tag, _text in self._content_tags()]
