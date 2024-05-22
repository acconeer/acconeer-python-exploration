#######################################
Setting up and running Exploration Tool
#######################################

.. youtube:: MxdJxe9-ipw
   :width: 100%


See also our other Getting Started guides:

* *Getting started with the XM126 EVK*: :octicon:`download` `PDF <dev_pdf_xm126_getting_started_>`_
* *Getting started with the XE125 EVK*: `YouTube <yt_xe125_getting_started_>`_, :octicon:`download` `PDF <dev_pdf_xm125_getting_started_>`_
* *Getting started with the A121 EVK*: `YouTube <yt_xe121_getting_started_>`_, :octicon:`download` `PDF <dev_pdf_xe121_getting_started_>`_


.. _installation-and-setup:

*****************************
Exploration Tool Installation
*****************************

Depending on what you wish to accomplish with Exploration Tool or the :doc:`Python API </exploration_tool/api/index>`,
you can install in different ways:

.. tabs::

   .. tab:: :fab:`windows;fa-xl` Quick Start

      If you have a Windows PC and you're only interested in running Exploration Tool to see visualizations,
      experiment with configurations or use the :doc:`/exploration_tool/resource_calc`, the Portable Windows
      package is a great choice.

      Get started with the following steps:

      #. :octicon:`download` `Download the zip <portable_et_download_>`_
      #. Extract the ``.zip`` file in a suitable place
      #. Double-click the ``update`` script
      #. Double-click the ``run_app`` script to start the Exploration Tool Application


   .. tab:: :fab:`python;fa-xl` Python Package (PyPi)

      If you have a PC with Windows or Ubuntu, want to use Python,
      want to run the Exploration Tool Application,
      interested in scripting and using the :doc:`Python API </exploration_tool/api/index>`,
      you can install the `Exploration Tool Python package <et_pypi_>`_:

      If not already installed, install Python by following the video-/PDF guides above or go to `python.org <https://www.python.org/downloads/>`_

      .. code-block::

         python -m pip install --upgrade acconeer-exptool[app]

      .. note::
         Depending on your environment, you might have to replace ``python`` with ``python3`` or ``py``.

      .. dropdown:: Python API in non-graphical environments

         If you only want to use the :doc:`Python API </exploration_tool/api/index>` and not use the
         Exploration Tool Application, for example on a platform that might not support graphical programs
         (like Raspberry Pi), skip installing the graphical dependencies by
         only installing the ``algo`` *extra*:

         .. code-block::

            python -m pip install --upgrade acconeer-exptool[algo]

      If you run into any issues during installation, try installing Exploration Tool
      in a virtual environment (`Guide <venv_guide_>`_)

      Finally, run

      .. code-block::

         python -m acconeer.exptool.app

      to start the Exploration Tool Application.

      .. tip::
         Running the command ``python -m acconeer.exptool.app.new``
         will start the new Exploration Tool directly

   .. tab:: :fab:`github;fa-xl` Source Installation

      If you have a PC with Windows or Ubuntu and want a more flexible install than what's offered
      in the **Python Package** install, Exploration Tool is open source on `GitHub <et_github_>`_.

      This allows you to edit the source code (which should not be done in the other installation options),
      create `Forks <gh_docs_forks_>`_ and much more.

      To install the latest version from source; download or clone the repository from `GitHub <et_github_>`_.
      Run the following command in the newly created directory:

      .. code-block::

         python -m pip install --upgrade .[app]

      .. note::
         Any edit to the source code requires reinstalling ``acconeer-exptool`` unless you are using an editable install:

         .. code-block::

            python -m pip install -e .[app]

         You can read more about editable installs `here <pip_docs_editable_>`_.

      If you run into any issues during installation, try installing Exploration Tool
      in a virtual environment (`Guide <venv_guide_>`_)

      Finally, run

      .. code-block::

         python -m acconeer.exptool.app

      to start the Exploration Tool Application.

      .. tip::
         Exploration Tool is managed with ``hatch`` (`Install guide <hatch_install_>`_), which automates
         virtual environments and the editable install for you.

         After cloning or downloading the repo from GitHub and installing ``hatch``,
         start the Exploration Tool Application by running the command

         .. code-block::

            hatch run app:launcher

         To skip the launcher, you can go to the *new* Exploration Tool directly with

         .. code-block::

            hatch run app:new

****************
Additional Setup
****************

