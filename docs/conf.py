# Copyright (c) Acconeer AB, 2022-2026
# All rights reserved
import datetime
import importlib.metadata
import json
import os
import posixpath
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from docutils import nodes
from sphinx.application import Sphinx
from sphinx.environment.adapters.toctree import global_toctree_for_doc
from sphinx.util import logging


project = "acconeer-python-exploration"
copyright = "2019-2026, Acconeer AB"
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
    "hw_integration/common",
    "radar_data_and_control/common",
]

extensions = [
    "sphinx.ext.mathjax",
    "sphinx.ext.autodoc",
    "sphinx.ext.graphviz",
    "sphinx.ext.extlinks",
    "sphinx_copybutton",
    "sphinx_design",
    "myst_parser",
    "sphinxext.rediraffe",
    "notfound.extension",
    "sphinxcontrib.youtube",
    "sphinxcontrib.spelling",
    "sphinxcontrib.images",
]

suppress_warnings = [
    "ref.python",  # https://github.com/sphinx-doc/sphinx/issues/4961
    # Rendered without content, see autodoc_mock_imports
    "autodoc.mocked_object",
]

# The single-page builds of _build_single_page_guides are rooted below index.rst
if tags.has("printable"):  # noqa: F821, Sphinx provides tags
    suppress_warnings.append("toc.not_included")

pygments_style = None

logger = logging.getLogger(__name__)

########################## Extensions' configuration ###########################

# autodoc
autodoc_member_order = "bysource"
autodoc_typehints_format = "short"
python_use_unqualified_type_names = True
# Shipped in the algo bundle, not in this repository
autodoc_mock_imports = ["acconeer.algo_bundle"]

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
]
linkcheck_ignore = [
    "https://math.stackexchange.com/.*",  # Causes 403 error
    "https://ftdichip.com/.*",  # Causes 403 error
    # TODO: Remove once the A212 examples are released on GitHub
    "https://github.com/acconeer/acconeer-python-exploration/blob/master/examples/a2/.*",
    # Written into the html output by _build_single_page_guides, so not in the sources
    r"single_page\.html$",
]

# rediraffe
rediraffe_redirects = "redirects.txt"
# "rediraffe_branch" is assumed to be used in a `git diff` command.
# Current commit (HEAD) compared against the merge base of HEAD & origin/master, i.e.:
# - If HEAD is ahead of origin/master, the merge base is origin/master
# - If HEAD is on another "branch" than origin/master,
#   this will be the most recent common commit (diverging point)
rediraffe_branch = "origin/master...HEAD"
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

html_favicon = "images/favicon.png"
html_logo = "images/logo.svg"
html_static_path = ["_static"]
html_css_files = ["css/custom.css"]
if tags.has("printable"):  # noqa: F821, Sphinx provides tags
    html_css_files.append("css/single_page.css")

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
    "analytics": {"google_analytics_id": "G-HRERX3GCYB"},
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

numfig = True
numfig_format = {"figure": "Figure %s"}
math_eqref_format = "Eq. {number}"
numfig_secnum_depth = 0


def _update_sensor_placeholder(
    app: Sphinx, relative_path: Path, parent_docname: str, content: list[str]
) -> None:
    """
    Update placeholder string with the sensor name derived from the doc path.

    The radar_data_and_control documents contains information that is common
    to both A121 and A212. Since the common information has references that
    are expected to be unique for a document, the references will not resolve
    correctly when broken out to a common source and included into multiple
    documents.

    By using an include-read hook we can scan the document for a placeholder
    string in the included content. If found, we'll replace it with a unique
    identifier based on the including document path, which will make labels
    unique across the documents.
    """
    placeholder_lower = "SENSOR_PLACEHOLDER_LOWER"
    placeholder_upper = "SENSOR_PLACEHOLDER_UPPER"

    if placeholder_lower not in content[0] and placeholder_upper not in content[0]:
        return
    for sensor in ("a121", "a212"):
        if sensor in parent_docname:
            content[0] = content[0].replace(placeholder_lower, sensor)
            content[0] = content[0].replace(placeholder_upper, sensor.upper())
            return


