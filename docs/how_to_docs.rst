###########
How to docs
###########

This documentation is internal and is displayed since you ran
``sphinx-autobuild -t internal`` (which is part of ``hatch run docs:autobuild``).

The following sections will provide you with some good links to resources
and information about how our sphinx setup works.

**********************
Setup for docs writing
**********************

#. `Install pipx <pipx_install_gh_>`_
#. `Install hatch <hatch_install_>`_
#. Run ``hatch run docs:autobuild``
#. Open http://127.0.0.1:8000/ in your browser.

.. _pipx_install_gh: https://github.com/pypa/pipx?tab=readme-ov-file#install-pipx
.. _hatch_install: https://hatch.pypa.io/latest/install/#pipx

************************
Our Sphinx configuration
************************

We use `Sphinx <https://www.sphinx-doc.org/en/master/>`_ to build our documentation.
Our documentation (and Sphinx documentation) is typically written in a markup called
`reStructuredText <https://en.wikipedia.org/wiki/ReStructuredText>`_, although other formats
can be used.

We use the theme `Sphinx Book Theme <https://sphinx-book-theme.readthedocs.io/en/stable/>`_
and a handful of extensions (plugins).

All of this is configured in the file ``docs/conf.py``.

Spell checking
==============

We run spell checks using `sphinxcontrib-spelling <https://sphinxcontrib-spelling.readthedocs.io/en/latest/index.html>`_.
The supplementary wordlist can be found in ``docs/spelling_wordlist.txt``


*****************************
Reference-/Learning Resources
*****************************

* `A Sphinx Cheat Sheet <cheatsheet_>`_
* `reStructuredText Primer <primer_>`_
* `Our theme's elements <sbt_elements_>`_
* `Sphinx autodoc Docs <autodoc_>`_

.. _cheatsheet: https://sphinx-tutorial.readthedocs.io/cheatsheet/
.. _primer: https://www.sphinx-doc.org/en/master/usage/restructuredtext/basics.html
.. _autodoc: https://www.sphinx-doc.org/en/master/usage/extensions/autodoc.html
.. _sbt_elements: https://sphinx-book-theme.readthedocs.io/en/stable/reference/kitchen-sink/index.html

****
Tips
****

Documentation Structure
   The only thing that decides the documentation structure is
   ``..toctree::`` s., **NOT** the file structure (Except when ``:glob:`` is used).

Navigation on left hand side gets of sync.
   This a common occurence when modifying the documentation structure
   (modifying ``.. toctree::`` s.).
   Re-running ``hatch run docs:autobuild`` will remove the folder ``docs/_build``
   and eliminate the issue.

*************
VS Code Setup
*************

Install the extensions Python and reStructuredText. Hit Ctrl-Shift-P, search for "Python: Select Interpreter", and select Python 3. When VS Code asks how to generate HTML, select Sphinx. If VS Code doesn't ask, hit the gear icon in the statusbar when you have an .rst document open.

Some good resources:

* http://docutils.sourceforge.net/docs/user/rst/quickref.html
* https://sphinx-rtd-theme.readthedocs.io/en/stable/index.html


********************
Public landing page:
********************

.. this file is included in docs/index.rst just before all landing page contents,
.. making this a header for the public landing page.
