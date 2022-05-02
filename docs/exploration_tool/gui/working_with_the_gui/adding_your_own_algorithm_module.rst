.. _adding-your-own-algorithm-module:


Adding your own algorithm module
================================
At some point you may want to write your own example for your algorithm and use the Exploration Tool App to test and tune it.
We will need to do the following steps:

#. **Creating an algorithm module**: This is where almost all coding happens
#. **Module import for the App**: Tell the App to import your algorithm module

We will cover these steps in the following sections.

.. note::
    This requires you to download the source code of Exploration Tool, via ``git`` or as a ``.zip`` file.


Creating an algorithm module
----------------------------
In this example we will create a toy algorithm, where we will plot Envelope frames in
in Exploration Tool. We will also be able to change the color of the plot and scale the
data by some settable factor.


The toy algorithm module
^^^^^^^^^^^^^^^^^^^^^^^^

Create a new file in the :github_1a5d2c6:`src/acconeer/exptool/a111/algo/` folder.

You can copy-paste the example below and name it something nice; like ``my_algorithm_module.py`` for example.


.. literalinclude:: docs_my_algorithm_module.py
    :language: python
    :linenos:
    :emphasize-lines: 11, 25, 60, 81, 124-134

The ``ModuleInfo`` is what is sent to the App.
If your ``my_algorithm_module.py`` file defines a valid ``ModuleInfo``, the App
will populate buttons and settings automatically for you.


.. note::
   ``ModuleInfo`` accept classes, not instances:

   .. code-block::

      processor=MyNewProcessor,    # <- Correct!

      processor=MyNewProcessor(),  # <- Wrong!


Multi-sensor support
^^^^^^^^^^^^^^^^^^^^
There are three options for handling multi-sensor support:

#. Do not allow multiple sensors --> set ``mutli_sensor = False``
#. Allow multiple sensors        --> set ``mutli_sensor = True``

    a) Use a wrapper (multiplies graphs and plots, when you select more than one sensor).
       Basic wrappers for your ``Processor``- and ``PGUpdater`` classes are defined in
       :github_1a5d2c6:`acconeer.exptool.a111.algo.utils <src/acconeer/exptool/a111/algo/utils.py>`.
    b) Define plots and graphs for individual sensors in your processor


Note about file structure
^^^^^^^^^^^^^^^^^^^^^^^^^
We at Acconeer have split up this file in multiple files and put those files in a folder.
This is not necessary to do for your first example, but if you want to look att how we have done things, you can find
the corresponding classes and functions in the following places:

+-------------------+----------------------------------------------------------------------------------+
| File              | Class/Function                                                                   |
+===================+==================================================================================+
| ``_meta.py``      | ``ModuleInfo``                                                                   |
+-------------------+----------------------------------------------------------------------------------+
| ``_processor.py`` | ``ProcessingConfiguration``, ``get_sensor_config()/SensorConfig``, ``Processor`` |
+-------------------+----------------------------------------------------------------------------------+
| ``ui.py``         | ``PGUpdater``                                                                    |
+-------------------+----------------------------------------------------------------------------------+

You might come across some other files aswell, but they are not important for now.


Module import for the App
-------------------------
The App only needs to import your ``ModuleInfo``, which we have called ``my_module_info`` for this example.

Import your newly created file in :github_1a5d2c6:`src/acconeer/exptool/app/elements/modules.py` file,
which defines the services and detectors loaded into the App, to include the new algorithm module.

.. code-block:: python
   :emphasize-lines: 6, 14

    import acconeer.exptool.a111.algo.breathing._meta as breathing_meta
    import acconeer.exptool.a111.algo.button_press._meta as button_press_meta

    ...

    from acconeer.exptool.a111.algo import my_algorithm_module

    MODULE_INFOS = [
        envelope_meta.module_info,
        iq_meta.module_info,

        ...

        my_algorithm_module.my_module_info,
    ]

    ...

.. note::
    Unless you have an editable install of Exploration Tool, you will need to reinstall after editing ``modules.py``

That's it! Now, lets have a look at what we've accomplished.

.. figure:: /_static/gui/my_new_algorithm_module_select_service.png
    :figwidth: 40%
    :align: right

If we take a look at the **Scan controls** section, press the drop-down and scroll all the way down. We should see
**My Algorithm Module** appear.

Select it, and start a new measurement. Voila!


.. raw:: html

    <video width="100%" controls>
        <source src="/_static/gui/final_product.mp4">
    </video>
