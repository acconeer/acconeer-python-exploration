project = "acconeer-python-exploration"
copyright = "2019 - 2022, Acconeer AB"
author = "Acconeer AB"

# version = ""  # The short X.Y version
# release = ""  # The full version, including alpha/beta/rc tags

extensions = [
    "sphinx.ext.mathjax",
    "sphinx.ext.autodoc",
    "sphinx.ext.graphviz",
    "sphinx.ext.extlinks",
    "myst_parser",
    "sphinxext.rediraffe",
]

autodoc_member_order = "bysource"

autodoc_typehints_format = "short"

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
rediraffe_branch = "HEAD~1"
rediraffe_auto_redirect_perc = 95

source_suffix = ".rst"

master_doc = "index"

language = None

exclude_patterns = [
    "_build",
    "Thumbs.db",
    ".DS_Store",
    "README.md",
    "how_to_docs.txt",
]

pygments_style = None

html_theme = "sphinx_rtd_theme"

html_css_files = ["css/custom.css"]

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
        "sensor_introduction",
        "sensor_introduction.tex",
        "Sensor Introduction",
        author,
        "howto",
        False,
    )
]

numfig = True
numfig_format = {"figure": "Figure %s"}
math_eqref_format = "Eq. {number}"
numfig_secnum_depth = 0
