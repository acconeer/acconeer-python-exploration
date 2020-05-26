.. _optimizing-detector:

Optimizing detectors
====================
When you are working on implementing a detector into your embedded system, tuning and data analysis can become difficult, especially when live data fetching and plotting is not possible or available.

.. _processing-settings:
.. figure:: /_static/gui/processing_settings.png
    :figwidth: 40%
    :align: right

    Processing settings for the Obstacle detector

This is where the Exploration Tool GUI can greatly speed up your project.
For some detectors Acconeer offers C-reference code, and the corresponding detector in the GUI uses the same settings and parameters and the processing is kept as similar as possible.
For most cases, processing results are nearly identical between C-code and Python code, so that you can simply copy your settings between both platforms.

At the moment we have the following detectors matched with C-code and verified that the processing is within the expected precision (see :numref:`c-python`):

   - :ref:`Distance Detection <distance-detector>`
   - :ref:`Obstacle Detection <obstacle-detection>`
   - :ref:`Presence Detection <sparse-presence-detection>`

Regardless, of whether you are working with one of these detectors or any other example, all detector relevant settings can be found in the **Processing settings** tab on the left side of the GUI.

Since the GUI only stores the unprocessed service data, you can always save/load/replay data and change and optimize the settings until they meet your requirements.

.. attention::
    When you save data, the last settings used during the scan will be stored in the saved file. Those settings will be restored when loading and can be changed again when replaying.

Often, you can find a **Processing settings** and **Advanced processing settings** tab.
Internally, there is no difference between those two tabs, but for the sake of keeping the GUI compact and easy to use, we have sorted them into these two groups and are collapsing the **Advanced processing settings** tab by default.

.. _c-python:
.. figure:: /_static/gui/c_python.png

    Comparison of FFT amplitude analysis using C-code and Python with the Obstacle detector
