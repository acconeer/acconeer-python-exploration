.. _handbook-a111-configuring:

Configuration overview
======================

The Acconeer A111 is highly configurable and can operate in many different modes where parameters are tuned to optimize the sensor performance for specific use cases.

Signal averaging and gain
-------------------------

In addition to the Profile configuration parameter, two main configuration parameters are available in all Services to optimize the signal quality:

* Hardware Accelerated Average Samples (HWAAS) is related to the number of pulses averaged in the radar to produce one data point. A high number will increase the radar loop gain but each sweep will take longer to acquire and therefore limit the maximum update rate.

* The gain of the amplifiers in the sensor. Adjusting this parameter so the ADC isn't saturated and at the same time the signal is above the quantization noise is necessary. A gain figure of 0.5 is often a good start.


Sweep and update rate
---------------------

A sweep is defined as a distance measurement range, starting at the distance *start range* and continues for *sweep length*. Hence, every sweep consists of one or several distance sampling points.

A number of sweeps :math:`N_s` are sampled after each other and the time between each sweep is :math:`T_s`, which is configurable. We usually refer to this as the *update rate* :math:`f_s=1/T_s`.

In addition, the sparse service introduces a concept of frames defined `here <https://docs.acconeer.com/en/latest/services/sparse.html>`__.


Repetition modes
----------------

RSS supports two different *repetition modes*. They determine how and when data acquisition occurs. They are:

* **On demand**: The sensor produces data when requested by the application. Hence, the application is responsible for timing the data acquisition. This is the default mode, and may be used with all power save modes.

* **Streaming**: The sensor produces data at a fixed rate, given by a configurable accurate hardware timer. This mode is recommended if exact timing between updates is required.

Note, Exploration Tool is capable of setting the update rate also in *on demand* mode. Thus, the difference between the modes becomes subtle. This is why *on demand* and *streaming* are called *host driven* and *sensor driven* respectively in Exploration Tool.

.. _power-save-modes:

Power save modes
----------------

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
---------------------

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
