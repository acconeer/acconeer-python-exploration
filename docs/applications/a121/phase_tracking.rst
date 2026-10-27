Phase Tracking
==============

Phase Tracking is an example of how a single object can be tracked using only the phase information of the Sparse IQ service.

The Phase Tracking :term:`Example Application` algorithm calculates the change in phase between consecutive frames and converts it to the corresponding increment in distance, using the known wavelength of the transmitted pulse.
See :ref:`rdac-a121-interpreting-radar-data` for more information on the conversion between phase change and distance.
The change in distance is accumulated over multiple frames, resulting in a highly accurate estimate of the movement, relative the starting points.

The figure below depicts the GUI.
The upper graph shows the envelope of the signal and the middle graph the phase.
The lower graph shows the estimated distance, where in this case, an object is being moved in a sinusoidal motion with an amplitude of half a millimeter.
The green vertical line shows where the phase is currently being tracked, which is determined by the location of the highest envelope peak.
Note, as this example use a simple peak tracking strategy (highest peak), it might not perform as well in the case of multiple objects.

.. image:: /images/processing/a121_phase_tracking.png
    :align: center

Verification
------------

This application has not been verified with a systematic testing procedure, but works quite well
for the basic use case (see :term:`Example Application`).

Exploration Tool Python API
---------------------------

Example Application Configuration
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
.. autoclass:: acconeer.exptool.a121.algo.phase_tracking.ProcessorConfig
   :members:
