.. _sensor-intro:


Radar sensor introduction
=========================


Welcome!
--------

We are very happy that you have decided to have a closer look at what Acconeer’s pulsed coherent radar technology can offer. We are working hard to give you the right tools to **“Explore the Next Sense”**, whether it is for remote monitoring of vital signs, smart city IoT, robot navigation or any other imaginable sensing application where precision, size, and power consumption are key parameters.
This document serves as an introduction to Acconeer’s sensor technology and product offer. The Acconeer radar system is described based on established radar theory to give you the right knowledge to integrate and configure the sensor in your product.

When starting to use the Acconeer sensor there are different alternatives for both hardware and software setup and we are adding more as we get to know your needs. Check out our website to see our current offer of sensors, modules, and evaluation kits. A typical development flow to get started is to setup one of our evaluation kits and:

* Use the `Exploration Tool <https://github.com/acconeer/acconeer-python-exploration>`__ to get data from sensor into Python to start application development for your use case

* Use our Reference applications to get guidance on use case specific software solutions

* Use Acconeer SDK or Acconeer Module Software to start software development

To further support and guide you through the development process we also provide several user guides, data sheets, reference schematics, and reference layouts, which you can find at `acconeer.com <https://acconeer.com>`__. Also check out our `demo videos <https://www.youtube.com/channel/UC56HMJfKPSpamS-kMHXOcAw>`__ and `application page <https://www.acconeer.com/applications>`__ to get inspiration on how you can solve different use cases and how the Acconeer sensor can be used in your application.

.. figure:: /_static/introduction/fig_selected_use_cases.png
    :align: center
    :width: 38%

    Selected use cases.

Radar basics and the Acconeer pulsed coherent radar
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Radar is a well-established technology which has been used in many different applications where accurate and robust distance measurement is required. You can find radar in cars, in the process industry, in airplanes etc. However, most often these radar systems are big, power hungry and expensive, what Acconeer offer is a way to take radar into applications where size, cost and power consumption matter.
Radar is an acronym for Radio Detection and Ranging and is a way of determining range to an object by transmitting and detecting radio waves. Acconeer’s radar system is a time-of-flight system, which means that a radio wave is transmitted by a first antenna, reflected by an object, and then received by a second antenna. The time of flight between transmission and reception of the signal is measured, as illustrated in :numref:`fig_sensor_wave_object`.

.. _fig_sensor_wave_object:
.. figure:: /_static/introduction/fig_sensor_wave_object.png
    :align: center

    Illustration of the pulsed coherent radar system where the time of flight is measured to determine distance to object

The distance to the object can then be calculated by multiplying the time-of-flight with the speed of the radio wave (same as speed of light) and then dividing by two as the distance the signal has traveled is equal to two times the distance to the object. More details about the radar and the Acconeer approach can be found in the chapter `System Overview`_.

There are different approaches to building radar systems, each with its own pros and cons that typically results in a trade-off between accuracy and power consumption, see :numref:`fig_pulsed_coherent_radar`. At Acconeer we have solved this by combining two important features of a radar system, the first is that it is pulsed, which means that the radio part is shut down in between transmission of signals. In fact, the Acconeer radar is pulsed so fast that, typically, the radio is active less than 1 % of the time even when transmitting at maximum rate. This is how the power consumption can be kept low and optimized dependent on the update rate required by your application.

.. _fig_pulsed_coherent_radar:
.. figure:: /_static/introduction/fig_pulsed_coherent_radar.png
    :align: center
    :width: 60%

    Pulsed coherent radar.

The second feature is that it is coherent, which means that each transmitted signal has a stable time and phase reference on the pico second scale, which allows for high accuracy measurements. Coherent radar systems usually rely on a continuous generation of the radio signal, which consumes a lot of current independent on update rate, hence one of the innovations Acconeer has made is to combine the benefits of pulsed systems and the benefits of coherent systems into one product, the Pulsed Coherent Radar (PCR).
The unique selling points of the PCR sensor are summarized in :numref:`fig_unique_selling_points`. The sensor makes it possible to perform high accuracy measurements while consuming very little power and the fast pulsing of the system makes it possible to track fast movements.

.. _fig_unique_selling_points:
.. figure:: /_static/introduction/fig_unique_selling_points.png
    :align: center
    :width: 85%

    Unique selling points of the Acconeer pulsed coherent radar.