.. tabs::

   .. tab:: :fab:`windows;fa-xl`

      If you encounter any connection issues while following along :ref:`exploration_tool-running` you *might* be missing
      drivers that allow proper function of Acconeer's modules.

      See :doc:`evk_setup/index` for your specific module for more information.

   .. tab:: :fab:`ubuntu;fa-xl`

      After installing the ``acconeer-exptool`` package, you can run:

      .. code-block::

         python -m acconeer.exptool.setup

      which lets you interactively configure your machine and download needed dependencies.
      This is done in order for your machine to work at its best with Exploration Tool.
      ``acconeer.exptool.setup`` performs the same steps that are described in the **Details** below.

      .. dropdown:: Details

         Serial port permissions
            If you are running Linux together with an XM112, XM122, or XM132 module through UART,
            you probably need permission to access the serial port. Access is obtained by adding
            yourself to the ``dialout`` group:

            .. code-block::

               sudo usermod -a -G dialout $USER

            Reboot for the changes to take effect.

            .. note::
               If you have ``ModemManager`` installed and running it might try to connect to the module,
               which has proven to cause problems. If you are having issues, try disabling the ``ModemManager`` service.

         USB permissions
            If you are using Linux together with an XC120, the USB communication is preferred over
            serial port communication. To be able to access the USB device.
            Either run the scripts with ``sudo`` or create an ``udev`` rule as follows. Create and edit:

            .. code-block::

               sudo nano /etc/udev/rules.d/50-xc120.rules

            with the following content:

            .. code-block::

               SUBSYSTEM=="usb", ATTRS{idVendor}=="0483", ATTRS{idProduct}=="a41d", MODE:="0666"
               SUBSYSTEM=="usb", ATTRS{idVendor}=="0483", ATTRS{idProduct}=="a42c", MODE:="0666"
               SUBSYSTEM=="usb", ATTRS{idVendor}=="0483", ATTRS{idProduct}=="a42d", MODE:="0666"
               SUBSYSTEM=="usb", ATTRS{idVendor}=="0483", ATTRS{idProduct}=="a449", MODE:="0666"

            This method is confirmed to work for **Ubuntu 22.04**.

         SPI permissions
            If you are using Linux together with an XM112, you probably need permission to access the SPI bridge USB device.
            Either run the scripts with ``sudo`` or create an `udev` rule as follows. Create and edit:

            .. code-block::

               sudo nano /etc/udev/rules.d/50-ft4222.rules

            with the following content:

            .. code-block::

               SUBSYSTEM=="usb", ATTRS{idVendor}=="0403", ATTRS{idProduct}=="601c", MODE:="0666"

            This method is confirmed to work for ***Ubuntu 22.04**.

         Ubuntu 22.04
            To run the application on Ubuntu 20.04, ``libxcb-xinerama0-dev``, ``libusb-1.0-0`` and
            ``libxcb-cursor0`` needs to be installed:

            .. code-block::

               sudo apt update
               sudo apt install -y libxcb-xinerama0-dev libusb-1.0-0 libxcb-cursor0

            Udev needs to be informed that rules have changed if changes have been made in ``/etc/udev/rules/``:

            .. code-block::

               sudo udevadm control --reload-rules
               sudo udevadm trigger

            An USB device have to be disconnected and reconnected before the udev permissions are updated.


.. _exploration_tool-running:

************************
Running Exploration Tool
************************

Depending on which path you took in :ref:`installation-and-setup`, Exploration Tool is started by either

* Double-clicking the ``run_app`` script,
* Running the command ``python -m acconeer.exptool.app`` in your terminal.

After that, have a look at the functional overview below for an introduction of Exploration Tool:

.. youtube:: NXmYK40akvU
   :width: 100%

Running Example Scripts
=======================

If you followed **Source Installation** in :ref:`installation-and-setup`,  you can
view, edit, and run the examples under the ``examples/`` folder.
If you followed **Python Package (PyPi)** you can download each example directly from `examples/ on GitHub <et_github_examples_>`_.

Some examples are meant to be edited directly and does not support *command line arguments*, but most examples do.
The majority of the examples can be run against our modules via a common set of command line arguments:

.. tip::
	The supported command line arguments can be seen in most examples by running::

		python <some_example.py> --help

A121 Examples' Command Line Arguments
-------------------------------------
The examples in the ``examples/a121/`` folder support the common command line arguments::

   python <some_example.py> --serial-port COMX
   python <some_example.py> --ip-address <ip-address of, for example, a Raspberry Pi>
   python <some_example.py> --usb-device

A111 Examples' Command Line Arguments
-------------------------------------
The examples in the ``examples/a111/`` folder support the common command line arguments::

	python <some_example.py> --uart COMX
	python <some_example.py> --socket <ip-address of, for example, a Raspberry Pi>


.. _dev_pdf_xe121_getting_started: https://developer.acconeer.com/download/getting-started-guide-a121-evk/?tmstv=1716368189
.. _dev_pdf_xm125_getting_started: https://developer.acconeer.com/download/getting-started-guide-a121-xe125/?tmstv=1716368160
.. _dev_pdf_xm126_getting_started: https://developer.acconeer.com/download/getting-started-guide-a121-xe126/?tmstv=1716368093
.. _et_github_examples: https://github.com/acconeer/acconeer-python-exploration/tree/master/examples
.. _et_github: https://github.com/acconeer/acconeer-python-exploration
.. _et_pypi: https://pypi.org/project/acconeer-exptool
.. _gh_docs_forks: https://docs.github.com/en/pull-requests/collaborating-with-pull-requests/working-with-forks/fork-a-repo
.. _hatch_install: https://hatch.pypa.io/latest/install/
.. _pip_docs_editable: https://pip.pypa.io/en/stable/topics/local-project-installs/#editable-installs
.. _portable_et_download: https://developer.acconeer.com/download/portable_exploration_tool
.. _venv_guide: https://packaging.python.org/en/latest/guides/installing-using-pip-and-virtual-environments/
.. _yt_xe121_getting_started: https://www.youtube.com/watch?v=5fCZnHZYJhA&list=PLBXaD001iDmsY03T91ltIomJjMNzmk0aY
.. _yt_xe125_getting_started: https://www.youtube.com/watch?v=Z8lQgxaJFOY&list=PLBXaD001iDmsY03T91ltIomJjMNzmk0aY
.. _yt_xm126_getting_started: https://www.youtube.com/watch?v=MxdJxe9-ipw&list=PLBXaD001iDmsY03T91ltIomJjMNzmk0aY
