.. _select-service:

Select service
=======================================
.. figure:: /_static/deep_learning/select_service_01.png
    :align: center

    Overview of the "Select features" tab.

Description of tab areas (roughly in order of work flow):

1. Select interface and connect to sensor
2. Select service
3. Configure sensor settings
4. Start/Stop measurement or Save/Load/Replay previous measurement
5. Service specific plotting of sensor data frames
6. Number of sensor data frames and number of missed data frames


At this point, we assume that you have familiarized yourself with the general functionality of our standard GUI and the general functionality of our sensor (see :ref:`sensor-intro`).
The first step is to select a service providing data best suited for your specific use case, and thus this tab is much like the normal python exploration tool.
The main difference is that you can only select services (:ref:`iq-service`, :ref:`envelope-service` and :ref:`sparse-service`), not examples or detectors, since these include post-processing.
If you would like to use on of our examples or detectors as input, you need to add it as a feature (see :ref:`select-features`).

If you are unsure about which service will work best, we recommend to set up a typical scenario of your use-case and check the sensor response for the different services.
This could be placing a piece of carpet or other material under the sensor or waving your hand in front it.

There is no general rule about which service is best for what application, but you can look at the following list as guidance:

- Material detection:
    * Try IQ:
    * Set profile to 1 to resolve finer structures (at the cost or reduced SNR)
    * Sensor update-rate can be low (10th of Hz)
    * If you use it with a moving robot, you might want to increase the senor update-rate to match the response time with the robot speed
    * Try to measure between :math:`10 - 30\,\text{cm}`
    * Try features extracting averages, variances, FFT, autocorrelation
- Macro gesture detection (large motion, like waving hand):
    * Try Sparse or Envelope
    * Set profile to 1 for :math:`<10\,\text{cm}` otherwise to 2
    * Sensor update-rate should be high (upwards of :math:`60\,\text{Hz}` depending on speed of gesture)
    * For Sparse, try Sampling mode A with 64 sweeps per frame
    * Detecting macro gestures past :math:`1\,\text{m}` might prove difficult
    * Try FFT or Presence sparse feature
- Micro gesture detection (small motion, like moving fingers):
    * Try Sparse
    * Set profile to 1 for :math:`<10\,\text{cm}` otherwise to 2
    * Sensor update-rate should be high (upwards of :math:`60\,\text{Hz}` depending on speed of gesture)
    * Try Sampling mode A with 64 sweeps per frame
    * Detecting micro gestures past :math:`50\,\text{cm}` might prove difficult
    * Try FFT or Presence sparse feature

You should set the range start and end of the sensor data to roughly match the detection volume for your use-case.
Adding a few cm margin is recommended.
You can change the range and other sensor settings in the next tab, if you need to adjust them.
Once you have confirmed that the selected service provides data suitable for your use-case, you can switch to the next tab.
It is good if you can see a change in the service data for each of your different prediction cases at this point, but if not, you have the possibility to live-test your set of features in the next tab and change the service type if necessary.