Another benefit of the pulse coherent radar is that amplitude, time and phase of the received signal can be handled separately and allow for classification of different materials that the signal has been reflected on. These are all benefits when compared to sensors such as infra-red and ultrasonic. Additional benefits are that the Acconeer radar can be hidden behind colored plastic or glass and hence do not need an open or visible aperture, we call this optimized integration. The sensor is also robust as it is not sensitive to ambient light or sound and not sensitive to dust or even color of the object.


The Acconeer offer
^^^^^^^^^^^^^^^^^^

The Acconeer offer consists of two parts, hardware and software, as illustrated in :numref:`fig_acconeer_offer`. In addition, Acconeer also provides various tools to aid the customer in the development process.

.. _fig_acconeer_offer:
.. figure:: /_static/introduction/fig_acconeer_offer.png
    :align: center

    The Acconeer offer.

The A111 sensor is the core of the hardware offer and is available in modules and in evaluation kits. The purpose of the evaluation kit is to provide a platform to get acquainted with the pulsed coherent radar and to start use case evaluation. The sensor evaluation kits are based on Raspberry Pi, which is a well-known and available platform which also allows you to connected other types of sensors. The module is an integration of the A111 and a microcontroller unit (MCU) and has its own evaluation kit. Just as the sensor evaluation kit it can be used to get familiar with the pulsed coherent radar technology and get started with use case development. It can also be included as a single unit in your product to decrease your development cost and decrease time to market.

:numref:`fig_system_structure` outlines the software structure, platform for running it, and communication interfaces. The software for controlling the A111 sensor and retrieving data from it is called Radar System Software (RSS) and provides output at two levels:

* Service, provides pre-processed sensor data

* Detector, provides results based on the sensor data - all Detectors are based on Services

.. _fig_system_structure:
.. figure:: /_static/introduction/fig_system_structure.png
    :align: center
    :width: 65%

    System structure, the RSS software runs on a host that controls the sensor.

RSS is provided as library files and is written in C and designed to be portable between different platforms, a list of currently supported processor architectures and toolchains are available at the `Acconeer developer site <https://developer.acconeer.com>`__. Apart from RSS, Acconeer provides Example applications and stubbed software integration source code in the Software development kits (SDKs) as well as full reference integrations for selected platforms.

Acconeer provides four types of applications:

* Example applications: Example of how to use RSS, available in SDK at Acconeer developer site

* Reference applications: Use case specific reference application available in SDK at Acconeer developer site

* Exploration server: Application streaming data from sensor evaluation kit to PC, available in SDK for Raspberry Pi at Acconeer developer site

* Module server: Application providing a register write based interface to Acconeer modules, available in Module software image at Acconeer developer site.

Both RSS and Applications run on a host platform and Acconeer provides a software integration reference with guidance on how to integrate to your host platform as well as specific integration for the modules and evaluation kits that Acconeer provides.

* For our EVK platforms we provide a software package and for

    * Raspberry Pi it includes hardware abstraction layer, device drivers, and build environment provided as source code

    * Modules it includes hardware abstraction layer and build environment provided as source code

* For STM32 platforms we provide example integration files and instructions for how to set up a project in STM32CubeIDE.

* Other ARM Cortex M0, M4 and M7 based platform can easily be used by writing a custom implementation of the HAL integration layer. A handful functions that use MCU specific driver functions for accessing timers, SPI and GPIO have to be implemented.

For more detailed information on how to implement the HAL integration layer used by RSS, there is a user guide available at `developer.acconeer.com <https://developer.acconeer.com>`__ under *Documents and learning > SW*.

Based on these deliveries it is possible for the customer to create their own integration layer for any platform that uses a supported processor architecture. The currently available products and corresponding software deliveries are listed in :numref:`fig_product_sw_offer`, refer to documentation for each specific product for further details.

.. _fig_product_sw_offer:
.. figure:: /_static/introduction/fig_product_sw_offer.png
    :align: center
    :width: 92%

    Products and software deliverables.

At `acconeer.com <https://acconeer.com>`__, there are modules and SDK variants and they all contain RSS, Software integration, and Example applications. The Module software image contains RSS, software integration, and Module server.
The module can be used in two different setups:

* Stand-alone module: The module has got no dependency on external controllers. The application is customized to a specific use case by the customer and runs on the embedded MCU. The customers application is accessing the RSS API via a software interface.

