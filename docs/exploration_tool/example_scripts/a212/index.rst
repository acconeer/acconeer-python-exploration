.. _python_api_a212_example_scripts:

####################
A212 Example Scripts
####################

A great example to get started with the :doc:`Python API </exploration_tool/api/a212>` is:

* :doc:`python_api/examples-a2-record_data-barebones`

If you followed **Source Installation** in :ref:`installation-and-setup`,  you can
view, edit, and run the examples under the ``examples/a2/`` folder.

Some examples are meant to be edited directly and does not support *command line arguments*, but most examples do.
The majority of the examples can be run against our modules via a common set of command line arguments:

.. tip::
   If an example supports command line arguments, you can see them by running::

      python <some_example.py> --help


Command Line Arguments
-------------------------------------
The examples in the ``examples/a2/`` folder support the common command line arguments::

   python <some_example.py> --serial-port COMX
   python <some_example.py> --ip-address <ip-address of, for example, a Raspberry Pi>
   python <some_example.py> --usb-device

.. toctree::
   :maxdepth: 2
   :caption: Complete list of example scripts
   :glob:

   */index
