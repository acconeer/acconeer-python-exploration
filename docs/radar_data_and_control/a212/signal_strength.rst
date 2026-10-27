.. _rdac-a212-signal-strength:

.. include:: ../common/signal_strength.rst

HWAAS scaling
^^^^^^^^^^^^^

For A212, HWAAS is controlled per subsweep by three parameters:

- **hwaas_max** (default 50, range 1 to 2047): HWAAS at the farthest distance point.
- **hwaas_min** (default 1, range 1 to 2047): floor value when distance scaling is active.
- **hwaas_exponent** (default 0, range 0 to 4): scaling power applied to the distance ratio.

The effective HWAAS at distance point :math:`n` is

.. math::

   \text{HWAAS}(n) = \max\!\left(\text{hwaas\_min},\;
   \text{hwaas\_max} \times \left(\frac{d_n}{d_\text{end}}\right)^{e}\right)

where :math:`d_n` is the distance at point :math:`n`, :math:`d_\text{end}` is the distance at
the last point in the subsweep, and :math:`e` is ``hwaas_exponent``.
Higher values of :math:`e` allocate more averages to far points to compensate for signal energy
loss with distance. The goal of this dynamic averaging is to maintain a constant SNR through
the measurement range while minimizing power consumption. Commonly used values are ``0``
(constant HWAAS throughout the sweep), ``2`` (appropriate for large planar targets such as flat
surfaces), and ``4`` (appropriate for targets with a general three-dimensional shape).

.. seealso::

   :py:class:`~acconeer.exptool.a2.SubsweepConfig` for the full list of per-subsweep
   parameters including ``hwaas_max``, ``hwaas_min``, and ``hwaas_exponent``.
