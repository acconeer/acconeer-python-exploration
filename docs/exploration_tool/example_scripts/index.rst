.. _python_api_example_scripts:

###############
Example Scripts
###############

Some great examples to get started with the :doc:`Python API </exploration_tool/api/index>` are:

* :doc:`python_api/examples-a121-basic`
* :doc:`python_api/examples-a121-plot`
* :doc:`python_api/examples-a121-record_data-barebones`
* :doc:`python_api/examples-a121-load_record`

If you followed **Source Installation** in :ref:`installation-and-setup`,  you can
view, edit, and run the examples under the ``examples/`` folder.
If you followed **Python Package (PyPi)** you can download each example directly from
`examples/ on GitHub <et_github_examples_>`_ or each examples' page here.

Some examples are meant to be edited directly and does not support *command line arguments*, but most examples do.
The majority of the examples can be run against our modules via a common set of command line arguments:

.. tip::
	If an example supports command line arguments, you can see them by running::

		python <some_example.py> --help


A121 Examples' Command Line Arguments
-------------------------------------
The examples in the ``examples/a121/`` folder support the common command line arguments::

   python <some_example.py> --serial-port COMX
   python <some_example.py> --ip-address <ip-address of, for example, a Raspberry Pi>
   python <some_example.py> --usb-device


.. toctree::
   :maxdepth: 2
   :caption: Complete list of example scripts
   :glob:

   */index

.. _et_github_examples: https://github.com/acconeer/acconeer-python-exploration/tree/master/examples
