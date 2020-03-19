# -*- coding: utf-8 -*-

import os
import sys


conf_dir = os.path.dirname(os.path.realpath(__file__))
root_dir = os.path.abspath(os.path.join(conf_dir, ".."))
sys.path.append(root_dir)

project = "acconeer-python-exploration"
copyright = "2019 - 2020, Acconeer AB"
author = "Acconeer AB"

# version = ""  # The short X.Y version
# release = ""  # The full version, including alpha/beta/rc tags

extensions = [
    "sphinx.ext.mathjax",
    "sphinx.ext.autodoc",
    "sphinx.ext.graphviz",
]

autodoc_member_order = "bysource"

graphviz_dot_args = [
    "-Gfontname=sans-serif",
    "-Efontname=sans-serif",
    "-Nfontname=sans-serif",
]
graphviz_output_format = "svg"

source_suffix = ".rst"

master_doc = "index"

language = None

exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]

pygments_style = None

html_theme = "sphinx_rtd_theme"

html_static_path = ["_static"]

htmlhelp_basename = "acconeer-python-exploration-docs"

latex_elements = {
    "papersize": "a4paper",
    "pointsize": "11pt",
    "fontpkg": r"""
        \usepackage{helvet}
        \renewcommand{\familydefault}{\sfdefault}
    """,
    "tableofcontents": "",
    "sphinxsetup": ",".join([
        r"hmargin={1.2in, 1.2in}",
    ]),
    "preamble": r"""
        \usepackage{titling}
        \usepackage{graphicx}
        \graphicspath{{../../_static/}}
    """,
    "maketitle": r"""
        \vspace*{50mm}
        \begin{center}
            \includegraphics[width=100mm]{logo.pdf}
            \par
            \vspace*{15mm}
            {
                \huge
                \thetitle
            }
        \end{center}
        \newpage
        \tableofcontents
        \newpage
    """,
}

# (startdocname, targetname, title, author, documentclass, toctree_only)
latex_documents = [
    (
        "sensor_introduction",
        "sensor_introduction.tex",
        "Sensor Introduction",
        author,
        "howto",
        False,
    )
]


def setup(app):
    app.add_stylesheet("css/custom.css")


numfig = True
