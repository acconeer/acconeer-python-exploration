.. _handbook-a121-fom:

Figure of Merits
================

This page describes and defines Figure of Merits.

Radar loop gain (RLG)
---------------------

Signal-to-noise ratio (SNR)
^^^^^^^^^^^^^^^^^^^^^^^^^^^

Let
:math:`x(f, s, d)`
be a (complex) point
at a distance :math:`d` where the number of distances is :math:`N_d`,
in a sweep :math:`s` where the number of sweeps per frame is :math:`N_s`,
in a frame :math:`f` where the number of frames collected is :math:`N_f`.
Further, let
:math:`x_S`
be data collected with a known reflector in the range.
This is used for the signal part of the SNR.
Correspondingly, let
:math:`x_N`
be the data collected with the transmitter (TX) disabled.
This is used for the noise part of the SNR.

The frame/sweep distinction is not necessary for the SNR definition. The frames can simply be concatenated:
:math:`x(f, s, d) \rightarrow y(s', d)`
where :math:`N_{s'} = N_f \cdot N_s`.

Let the signal power
:math:`S = \max_{d}(\text{mean}_{s'}(|y_S|^2))`.

Let the noise power
:math:`N = \text{mean}_{s', d}(|y_N|^2)`.
This is assuming :math:`E(y_N) = 0` and :math:`V(y_N)` is constant over :math:`(s', d)`,
where :math:`E` is the expectation value and :math:`V` is the variance.

Finally, let
:math:`\text{SNR} = S/N`.
The SNR in decibel
:math:`\text{SNR}_\text{dB} = 10 \cdot \log_{10}(S/N)`.

.. note::

    The expectation value of the SNR is **not** affected by the
    total number of sweeps :math:`N_{s'}`
    nor the number of distances :math:`N_d` measured.

Radar loop gain (RLG)
^^^^^^^^^^^^^^^^^^^^^

The radar loop gain is given by:
:math:`\text{RLG}_\text{dB} = \text{SNR}_\text{dB} - \text{RCS}_\text{dB} + 40 \log_{10}(d)`
where
SNR is the signal-to-noise ratio,
RLG is the radar loop gain,
RCS is the radar cross-section,
and
:math:`d` is the distance to the target with the given RCS.

.. note::

    Of the configuration parameters, RLG only depends on :ref:`profile <handbook-a121-profiles>` and HWAAS.
    Excluding the configuration, RLG may vary on other factors such as per unit variations, temperature, and the hardware integration.

.. _handbook-a121-fom-base-rlg:

Base RLG
^^^^^^^^

*Base* RLG is the RLG (equivalent) for HWAAS = 1.

SNR and therefore also RLG scales linearly with HWAAS, meaning a 3dB increase for every doubling of HWAAS.

Radar loop gain per time (RLG/t)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Measurement time is not accounted for in the RLG metrics.
To account for it, we define the *radar loop gain per time (RLG/t)*:

.. math::
    :label:

    \text{RLG/t}_\text{dB}
    =
    (\text{RLG}_\text{dB}\ |\ \text{HWAAS} = 1)
    - 10 \log_{10}(\tau_\text{sample})

where
:math:`(\text{RLG}_\text{dB}\ |\ \text{HWAAS} = 1)` is the :ref:`base RLG<handbook-a121-fom-base-rlg>`,
and
:math:`\tau_\text{sample}` is the :ref:`sample duration<handbook-a121-timing-sample-dur>`.

.. note::

    RLG/t also depends on :class:`PRF <acconeer.exptool.a121.PRF>`.
    Higher PRF:s have higher RLG/t,
    which are generally more efficient.
