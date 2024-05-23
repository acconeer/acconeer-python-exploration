.. _adding-your-own-plugin:

Adding your own plugin
======================
When developing your own algorithm there might be need to be able to add your own plugin to the Exploration Tool App.
To create a plugin the user must follow these steps:

#. **Creating a plugin shell**: The focus is to add a simple shell for a plugin
#. **Implement your plugin**: The main algorithm and plotting development
#. **Plugin import for the App**: Tell the App to import your plugin

Creating a plugin shell
-----------------------
Create a new Python file.

To get started, copy or closely follow the example in :doc:`my_plugin.py <example_scripts/app/examples-app-new-plugins-my_plugin>`.

There are three main parts of a plugin:

#. **Backend**: Defines functions needed by the backend to be able to send and receive data from the plugin

    .. literalinclude:: ../../examples/app/new/plugins/my_plugin.py
        :language: python
        :lines: 95-123

#. **View**: Defines the configuration view of the plugin

    .. literalinclude:: ../../examples/app/new/plugins/my_plugin.py
        :language: python
        :lines: 126-152

#. **Plot**: Defines what plots should be created and how data should be plotted

    .. literalinclude:: ../../examples/app/new/plugins/my_plugin.py
        :language: python
        :lines: 155-206

To register the plugin in the App, two parts are needed:

#. **PluginSpec**: Specification defining the different parts of the plugin

    .. literalinclude:: ../../examples/app/new/plugins/my_plugin.py
        :language: python
        :lines: 209-232

#. **Register function**: Register the plugin

    .. literalinclude:: ../../examples/app/new/plugins/my_plugin.py
        :language: python
        :lines: 235-236


Implement your plugin
---------------------
Plugin implementation is divided into two parts:

#. **Processing**: Process Sparse IQ data to extract relevant information and send to plotting

    .. literalinclude:: ../../examples/app/new/plugins/my_plugin.py
        :language: python
        :lines: 55-92

#. **Plotting**: Plot data produced by the processor

    .. literalinclude:: ../../examples/app/new/plugins/my_plugin.py
        :language: python
        :lines: 200-206



Plugin import for the App
-------------------------

To include the plugin in the App, the plugin module must be specified.
For the example plugin ``my_plugin.py``, this can be done in three way if the user is in the root folder of the repository.

#. **Using python path**:

    (Might not work on Windows)

    .. code-block:: bash

        PYTHONPATH=examples/app/new/plugins python -m acconeer.exptool.app.new --plugin-module my_plugin

#. **Specifying the full module**:

    .. code-block:: bash

        python -m acconeer.exptool.app.new --plugin-module examples.app.new.plugins.my_plugin

#. **Change directory to module**:

    .. code-block:: bash

        cd examples/app/new/plugins
        python -m acconeer.exptool.app.new --plugin-module my_plugin

.. tip::
   You can specify many plugins to load by repeating the ``--plugin-module`` option!