def _add_header_buttons(
    app: Sphinx,
    pagename: str,
    templatename: str,
    context: dict[str, Any],
    doctree: object,
) -> None:
    """
    Give the single-page guides a button back to the guide and a print button.

    sphinx_book_theme offers "Print to PDF" only in its menu for downloading
    the page's source, which it leaves out of a page with no single source,
    so the pages would otherwise lack the button they are for.
    """
    if app.builder.name != "singlehtml":
        return

    context["header_buttons"][:0] = [
        {
            "type": "link",
            # Relative to the output root, like every link on the page until
            # _build_single_page_guides moves it next to the guide
            "url": f"{app.config.root_doc}.html",
            "tooltip": "Back to the guide",
            "icon": "fas fa-arrow-left",
            "label": "back-to-guide-button",
        },
        {
            "type": "javascript",
            "javascript": "window.print()",
            "tooltip": "Print to PDF",
            "icon": "fas fa-file-pdf",
            "label": "print-pdf-button",
        },
    ]


# Root documents of guides to also build as one page, to print or save as PDF,
# with the title and subtitle on the printed cover, and the acconeer.exptool
# package whose RSS version the guide is printed with
SINGLE_PAGE_GUIDES = {
    "hw_integration/a121/index": ("A121", "Hardware Integration Guide", "a121"),
    "hw_integration/a212/index": ("A212", "Hardware Integration Guide", "a2"),
}


def _rss_version(package: str) -> str:
    """
    The RSS version an acconeer.exptool package is made for, as RSS names it.

    Read from the source, as importing the package would import all of acconeer.exptool.
    """
    init = Path(__file__).parents[1] / "src" / "acconeer" / "exptool" / package / "__init__.py"
    match = re.search(r'^SDK_VERSION = "(.+)"$', init.read_text(encoding="utf-8"), re.MULTILINE)
    if match is None:
        msg = f"No SDK_VERSION in {init}"
        raise RuntimeError(msg)
    return f"{package}-v{match[1]}"


def _add_print_matter(
    app: Sphinx,
    pagename: str,
    templatename: str,
    context: dict[str, Any],
    doctree: object,
) -> None:
    """
    Frame a single-page guide like Acconeer's other printed documents.

    A cover, a page of document info and the contents go before the guide,
    and the site's disclaimer after it. single_page.css shows all but the
    disclaimer only in print, in place of sphinx_book_theme's title and
    contents, and gives every printed page but the cover a header and a footer.
    """
    if app.builder.name != "singlehtml" or pagename != app.config.root_doc:
        return

    title, subtitle, package = SINGLE_PAGE_GUIDES[app.config.root_doc]
    # The version the docs were built from, as distributed on PyPI
    version = importlib.metadata.version("acconeer-exptool")
    today = datetime.date.today()
    # Down to subsections, where the theme's contents list only the documents
    contents = global_toctree_for_doc(
        app.env, pagename, app.builder, tags=app.tags, collapse=False, maxdepth=3
    )
    # singlehtml links a section as "#document-<document>#<section>"
    for reference in contents.findall(nodes.reference):
        reference["refuri"] = "#" + reference["refuri"].rpartition("#")[2]
    # render_partial nests what it renders in a document, which a whole
    # document would be rendered twice in, so it gets the section
    disclaimer = app.env.get_and_resolve_doctree("disclaimer", app.builder).next_node(
        nodes.section
    )

    front = f"""
<style>
@page {{
    @top-right {{ content: {json.dumps(f"{title} {subtitle}")}; }}
    @bottom-left {{ content: "© {today.year} by Acconeer AB - All rights reserved"; }}
}}
/* As this follows single_page.css, its blank cover can't blank these */
@page :first {{
    @top-right {{ content: none; }}
    @bottom-left {{ content: none; }}
}}
</style>
<section class="print-cover">
  <img class="print-cover-logo" src="{context["logo_url"]}" alt="Acconeer">
  <div class="print-cover-title">
    <p class="print-title">{title}</p>
    <p class="print-subtitle">{subtitle}</p>
  </div>
</section>
<section class="print-info">
  <div class="print-info-box">
    <p>{title}</p>
    <p>{subtitle}</p>
    <p>Author: Acconeer AB</p>
    <p>Exploration Tool version: {version}</p>
    <p>RSS version: {_rss_version(package)}</p>
    <p>Acconeer AB {today:%b %d, %Y}</p>
  </div>
</section>
<section class="print-contents">
  <h2>Contents</h2>
  {app.builder.render_partial(contents)["fragment"]}
</section>
"""
    back = f"""
<section class="print-disclaimer">
{app.builder.render_partial(disclaimer)["fragment"]}
</section>
"""
    context["body"] = front + context["body"] + back
    # Which browsers name the saved PDF after
    context["title"] = f"{title} {subtitle}"


