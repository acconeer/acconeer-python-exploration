**************************
Sparse IQ Figure of Merits
**************************

The definitions below apply to any of Acconeer's products implementing the Sparse IQ service.

.. _fom-rlg:

Radar Loop Gain (RLG)
=====================

*Radar Loop Gain* is given the formula (rearranged from :term:`signal-to-noise ratio<SNR>` definition):

.. math::
   :label:

   \text{RLG}_{dB} = \text{SNR}_{dB} - \text{RCS}_{dB} + 40 \log_{10}(d),

where
RLG is the radar loop gain,
SNR is the :term:`signal-to-noise ratio<SNR>`,
RCS is the :term:`radar cross-section<Radar cross section>`,
and
:math:`d` is the distance to the target with the given RCS.

.. _fom-base-rlg:

Base Radar Loop Gain (Base RLG)
===============================

*Base* RLG is the RLG (equivalent) for HWAAS = 1.

RLG (and SNR) scales linearly with HWAAS, meaning a 3dB increase for every doubling of HWAAS.

Radar Loop Gain per time (RLG/t)
================================

Measurement time is not accounted for in the *RLG* and *Base RLG* metrics.
To account for it, we define the *Radar Loop Gain per time (RLG/t)* as

.. math::
    :label:

    \text{RLG/t}_{dB}
    =
    (\text{RLG}_{dB}\ |\ \text{HWAAS} = 1)
    - 10 \log_{10}(\tau_\text{sample})

where
:math:`(\text{RLG}_{dB}\ |\ \text{HWAAS} = 1)` is the :ref:`base RLG<fom-base-rlg>`,
and
:math:`\tau_\text{sample}` is the sample duration.
