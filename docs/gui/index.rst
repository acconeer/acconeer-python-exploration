.. _gui-introdution:

Working with the GUI
====================
Acconeer offers a comprehensive GUI for the Python Exploration Tool to work with our sensors.
The tool is meant as a companion throughout your project; it should help you getting started quickly with testing and evaluating our sensor for your use-case, but also support you in finding the optimal sensor settings and fine-tuning the data processing for your final product implementation.

The general work-flow with the Python Exploration Tool GUI is described in the following:

.. figure:: /_static/gui/work_flow.png

   Exploration tool with numbered work steps


#. :ref:`Connect to a sensor <connect-sensor>`
#. :ref:`Select a service or detector <gui-select-service>`
#. :ref:`configure-sensor`
#. :ref:`collect-data`

    - :ref:`start-stop`
    - :ref:`background-data`
    - :ref:`replay-data`
    - :ref:`save-load`

#. :ref:`optimizing-detector`

.. toctree::
   :maxdepth: 1
   :glob:
   :hidden:

   working_with_the_gui/connect_sensor
   working_with_the_gui/select_service
   working_with_the_gui/sensor_configuration
   working_with_the_gui/collect_data
   working_with_the_gui/optimizing_detectors

Getting started
===============
The Exploration Tool has been tested on the following operating systems

- Windows 10
- Ubuntu (18.04, 20.04)
- WSL (Windows Subsystem for Linux)

but others should work fine, too (such as macOS or other versions of Linux).
Installing the Exploration Tool GUI on a Raspberry Pi is not supported!
(You can still use the Exploration Tool without graphical interface on the Raspberry Pi.)

.. attention::
    In order to get started, you need either a Raspberry Pi with an XC/XR112 (:ref:`setup_raspberry`) or one of our modules with the latest firmware (:ref:`setup_xm112`, :ref:`setup_xm122`, :ref:`setup_xm132`).

First, you should clone the Exploration Tool repository from `GitHub <https://github.com/acconeer/acconeer-python-exploration>`_.
There, you can find detailed instructions for installing our libraries; in a nut-shell:

#. Make sure you have Python 3.6 or newer installed.
#. Install the required packages (you might have to replace python with python3 or py)::

    python -m pip install -U --user setuptools wheel
    python -m pip install -U --user -r requirements.txt

#. Install the acconeer.exptool library::

    python -m pip install -U --user .

#. Once, you have installed everything, you can start the GUI from the root of the repository via::

    python gui/main.py


GUI Framework
=============
The GUI acts as a front-end to the Python Exploration Tool.
It handles sensor connections, sensor settings and allows you to test examples, tune detectors and save and load data for in-depth analysis or easy sharing.
In below figure, you can find a top-level depiction of the data-flow and control connections between the GUI and the Exploration Tool.

.. figure:: /_static/gui/gui_flow.png

   Framework of the Python Exploration Tool GUI

.. attention::
    The GUI never stores processed data, only the original service data, including all sensor and detector settings. Whenever you replay data (saved or buffered), the processing is always redone on the original sensor data.