def _link_single_page_references(app: Sphinx, doctree: nodes.document, docname: str) -> None:
    """
    Make a single-page guide's cross-references links that work.

    singlehtml links every document of the site as "#document-<document>", and
    a target in it as "#document-<document>#<target>", which no browser follows.
    A target in the guide is linked as itself, being on the page, and one in a
    document outside the guide, such as the glossary, on that document's page.
    """
    if app.builder.name != "singlehtml":
        return

    in_guide = {app.config.root_doc}
    unvisited = [app.config.root_doc]
    while unvisited:
        for child in app.env.toctree_includes.get(unvisited.pop(), []):
            if child not in in_guide:
                in_guide.add(child)
                unvisited.append(child)

    for reference in doctree.findall(nodes.reference):
        uri = reference.get("refuri", "")
        if not uri.startswith("#document-"):
            continue
        document, separator, target = uri.removeprefix("#document-").partition("#")
        if document not in in_guide:
            # Relative to the output root, like every link on the page until
            # _build_single_page_guides moves it next to the guide
            reference["refuri"] = f"{document}.html{separator}{target}"
        elif target:
            reference["refuri"] = f"#{target}"


_PRIMARY_SIDEBAR = re.compile(
    r'<div id="pst-primary-sidebar".*?(?=<main id="main-content")', re.DOTALL
)
_RELATIVE_URL = re.compile(
    r'(?P<attr>\b(?:href|src|action|data-content_root))="(?!#|/|[a-zA-Z][a-zA-Z0-9+.-]*:)'
    r'(?P<path>[^"?#]*)(?P<rest>[^"]*)"'
)


def _build_single_page_guides(app: Sphinx, exception: Exception | None) -> None:
    """
    Build each of SINGLE_PAGE_GUIDES as one page, single_page.html beside its root.

    A multi-page guide printed from the browser prints one page at a time.
    The singlehtml builder joins a guide into one page, but takes the root
    document from the configuration, so each guide is a Sphinx run of its own.
    The runs are subprocesses, as Sphinx keeps global state, and their warnings
    are reported as this build's, which decides whether they fail it.

    The page is made a page of this site: its links, which singlehtml makes
    relative to the output root, are made relative to the guide, and it gets
    the site's left sidebar from the guide's root.
    """
    if exception is not None or app.builder.name != "html":
        return

    outdir = Path(app.outdir)

    with tempfile.TemporaryDirectory() as tmp:
        runs = {}
        for root_doc in SINGLE_PAGE_GUIDES:
            command = [
                sys.executable,
                "-m",
                "sphinx",
                "--quiet",
                "--jobs",
                str(max(app.parallel, 1)),
                "--doctree-dir",
                str(Path(tmp, root_doc, "doctrees")),
                "--builder",
                "singlehtml",
                "--tag",
                "printable",
                "--define",
                f"master_doc={root_doc}",
                str(app.srcdir),
                str(Path(tmp, root_doc, "html")),
            ]
            runs[root_doc] = subprocess.Popen(command, stderr=subprocess.PIPE, text=True)

        for root_doc, run in runs.items():
            _, stderr = run.communicate()
            if run.returncode != 0:
                msg = f"Single-page build of {root_doc} failed:\n{stderr}"
                raise RuntimeError(msg)
            for line in stderr.splitlines():
                logger.warning("%s", line)

        for root_doc in SINGLE_PAGE_GUIDES:
            guide_dir = posixpath.dirname(root_doc)
            single_dir = Path(tmp, root_doc, "html")
            page = Path(single_dir, f"{root_doc}.html").read_text(encoding="utf-8")
            guide_page = Path(outdir, f"{root_doc}.html").read_text(encoding="utf-8")

            # This site's copy of an image must be the one the page was built with
            for image in re.findall(r'src="(_images/[^"]+)"', page):
                if Path(single_dir, image).read_bytes() != Path(outdir, image).read_bytes():
                    msg = f"{root_doc}: {image} differs from the single-page build's"
                    raise RuntimeError(msg)

            def relative_to_guide(match: re.Match[str], guide_dir: str = guide_dir) -> str:
                path = posixpath.relpath(match["path"] or ".", guide_dir)
                if match["path"] in ("", "./"):
                    path += "/"
                return f'{match["attr"]}="{path}{match["rest"]}"'

            page = _RELATIVE_URL.sub(relative_to_guide, page)

            sidebar = _PRIMARY_SIDEBAR.search(guide_page)
            if sidebar is None or _PRIMARY_SIDEBAR.search(page) is None:
                msg = "The theme's left sidebar has moved, update _PRIMARY_SIDEBAR"
                raise RuntimeError(msg)
            page = _PRIMARY_SIDEBAR.sub(lambda _: sidebar[0], page, count=1)

            Path(outdir, guide_dir, "single_page.html").write_text(page, encoding="utf-8")


