# Copyright (c) Acconeer AB, 2022-2024
# All rights reserved

project = "acconeer-python-exploration"
copyright = "2019-2024, Acconeer AB"
author = "Acconeer AB"
html_title = "Acconeer docs"

# version = ""  # The short X.Y version
# release = ""  # The full version, including alpha/beta/rc tags

extensions = [
    "sphinx.ext.mathjax",
    "sphinx.ext.autodoc",
    "sphinx.ext.graphviz",
    "sphinx.ext.extlinks",
    "sphinx_design",
    "myst_parser",
    "sphinxext.rediraffe",
    "notfound.extension",
]

suppress_warnings = [
    "ref.python",  # https://github.com/sphinx-doc/sphinx/issues/4961
]

autodoc_member_order = "bysource"

autodoc_typehints_format = "short"
python_use_unqualified_type_names = True

graphviz_dot_args = [
    "-Gfontname=sans-serif",
    "-Efontname=sans-serif",
    "-Nfontname=sans-serif",
]
graphviz_output_format = "svg"

extlinks = {
    "github_1a5d2c6": (
        "https://github.com/acconeer/acconeer-python-exploration/tree/"
        + "1a5d2c68d1c0b458109818af788ed2b386144644/%s",
        "%s",
    ),
}

rediraffe_redirects = "redirects.txt"
rediraffe_branch = "origin/master"
rediraffe_auto_redirect_perc = 95

source_suffix = ".rst"

master_doc = "index"

language = "en"

exclude_patterns = [
    "_build",
    "Thumbs.db",
    ".DS_Store",
    "README.md",
    "how_to_docs.txt",
]

pygments_style = None

################
# HTML Options #
################

html_theme = "sphinx_book_theme"

html_favicon = "_static/favicon.png"
html_logo = "_static/logo.svg"
html_static_path = ["_static"]
html_css_files = ["custom.css"]

html_theme_options = {
    "external_links": [
        {"name": "Developer site", "url": "https://developer.acconeer.com/"},
    ],
    "icon_links": [
        {
            "name": "GitHub",
            "url": "https://github.com/acconeer/acconeer-python-exploration",
            "icon": "fab fa-github",
            "type": "fontawesome",
        },
        {
            "name": "Twitter",
            "url": "https://twitter.com/acconeer_ab",
            "icon": "fab fa-twitter",
        },
        {
            "name": "Instagram",
            "url": "https://instagram.com/acconeerab",
            "icon": "fab fa-instagram",
        },
    ],
}

html_last_updated_fmt = "%Y-%m-%d"


htmlhelp_basename = "acconeer-python-exploration-docs"


#################
# LaTeX Options #
#################

latex_elements = {
    "papersize": "a4paper",
    "pointsize": "11pt",
    "fontpkg": r"""
        \usepackage{helvet}
        \renewcommand{\familydefault}{\sfdefault}
    """,
    "tableofcontents": "",
    "sphinxsetup": ",".join(
        [
            r"hmargin={1.2in, 1.2in}",
        ]
    ),
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
        "handbook/index",
        "handbook.tex",
        "Handbook",
        author,
        "howto",
        False,
    )
]

numfig = True
numfig_format = {"figure": "Figure %s"}
math_eqref_format = "Eq. {number}"
numfig_secnum_depth = 0
