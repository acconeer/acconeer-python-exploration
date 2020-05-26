.. _phase-tracking:

Phase tracking
==============

An example of a relative movements tracking algorithm using phase information.

.. image:: /_static/processing/phase_tracking.png

``phase_tracking.py`` is an example of how single objects can be tracked using only the phase information of the IQ service. The point in which the phase is tracked is shown in dashed orange. It is the "center of mass" of the low pass filtered IQ envelope, shown in the upper left plot. The unfiltered phase information is shown below in the lower left plot.

To illustrate how the IQ data behaves, the point in which the phase is tracked is also shown in the polar plot. As you move an object towards and away from the radar, you will see the point rotating. It is this rotation that is translated into a relative movement, which is shown in the remaining two plots. One phase rotation translates to a movement of half a wavelength, which is roughly 2.5mm.

As we get a phase jitter of only a few degrees, this translates to a movement jitter of a couple of hundredths of a millimeter. For comparison, a typical sheet of paper is roughly a tenth of a millimeter thick.