* Controlled module: The module is connected to an external controller where the customer runs their application software. The customers are accessing the RSS API via a hardware interface through the module software, that provided register mapped protocol.

The two setups listed above are also illustrated in :numref:`fig_setups`.

.. _fig_setups:
.. figure:: /_static/introduction/fig_setups.png
    :align: center
    :width: 97%

    Setup.

For the Stand-alone module setup the customer should use the RSS library and Software integration source code provided in the corresponding SDK and build their own application on these deliveries. For the Controlled module regime, i.e. the modules designed by Acconeer, the complete software that runs on the module is delivered as an image. The customer can freely select between these two options, Acconeer supports both.


.. _Acconeer tools:

The Acconeer tools
^^^^^^^^^^^^^^^^^^

To help you to get to know the Acconeer products and get started quickly with application development we provide a Python based tool which consists of several scripts that gives you access to real time data and sensor configuration to easily start developing signal processing for specific use cases. The scripts can also be used to graphically display the radar output and to investigate the reflective properties of different objects. The Exploration Tool requires that the exploration server or Module server is installed on your sensor evaluation kit or module evaluation kit, respectively. The exploration server and Module server reflects the RSS API, which helps to understand how to manage the RSS API in your application. The Exploration Tool is provided for all our evaluation kits and is available at `Acconeer GitHub <https://github.com/acconeer/acconeer-python-exploration>`__. An overview of how Exploration Tool interface software and hardware for the evaluation kits is presented in :numref:`fig_sw_hw_if`.

.. _fig_sw_hw_if:
.. figure:: /_static/introduction/fig_sw_hw_if.png
    :align: center
    :width: 97%

    Overview of software and hardware interfaces to Acconeer tools.


Services and Detectors
----------------------

The RSS provides output at two different levels, Service and Detector. The Service output is pre-processed sensor data as a function of distance. Detectors are built with this Service data as the input and the output is a result, in the form of e.g. distance, presence, angle etc. Services and Detectors currently available are listed in :numref:`fig_detectors_services`.

.. _fig_detectors_services:
.. figure:: /_static/introduction/fig_detectors_services.png
    :align: center
    :width: 70%

    Available Detectors and Services.

Each Detector is built on top of a Service, i.e. you have the possibility to use our out-of-the-box Detectors or develop your own. To select the Service or Detector applicable for your use case it is recommended to use the Exploration tool (see Section `Acconeer tools`_) to observe the different outputs and understand what they represent. Each Service and Detector also comes with its own user guide, which can be found at `acconeer.com <https://acconeer.com>`__.

At `developer.acconeer.com <https://developer.acconeer.com>`__, we have several movies showing demos where the Acconeer sensor is used in different use cases. Together with the demo movies, corresponding reference applications are available in our different SDKs at Acconeer developer site. These reference applications are written in C code and use our Services and Detectors, check them out to get inspiration on how to build your product with the Acconeer sensor.


Services
^^^^^^^^

Envelope and Power Bins services
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

:numref:`fig_power_bins_demo` and :numref:`fig_env_demo` show outputs from the Power Bins and Envelope Services obtained with one of the scripts in Exploration Tool, the setup and environment are identical for the two data sets. Here it can be seen that Power Bins and Envelope Services provide output of the same type, i.e. amplitude of received signal as a function of distance. The difference lies in the signal processing done and the Power Bins output has lower SNR, lower resolution in range, but requires less processing and memory allocation than Envelope.

.. _fig_power_bins_demo:
.. figure:: /_static/introduction/fig_power_bins_tool_demo.png
    :align: center

    Output from the Power Bins service in Exploration Tool. Each bin correspond to a region of the scanned range, where Bin 1 is closest to the sensor.

.. _fig_env_demo:
.. figure:: /_static/introduction/fig_env_tool_demo.png
    :align: center

    Output from the Envelope service in Exploration Tool.


IQ service
~~~~~~~~~~

The IQ Service provides complex data in cartesian form, which is shown in :numref:`fig_iq_demo` with distance on the third axis and data taken with the same setup as for Envelope and Power bins in :numref:`fig_power_bins_demo` and :numref:`fig_env_demo`.

.. _fig_iq_demo:
.. figure:: /_static/introduction/fig_iq_tool_demo.png
    :align: center

    Output from the IQ Service in Exploration Tool.

