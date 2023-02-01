.. _handbook-a121-fom:

Figure of Merits
================

This page describes and defines Figure of Merits (FoM).

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

Radial resolution
-----------------

Radial resolution is described by the `full width at half maximum (FWHM) <https://en.wikipedia.org/wiki/Full_width_at_half_maximum>`_ envelope power.

Let
:math:`x(f, s, d)`
be a (complex) point
at a radial distance :math:`d` where the number of distances is :math:`N_d`,
in a sweep :math:`s` where the number of sweeps per frame is :math:`N_s`,
in a frame :math:`f` where the number of frames collected is :math:`N_f`.

Then, let the (average) envelope power

.. math::
    :label:

    y(d) = |\text{mean}_{f,s}(x)|^2

The FWHM of :math:`y` is what describes the radial resolution.

Distance
--------

Preliminaries
^^^^^^^^^^^^^

Let :math:`d_{est}(f, d)` be the estimated distance to a target located at distance :math:`d`,
formed by processing frame :math:`f` in accordance with the steps outline in the
:doc:`distance detector documentation</exploration_tool/algo/a121/distance_detection>`.
:math:`f` is a single frame in a set of frames of size :math:`N_f`.

Next, let :math:`e(f, d)=d_{est}(f, d) - d` be the estimation error of a single frame/measurement.

Lastly, form the mean error by averaging over the frames, :math:`\overline{e}(d)=\text{mean}_{f}(e(f,d))`.

:math:`\overline{e}(d)` describes the average error for a single sensor.
The metrics calculated in the following sections are based on data from a set of sensors.
To indicate what sensor the mean error is associated with, the subscript :math:`s` is added,
:math:`\overline{e}(d,s)`.

Accuracy
^^^^^^^^

The distance estimation accuracy is characterized through the following two sets of metrics:

- Mean error(:math:`\mu`) and standard deviation(:math:`\sigma`).
- Mean absolute error(:math:`\text{MAE}`).

Mean and standard deviation
~~~~~~~~~~~~~~~~~~~~~~~~~~~

The mean error for a set of sensors is given by :math:`\mu=\text{mean}_{d,s}(\overline{e}(d,s))`.

The standard deviation for a set of sensors is given by :math:`\sigma=\text{std}_{d,s}(\overline{e}(d,s))`.

Mean absolute error
~~~~~~~~~~~~~~~~~~~

The mean absolute error for a set of sensor is given by :math:`\text{MAE}=mean_{d,s}(|\overline{e}(d,s)|)`.

Linearity
^^^^^^^^^

Linearity refers to the variation in the distance estimate error as a function of the distance to the target.

The distance linearity is characterized through the mean of the standard deviation of the estimation error
over a number of distances, :math:`\sigma=\text{mean}_{s}(\text{std}_{d}(\overline{e}(d,s)))`.

The distance linearity is evaluated over two sets of distances:

- Micro: A number of distances within a few wavelengths.
- Macro: A number of distances over many wavelengths.

Temperature sensing
-------------------

The accuracy of the built-in temperature sensor is described by the *relative deviation*:

.. math::
    :label:

    k = \left| \frac{\hat{x} - x}{x} \right|

where :math:`x` is the actual temperature change and :math:`\hat{x}` is the measured temperature change.

The evaluated temperature span is typically the range from -40°C to 105°C.

.. note::

    The built-in temperature sensor is not designed for *absolute* measurements and should therefore not be used for that.
    For this reason, the absolute accuracy is not described as a FoM.
