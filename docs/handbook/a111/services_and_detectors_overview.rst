Services and detectors overview
===============================

The RSS provides output at two different levels, Service and Detector. The Service output is pre-processed sensor data as a function of distance. Detectors are built with this Service data as the input and the output is a result, in the form of e.g. distance, presence, angle etc. Services and Detectors currently available are listed in :numref:`fig_detectors_services`.

.. _fig_detectors_services:
.. figure:: /_static/introduction/fig_detectors_services.png
    :align: center
    :width: 70%

    Available Detectors and Services.

Each Detector is built on top of a Service, i.e. you have the possibility to use our out-of-the-box Detectors or develop your own. To select the Service or Detector applicable for your use case it is recommended to use the Exploration Tool to observe the different outputs and understand what they represent. Each Service and Detector also comes with its own user guide, which can be found at `acconeer.com <https://acconeer.com>`__.

At `developer.acconeer.com <https://developer.acconeer.com>`__, we have several movies showing demos where the Acconeer sensor is used in different use cases. Together with the demo movies, corresponding reference applications are available in our different SDKs at Acconeer developer site. These reference applications are written in C code and use our Services and Detectors, check them out to get inspiration on how to build your product with the Acconeer sensor.