The cartesian data can be transformed to polar data providing phase and amplitude of the signal. Having the phase of the signal available makes it possible to perform more accurate measurements as compared to the Power bins and Envelope Services where only the amplitude is available. This is illustrated in :numref:`fig_wavelet` where an object is moving towards the radar. The envelope of the signal only varies slightly when the object is moving, while the value of the coherent signal at a fixed time delay varies substantially. This change will be present in the phase of the data from the IQ Service.

.. _fig_wavelet:
.. figure:: /_static/introduction/fig_wavelet.png
    :align: center
    :width: 95%

    Illustration of envelope and phase change of a received pulse for a reflection from a moving object, what is returned from the IQ Service is in cartesian form.

The IQ Service is the choice when high accuracy is required, and higher processing power and memory allocation can be tolerated.


Sparse service
~~~~~~~~~~~~~~

The other services, :ref:`envelope-service`, :ref:`iq-service`, and :ref:`pb-service`, are all based on sampling the incoming waves several times per wavelength (effectively ~2.5 mm). In the Sparse service, the incoming waves are instead sampled approximately every 6 cm and the amount of processing is minimal, which makes Sparse data fundamentally different from data generated by the other services.

Due to the highly undersampled signal from the sparse service, it should not be used to measure the reflections of static objects. Instead, the sparse service should be used for situations, where detecting moving objects is desired. Sparse is optimal for this, as it produces sequences of very time accurate measurements at these sparsely located sampling points. More details `here <https://docs.acconeer.com/en/latest/services/sparse.html>`__.


Detectors
^^^^^^^^^

Detectors take Service data as input and produce a result as the output that can be used by the application. Currently we have four Detectors available that produce different types of results and that are based on different Services. User guides for the different Detectors are available at `acconeer.com  <https://developer.acconeer.com/>`__ and the Detectors are also available in the Exploration Tool.

In addition, we provide several Reference applications which use Services or Detectors to demonstrate how to develop applications based on our technology, you can find these in the various SDKs at Acconeer developer site.


Distance detector
~~~~~~~~~~~~~~~~~~~~~~

This is a distance detector algorithm built on top of the :ref:`envelope-service` service -- based on comparing the envelope sweep to a threshold and identifying one or more peaks in the envelope sweep, corresponding to objects in front of the radar. The algorithm both detects the presence of objects and estimates their distance to the radar. More details about the detector is found `here <https://docs.acconeer.com/en/latest/processing/distance_detector.html>`__.


Presence detector
~~~~~~~~~~~~~~~~~

Detects changes in the environment over time based on data from the Sparse service. More details about the detector is found `here <https://docs.acconeer.com/en/latest/processing/presence_detection_sparse.html>`__.


Obstacle detector
~~~~~~~~~~~~~~~~~

Assumes that the Acconeer sensor is placed on a moving object with a known velocity, such as a robotic vacuum cleaner or lawn mower. The detector creates a virtual antenna array and uses synthetic aperture radar (SAR) signal processing to localize objects. This detector is used in the Obstacle localization demo movie. More details about the detector is found `here <https://docs.acconeer.com/en/latest/processing/obstacle.html>`__.


.. _ System Overview:

System overview
---------------

The Acconeer sensor is a mm wavelength pulsed coherent radar, which means that it transmits radio signals in short pulses where the starting phase is well known, as illustrated in :numref:`fig_transmit_signal_length`.

.. _fig_transmit_signal_length:
.. figure:: /_static/introduction/fig_transmit_signal_length.png
    :align: center

    Illustration of the time domain transmitted signal from the Acconeer A111 sensor, a radar sweep typically consists of thousands of pulses. The length of the pulses can be controlled by setting Profile.

These transmitted signals are reflected by an object and the time elapsed between transmission and reception of the reflected signal (:math:`t_{delay}`) is used to calculate the distance to the object by using

.. math::
    :label: eq_dist

    d=\frac{t_{delay}v}{2}

.. math::
    :label: eq_speed_of_light

    v=\frac{c_0}{\sqrt{\varepsilon_r}}

where :math:`\varepsilon_r` is the relative permittivity of the medium. The '2' in the denominator of :eq:`eq_dist` is due to the fact that :math:`t_{delay}` is the time for the signal to travel to the object and back, hence to get the distance to the object a division by 2 is needed, as illustrated in :numref:`fig_sensor_wave_object`.
The wavelength :math:`\lambda` of the 60.5 GHz carrier frequency :math:`f_\text{RF}` is roughly 5 mm in free space.
This means that a 5 mm shift of the received wavelet corresponds to a 2.5 mm shift of the detected object due to the round trip distance.

