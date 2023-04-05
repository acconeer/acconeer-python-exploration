# Copyright (c) Acconeer AB, 2023
# All rights reserved
from __future__ import annotations

import typing as t

from PySide6.QtWidgets import QTextBrowser, QWidget


_HELP_MD = """
# Acconeer Exploration Tool Help

Welcome to the help section of Exploration Tool.
If you are searching for information, further reading or software downloads,
these links might be of help:

## Information and further reading

- [Handbook](https://docs.acconeer.com/en/latest/handbook/index.html):
Overview of radar concepts, information about Acconeer's radars.

- [Exploration Tool docs](https://docs.acconeer.com/en/latest/exploration_tool/index.html):
Covers how to install Exploration Tool and EVK setup,
Python API reference and algorithm descriptions.

- [docs.acconeer.com](https://docs.acconeer.com):
Documentation portal

## Software downloads

- [Acconeer on Github](https://github.com/acconeer):
Hosts machine learning examples and Exploration Tool itself.<br />Machine learning examples:
    + [Gesture control](https://github.com/acconeer/acconeer-a121-gesture-control)
    + [Grass detection](https://github.com/acconeer/acconeer-a121-grass-detection)
    + [Carpet detection](https://github.com/acconeer/acconeer-a121-carpet-detection)

- [Developer Site](https://developer.acconeer.com):
User guides and C SDKs.

## Other links:

- [Acconeer's Products](https://www.acconeer.com/products/)

- [Acconeer on Twitter](https://twitter.com/acconeer_ab)

- [Acconeer on Instagram](https://www.instagram.com/acconeerab/)

"""


class HelpMainWidget(QTextBrowser):
    def __init__(self, parent: t.Optional[QWidget] = None) -> None:
        super().__init__()

        self.setReadOnly(True)
        self.setOpenExternalLinks(True)

        self.setStyleSheet("border: none;")
        self.setMarkdown(_HELP_MD)