def _add_page_pdf(app: Sphinx, doctree: nodes.document) -> None:
    """
    Add the PDF that a page names in its ``:pdf:`` field (file-wide metadata,
    a path relative to the page) to the build's downloads, as :download: would.

    _link_page_pdf links the page's download button to it.
    """
    docname = app.env.current_document.docname
    pdf = app.env.metadata[docname].get("pdf")
    if pdf is None:
        return
    rel_filename, filename = app.env.relfn2path(pdf, docname)
    app.env.note_dependency(rel_filename)
    if not os.access(filename, os.R_OK):
        logger.warning("PDF not readable: %s", filename, location=docname)
        return
    app.env.dlfiles.add_file(docname, rel_filename)


def _link_page_pdf(
    app: Sphinx,
    pagename: str,
    templatename: str,
    context: dict[str, Any],
    doctree: nodes.document | None,
) -> None:
    """
    Make the .pdf entry of sphinx_book_theme's download button, which prints
    the page, download the PDF that the page names in its ``:pdf:`` field
    instead (see _add_page_pdf).
    """
    pdf = (context.get("meta") or {}).get("pdf")
    if pdf is None:
        return
    rel_filename, _ = app.env.relfn2path(pdf, pagename)
    download = app.env.dlfiles.get(Path(rel_filename))
    if download is None:  # Not readable: _add_page_pdf warned
        return
    url = context["pathto"](f"_downloads/{download[1].as_posix()}", 1)
    for group in context.get("header_buttons", []):
        buttons = group.get("buttons", [])
        for i, button in enumerate(buttons):
            if button["label"] == "download-pdf-button":
                # The theme renders each button with all its keys as arguments,
                # so the print button's "javascript" must go.
                buttons[i] = {
                    "type": "link",
                    "url": url,
                    "text": button["text"],
                    "tooltip": "Download PDF",
                    "icon": button["icon"],
                    "label": button["label"],
                }
                return
    logger.warning("No .pdf download button to link %s to", pdf, location=pagename)


def setup(app: Sphinx) -> None:
    app.connect("include-read", _update_sensor_placeholder)
    # After sphinx_book_theme's add_header_buttons, at 501, has built the header buttons
    app.connect("html-page-context", _add_header_buttons, priority=502)
    app.connect("html-page-context", _add_print_matter)
    app.connect("doctree-resolved", _link_single_page_references)
    app.connect("build-finished", _build_single_page_guides)
    # After Sphinx's metadata collector (500), which reads the :pdf: field
    app.connect("doctree-read", _add_page_pdf, priority=600)
    # After sphinx_book_theme's add_header_buttons (501), which adds the button
    app.connect("html-page-context", _link_page_pdf, priority=600)