:numref:`fig_block_diagram` shows a block diagram of the A111 sensor. The signal is transmitted from the Tx antenna and received by the Rx antenna, both integrated in the top layer of the A111 package substrate. In addition to the mmWave radio the sensor consists of power management and digital control, signal quantization, memory and a timing circuit.

.. _fig_block_diagram:
.. figure:: /_static/introduction/fig_block_diagram.png
    :align: center

    Block diagram of the A111 sensor package, further details about interfaces can be found in the A111 data sheet.

:numref:`fig_envelope_2d` shows a typical radar sweep obtained with the Envelope Service, with one object present. The range resolution of the measurement is ~0.5 mm and each data point correspond to transmission of at least one pulse (depending on averaging), hence, to sweep 30 cm, e.g. from 20 cm to 50 cm as in :numref:`fig_envelope_2d`, requires that 600 pulses  are transmitted. The system relies on the fact that the pulses are transmitted phase coherent, which makes it possible to send multiple pulses and then combine the received signal from these pulses to improve signal-to-noise ratio (SNR) to enhance the object visibility.

.. _fig_envelope_2d:
.. figure:: /_static/introduction/fig_envelope_2d.png
    :align: center

    Output from Envelope service for a typical radar sweep with one object present.


Radar sensor performance metrics
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
Radar sensor performance metrics (RSPMs) for the Acconeer radar system provides useful information on the performance of the system: sensor, RSS and reference integration. The list contains the RSPMs that are applicable to services that produce radar data. However, not all RSPMs are applicable to all radar services. The RSPMs is used in our `Radar Datasheet <https://developer.acconeer.com/download/a111-datasheet-pdf/>`__.


Radar loop gain
~~~~~~~~~~~~~~~

The SNR can be modelled as a function of a limited number of parameters: the RCS of the object (:math:`\sigma`), the distance to the object (:math:`R`), the reflectivity of the object (:math:`\gamma`), and a radar sensor dependent constant referred to as radar loop gain (:math:`C`). The SNR (in dB) is then given by

.. math::
    :label: eq_radar_eq

    \mathrm{SNR}_{dB}=10\log_{10}\frac{S}{N}=C_{dB}+\sigma_{dB}+\gamma_{dB}-k10\log_{10}R

:numref:`fig_rx_power_vs_dist` shows how the received energy drops with increasing :math:`R` for objects where the exponent :math:`k` is equal to 4, which applies for objects which are smaller than the area which is illuminated coherently by the radar. For objects that are larger than this area the :math:`k` is smaller than 4, with a lower limit of :math:`k = 2`  when the object is a large flat surface.

.. _fig_rx_power_vs_dist:
.. figure:: /_static/introduction/fig_rx_power_vs_dist.png
    :align: center

    Received signal power versus distance. Note: signal, S, is plotted in dB.


Depth resolution
~~~~~~~~~~~~~~~~

The depth resolution determines the minimum distance of two different objects in order to be distinguished from each other.


Distance resolution
~~~~~~~~~~~~~~~~~~~

The Acconeer radar systems are based on a time diluted measurement that splits up as a vector of energy in several time bins it is important to know the bin separation. This is the delay resolution of the system and in A111 radar sensor the target is ~3 ps on average, which corresponds to a distance resolution of ~0.5 mm between distance samples.


Half-power beamwidth
~~~~~~~~~~~~~~~~~~~~

The half-power beamwidth (HPBW) radiation pattern determines the angle between the half-power (-3 dB) points of the main lobe of the radiation pattern. The radiation pattern of the sensor depends on both the antenna-in-package design and the hardware integration of the sensor, such as surrounding components, ground plane size, and added di-electric lenses for directivity optimizations, valid for both vertical and horizontal plane.


Distance jitter
~~~~~~~~~~~~~~~

The distance jitter determines the timing accuracy and stability of the radar system between sweep updates. The jitter is estimated by calculating the standard deviation of the phase, for the same distance bin, over many IQ sweeps.


Distance linearity
~~~~~~~~~~~~~~~~~~

The distance linearity deterministic the deterministic error from the ideal delay transfer function. Linearity of the service data is estimated by measuring the phase change of the IQ data vs distance.


