.. _exploration_tool-running:

Running Exploration Tool
========================


Launching the Exploration Tool application
------------------------------------------

After :ref:`installation-and-setup`, Exploration Tool is launched with::

    python -m acconeer.exptool.app


Launching the standalone examples
---------------------------------

If you have downloaded the repository from `GitHub <https://github.com/acconeer/acconeer-python-exploration>`__, you can
view, edit, and run the examples under the ``examples/`` folder.

Some examples are meant to be edited directly and does not support *command line arguments*, but most examples do.
The majority of the examples can be run against our modules via a common set of command line arguments:

.. tip::
	The supported command line arguments can be seen in most examples by running::

		python -m <some_example.py> --help

A121 Examples
^^^^^^^^^^^^^
The examples in the ``examples/a121/`` folder support the common command line arguments::

   python -m <some_example.py> --serial-port COMX
   python -m <some_example.py> --ip-address <ip-address of, for example, a Raspberry Pi>
   python -m <some_example.py> --usb-device

A111 Examples
^^^^^^^^^^^^^
The examples in the ``examples/a111/`` folder support the common command line arguments::

	python -m <some_example.py> --uart COMX
	python -m <some_example.py> --socket <ip-address of, for example, a Raspberry Pi>
