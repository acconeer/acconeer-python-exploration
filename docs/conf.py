# Copyright (c) Acconeer AB, 2022-2025
# All rights reserved
import os


project = "acconeer-python-exploration"
copyright = "2019-2025, Acconeer AB"
author = "Acconeer AB"
html_title = "Acconeer docs"
language = "en"

master_doc = "index"
source_suffix = ".rst"

exclude_patterns = [
    "_build",
    "Thumbs.db",
    ".DS_Store",
    "README.md",
    "how_to_docs.rst",
]

extensions = [
    "sphinx.ext.mathjax",
    "sphinx.ext.autodoc",
    "sphinx.ext.graphviz",
    "sphinx.ext.extlinks",
    "sphinx_design",
    "myst_parser",
    "sphinxext.rediraffe",
    "notfound.extension",
    "sphinx_tabs.tabs",
    "sphinxcontrib.youtube",
    "sphinxcontrib.spelling",
]

suppress_warnings = [
    "ref.python",  # https://github.com/sphinx-doc/sphinx/issues/4961
]

pygments_style = None


########################## Extensions' configuration ###########################

# autodoc
autodoc_member_order = "bysource"
autodoc_typehints_format = "short"
python_use_unqualified_type_names = True

# extlinks
extlinks = {
    "github_1a5d2c6": (
        "https://github.com/acconeer/acconeer-python-exploration/tree/"
        + "1a5d2c68d1c0b458109818af788ed2b386144644/%s",
        "%s",
    ),
}

# graphviz
graphviz_dot_args = [
    "-Gfontname=sans-serif",
    "-Efontname=sans-serif",
    "-Nfontname=sans-serif",
]
graphviz_output_format = "svg"

# linkcheck
linkcheck_retries = 2
linkcheck_exclude_documents = [
    "exploration_tool/example_scripts/.*",
    "a111/evk_setup/xm112.*",  # Due to instable link to https://ftdichip.com/drivers/vcp-drivers/
]

# rediraffe
rediraffe_redirects = "redirects.txt"
rediraffe_branch = "HEAD~1"
rediraffe_auto_redirect_perc = 95

# sphinx tabs
sphinx_tabs_disable_tab_closing = True

# spelling
spelling_suggestion_limit = 7
spelling_show_suggestions = True
spelling_show_whole_line = True
spelling_warning = True
spelling_word_list_filename = ["spelling_wordlist.txt"]

############################# HTML Builder Options #############################

html_theme = "sphinx_book_theme"

html_favicon = "_static/favicon.png"
html_logo = "_static/logo.svg"
html_static_path = ["_static"]
html_css_files = ["css/custom.css"]

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
            "type": "fontawesome",
        },
        {
            "name": "Instagram",
            "url": "https://instagram.com/acconeerab",
            "icon": "fab fa-instagram",
            "type": "fontawesome",
        },
        {
            "name": "YouTube",
            "url": "https://www.youtube.com/acconeer",
            "icon": "fab fa-youtube",
            "type": "fontawesome",
        },
        {
            "name": "Innovation Lab",
            "url": "https://www.acconeer.com/innovation-lab",
            "icon": "far fa-lightbulb",
            "type": "fontawesome",
        },
    ],
}

html_last_updated_fmt = "%Y-%m-%d"


htmlhelp_basename = "acconeer-python-exploration-docs"

### RTD Addons migration (See https://about.readthedocs.com/blog/2024/07/addons-by-default/)

# Set canonical URL from the Read the Docs Domain
html_baseurl = os.environ.get("READTHEDOCS_CANONICAL_URL", "")

# Tell Jinja2 templates the build is running on Read the Docs
if os.environ.get("READTHEDOCS", "") == "True":
    if "html_context" not in globals():
        html_context = {}
    html_context["READTHEDOCS"] = True


############################ LaTeX Builder Options #############################

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