Update rate accuracy
~~~~~~~~~~~~~~~~~~~~

The update rate accuracy determines the accuracy of the time between sweep updates or similarly the accuracy of the update rate, typically important when the radar data is used for estimating velocity of an object.


Close-in range
~~~~~~~~~~~~~~

The close-in range determines the radar system limits on how close to the radar sensor objects can be measured.


Power consumption
~~~~~~~~~~~~~~~~~

The power consumption determines the radar sensor power usage for different configurations as service depends, the power save mode, the update rate, downsampling, sweep length, etc.


.. _sensor-intro-configuring:

Configuring the Acconeer sensor
-------------------------------

The Acconeer sensor is highly configurable and can operate in many different modes where parameters are tuned to optimize the sensor performance for specific use cases.

Signal averaging and gain
^^^^^^^^^^^^^^^^^^^^^^^^^

In addition to the Profile configuration parameter, two main configuration parameters are available in all Services to optimize the signal quality:

* Hardware Accelerated Average Samples (HWAAS) is related to the number of pulses averaged in the radar to produce one data point. A high number will increase the radar loop gain but each sweep will take longer to acquire and therefore limit the maximum update rate.

* The gain of the amplifiers in the sensor. Adjusting this parameter so the ADC isn't saturated and at the same time the signal is above the quantization noise is necessary. A gain figure of 0.5 is often a good start.


Sweep and update rate
^^^^^^^^^^^^^^^^^^^^^

A sweep is defined as a distance measurement range, starting at the distance *start range* and continues for *sweep length*. Hence, every sweep consists of one or several distance sampling points.

A number of sweeps :math:`N_s` are sampled after each other and the time between each sweep is :math:`T_s`, which is configurable. We usually refer to this as the *update rate* :math:`f_s=1/T_s`.

In addition, the sparse service introduces a concept of frames defined `here <https://docs.acconeer.com/en/latest/services/sparse.html>`__.


Repetition modes
^^^^^^^^^^^^^^^^

RSS supports two different *repetition modes*. They determine how and when data acquisition occurs. They are:

* **On demand**: The sensor produces data when requested by the application. Hence, the application is responsible for timing the data acquisition. This is the default mode, and may be used with all power save modes.

* **Streaming**: The sensor produces data at a fixed rate, given by a configurable accurate hardware timer. This mode is recommended if exact timing between updates is required.

Note, Exploration Tool is capable of setting the update rate also in *on demand* mode. Thus, the difference between the modes becomes subtle. This is why *on demand* and *streaming* are called *host driven* and *sensor driven* respectively in Exploration Tool.

.. _power-save-modes:

Power save modes
^^^^^^^^^^^^^^^^

The power save mode configuration sets what state the sensor waits in between measurements in an active service. There are five power save modes, see :numref:`tab_power_save_modes`.  The different states differentiate in current dissipation and response latency, where the most current consuming mode *Active* gives fastest response and the least current consuming mode *Off* gives the slowest response. The absolute response time and also maximum update rate is determined by several factors besides the power save mode configuration. These are profile, length, and hardware accelerated average samples. In addition, the host capabilities in terms of SPI communication speed and processing speed also impact on the absolute response time. Nonetheless, the relation between the power save modes are always kept such that *Active* is fastest and *Off* is slowest.

Another important aspect of the power save mode is when using the service in repetition mode Streaming. In streaming mode the service is also configured with an update rate at which the sensor produces new data. The update rate is maintained by the sensor itself using either internally generated clock or using the externally applied clock on XIN/XOUT pins. Besides the fact that power save mode *Active* gives the highest possible update rate, it also gives the best update rate accuracy. Likewise, the power save mode *Sleep* gives a lower possible update rate than *Active* and also a lower update rate accuracy. Bare in mind that also in streaming mode the maximum update rate is not only determined by the power save mode but also profile, length, and hardware accelerated average samples. Power save mode *Off* and *Hibernate* is not supported in streaming mode since the sensor is turned off between its measurements and thus cannot keep an update rate. In addition, the power save mode *Hibernate* is only supported when using Sparse service.

:numref:`tab_power_save_modes` concludes the power save mode configurations.

