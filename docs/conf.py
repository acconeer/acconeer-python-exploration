# -*- coding: utf-8 -*-

import os
import sys


conf_dir = os.path.dirname(os.path.abspath(__file__))
root_dir = os.path.join(conf_dir, "..")
sys.path.append(root_dir)

project = 'acconeer-python-exploration'
copyright = '2019, Acconeer AB'
author = 'Acconeer AB'

# version = ''  # The short X.Y version
# release = ''  # The full version, including alpha/beta/rc tags

extensions = [
    'sphinx.ext.mathjax',
    'sphinx.ext.autodoc',
    'sphinx.ext.graphviz',
]

autodoc_member_order = 'bysource'

graphviz_dot_args = []
graphviz_output_format = "svg"

source_suffix = '.rst'

master_doc = 'index'

language = None

exclude_patterns = ['_build', 'Thumbs.db', '.DS_Store']

pygments_style = None

html_theme = 'sphinx_rtd_theme'

html_static_path = ['_static']

htmlhelp_basename = 'acconeer-python-exploration-docs'

latex_elements = {
    'papersize': 'a4paper',
    'pointsize': '11pt',
}

latex_documents = [
    (master_doc, 'acconeer-python-exploration.tex', 'acconeer-python-exploration Documentation',
     'Acconeer', 'manual'),
]

man_pages = [
    (master_doc, 'acconeer-python-exploration', 'acconeer-python-exploration Documentation',
     [author], 1)
]

texinfo_documents = [
    (master_doc, 'acconeer-python-exploration', 'acconeer-python-exploration Documentation',
     author, 'acconeer-python-exploration', 'One line description of project.',
     'Miscellaneous'),
]

epub_title = project

epub_exclude_files = ['search.html']
