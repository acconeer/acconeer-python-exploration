:orphan:

This is a template for the documentation structure of our Detectors/Reference Applications/Example Applications. To show which headings and content the documentation should include. Keep the following in mind when you write your documentation:

.. tip::
  * Keep the text as programming language agnostic as possible since this text gets included in the C SDK User Guide when the algorithm gets implemented into C. It is okay to include programming language specific information if it is clear if the information is relevant to Python or C users.

  * Utilize the docstrings available for the API description. The API reference should include enough information so that you understand the meaning of each parameter.

  * Use title case on headings and treat detectors etc. as names, for example: Distance Detector and don't abbreviate Reference Application to Ref. App. in the text (same applied for Example Application).

  * Use a grammar checker when writing your documentation.

  * Don’t forget to link to the glossary, and if any important words are not available there; add them. Linking to the glossary is made by writing :term:`PCR` (syntax: ``:term:`PCR```), but change PCR for the applicable word.

If you want a concrete example to follow, please see: :doc:`Parking Reference Application <ref_apps/a121/parking>`

################################################################
<Name of Detector, Reference Application or Example Application>
################################################################

Introduction
************
Here you should provide a “black-box” description. What is the purpose of the application? What kind of output do you get? What should you use the application for? This section should also state if this is a Detector, Reference Application or Example Application.

The introduction should start with the following sentence (where Reference Application is exchanged for the applicable term):

  This :term:`Reference Application` demonstrates how ..

This section could also include a flowchart showing the inputs and outputs from the application.

Your First Measurement
**********************

This section should include the following text:

  In this section you will find the information needed to make your first measurement with the <name of Detector/Reference Application/Example Application> .

Exploration Tool
================

This section should include a small example of how to run the Detector/Reference Application/Example Application in ET. Should include steps of how to start the measurement and preferably an image of the GUI and quick walk-through of the plots. This section should always link to the :ref:`Getting started page <setting_up_et>`.

Embedded C
==========

This section is only applicable if Detector/Reference Application/Example Application is implemented in C. Could look something like this:

  An embedded C application is provided in the Acconeer SDK, available at the `Acconeer Developer Site <https://developer.acconeer.com/>`_.

  The embedded application uses the same default configuration as Exploration Tool. By default, it prints the result using ``printf`` which usually is connected to stdout or a debug UART, depending on environment. The application is provided in source code.

Configuration
*************
This section should include the following text:

  This section outlines how to configure the <name of Detector/Reference Application/Example Application> in common scenarios.

Presets
=======
Text to describe the presets and when to use them/describing the purpose of each preset. Use the same format for the preset headings as used below:

  The Parking Reference Application has two predefined configurations, available in the application as presets, with the following purposes:

  Ground
    This preset is suitable for scenarios where the sensor is located close to the car, typically for ground-mounted or curb-mounted parking sensors. The update rate of this preset is set to 0.1 Hz to maintain low power consumption, as many ground-mounted parking sensors are battery-powered and do not require a fast response time.

Further Configuration
=====================

Text to describe how to further configure the Detector/Reference Application/Example Application in common scenarios and explain important configuration concepts. For example:

  This section describes further configurations that can be made to tailor the application to your use case.

  Setting the Measurement Range
    Adjustments to the measurement range can be done by changing the range settings (:attr:`~acconeer.exptool.a121.algo.parking._ref_app.RefAppConfig.range_start_m` and :attr:`~acconeer.exptool.a121.algo.parking._ref_app.RefAppConfig.range_end_m`). These determine the approximate range from the sensor wherein you expect to find a part of a car. Note that it is detrimental to the performance to let the range be to close to the sensor, it is not recommended to set the :attr:`~acconeer.exptool.a121.algo.parking._ref_app.RefAppConfig.range_start_m` closer than the :term:`direct leakage<Direct leakage>` allows. This is constricted in Exploration Tool application and API.

Physical Integration
********************
Should describe integration considerations such as lens usage or need to angle the sensor for good performance etc.

Calibration
***********

This section is only applicable when the algorithm utilizes some sort of calibration. This section should describe when calibration should be done. It should also describe if the calibration is dependent on the physical environment or temperature. This section makes the reader understand if the calibration can be done in factory or needs to be done in each integration. It is also important that the reader understands under which circumstances recalibration needs to be made.

<Concepts>
**********
These sections should describe concepts important for the Detector/Reference Application/Example Application, and the heading should be the concept's name. For example: **Thresholds**

<Detector/Ref App/Example App> Output
*************************************
Text to describe the output from the Detector/Ref App./Example App in more detail (compared to the black box description above) so that the user knows how to interpret the result.

Algorithm Signal Processing
***************************
This section should include text to describe the algorithm. This section is for users that want to know what kind of signal processing we do. Flow-charts are welcome. This should be the only section where mathematical formulas are used. This is to keep the rest of the text accessible for all kinds of users.

Memory and Power Consumption
****************************
Only applicable for algorithms implemented in C. The memory and power consumption are already provided in the SW User Guide but should also be available here. It’s important to note which module the memory and power consumption figures are applicable for, for example: XM125. See :doc:`Parking Reference Application <ref_apps/a121/parking>` for an example.

Test Results
************
This section should describe how we have tested the algorithm and the test results.

Exploration Tool Python API
***************************
This section should include the auto generated Exploration Tool API reference for this Detector/Reference Application/Example Application.

C API
*****
Only applicable for algorithms available in C. This should just be a short text which describes where the reader can find the C API reference for this Detector/Reference Application/Example Application.