.. _tab_power_save_modes:
.. table:: Power save modes.
    :align: center
    :widths: auto

    ================== ==================== ============== =====================
    Power save mode    Current consumption  Response time  Update rate accuracy
    ================== ==================== ============== =====================
    Off                Lowest               Longest        Not applicable
    Hibernate          ...                  ...            Not applicable
    Sleep              ...                  ...            Worst
    Ready              ...                  ...            ...
    Active             Highest              Shortest       Best
    ================== ==================== ============== =====================

As part of the deactivation process of the service the sensor is disabled, which is the same state as power save mode *Off*.


Configuration summary
^^^^^^^^^^^^^^^^^^^^^

:numref:`tab_sensor_params` shows a list of important parameters that are available through our API and that can be used to optimize the performance for a specific use case, refer to product documentation and user guides for a complete list of all parameters and how to use them.

.. _tab_sensor_params:
.. table:: List of sensor parameters
    :align: center
    :widths: auto

    ================== ==============================================================================================
    Parameter          Comment
    ================== ==============================================================================================
    Profile            Selects between the pulse length profiles. Trade off between SNR and depth resolution.
    Start              Start of sweep [m].
    Length             Length of sweep, independently of Start range  [m].
    HWAAS              Amount of radar pulse averaging in the sensor.
    Receiver gain      Adjust to accommodate received signal level.
    Repetition mode    On demand or Streaming.
    Update rate        Desired rate at which sweeps are generated [Hz] (in repetition mode Streaming).
    Power save mode    Tradeoff between power consumption and rate and accuracy at which sweeps are generated.
    ================== ==============================================================================================


Summary
-------

Acconeer’s Pulsed coherent radar technology is unique as it combines high precision and low power consumption into a tiny package and for the first time enables radar in products where size, cost and power consumption matters. We are committed to making the technology available to everyone and we are working hard to make it easy for you to take your product to the market, whether you need pre-integrated hardware or new Detectors we will help you to get the product to your customers.
Sign up for our newsletter or check out our website and Github for updates on new cool features that we have released, we are constantly innovating, **“Explore the next sense!”**.


Disclaimer
----------

The information herein is believed to be correct as of the date issued. Acconeer AB (**“Acconeer”**) will not be responsible for damages of any nature resulting from the use or reliance upon the information contained herein. Acconeer makes no warranties, expressed or implied, of merchantability or fitness for a particular purpose or course of performance or usage of trade. Therefore, it is the user’s responsibility to thoroughly test the product in their particular application to determine its performance, efficacy and safety. Users should obtain the latest relevant information before placing orders.

Unless Acconeer has explicitly designated an individual Acconeer product as meeting the requirement of a particular industry standard, Acconeer is not responsible for any failure to meet such industry standard requirements.

Unless explicitly stated herein this document Acconeer has not performed any regulatory conformity test. It is the user’s responsibility to assure that necessary regulatory conditions are met and approvals have been obtained when using the product. Regardless of whether the product has passed any conformity test, this document does not constitute any regulatory approval of the user’s product or application using Acconeer’s product.

Nothing contained herein is to be considered as permission or a recommendation to infringe any patent or any other intellectual property right. No license, express or implied, to any intellectual property right is granted by Acconeer herein.

Acconeer reserves the right to at any time correct, change, amend, enhance, modify, and improve this document and/or Acconeer products without notice.

This document supersedes and replaces all information supplied prior to the publication hereof.

Document history
----------------

.. table::
    :align: center
    :widths: auto

    =========== ====================================== ======= ============
    Author      Comments                               Version Date
    =========== ====================================== ======= ============
    Acconeer AB Update demo images.                    2.11    2022-05-11
    Acconeer AB Minor update.                          2.10    2022-03-10
    Acconeer AB Update link to HAL-integration guide.  2.9     2022-03-07
    Acconeer AB Updated max range in tables.           2.8     2020-12-14
    Acconeer AB Product sw offer figure updated.       2.7     2020-09-29
    Acconeer AB Product offer figure updated.          2.6     2020-09-28
    Acconeer AB Updated with new distance detector.    2.5     2020-08-14
    Acconeer AB Minor fixes.                           2.4     2020-05-27
    Acconeer AB Minor fixes.                           2.3     2020-03-13
    Acconeer AB Minor fixes.                           2.2     2020-02-27
    Acconeer AB Added power save mode Hibernate.       2.1     2020-01-17
    Acconeer AB Initial version for API 2.0.           2.0     2019-12-01
    =========== ====================================== ======= ============
