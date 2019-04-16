Presence detection (IQ)
=======================

An example of a presence/motion detection algorithm based on changes in the **IQ** received signal over time. Small changes/motions in front of the sensor are enough to trigger the detector. Further, static objects are ignored. A typical use case is to detect a person based on the small motions origin from the breathing and pulse.

The IQ service captures both amplitude and phase of the reflected radar pulse, and will therefore easily detect changes down to fractions of a wavelength. The Acconeer radar uses a 60 GHz radar pulse, where one wavelength -- in radar distance -- corresponds to 2.5 mm change of the reflector. A reflector position change of e.g. 0.1 mm will therefore result in a
:math:`360^{\circ}\frac{0.1}{2.5}\approx 14^{\circ}` phase change.

The presence detection processing example uses the IQ service and basically high-pass filters the (complex) IQ output in time -- individually per depth bin. When the power of the high-pass output from all bins is high enough, presence is detected.
