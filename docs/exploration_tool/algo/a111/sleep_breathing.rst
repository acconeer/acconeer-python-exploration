.. _sleep-breathing:

Sleep breathing
===============

An example of a "sleep breathing" detection algorithm assuming that the person is still (as when in sleep) where only the motion from breathing is to be detected.

The algorithm can be divided into three parts; (i) extracting the motion of the breathing person, (ii) performing a Fourier transform of the position over time to search for oscillations, and finally (iii) detecting the respiration rate in the spectra.

===================== ===================================================
Abbreviation          Description
:math:`f_s`           Sweep frequency [Hz]
:math:`s`             Sweep index
:math:`d`             Range index
:math:`x[s,d]`        Data from the IQ Service
:math:`\tau_{iq}`     Fast filter length [s]
:math:`f_{low}`       Lowest frequency of interest [Hz], typically 0.1
:math:`f_{high}`      Highest frequency of interest [Hz], typically 1
:math:`D`             Range downsampling factor
:math:`M`             Sweep (or time) downsampling factor
:math:`\phi[s]`       The phase of sweep s [rad]
:math:`T`             Fourier transform time window [s]
:math:`\lambda_p`     Peak to noise detection threshold
:math:`\lambda_{1/2}` Peak to signal at half frequency threshold
===================== ===================================================

Obtaining motion signal
-----------------------

The radar is configured to collect IQ radar sweeps with a range covering the chest of a breathing person. For example, the radar sensor could be mounted in a device on the night stand next to the bed where a person is sleeping. The radar should be aimed at the chest of the person and scanning the range of approx. 30 cm to 90 cm. The data samples from the IQ API are represented by

.. math:: x[s,d]

where, :math:`d`, is the range index, :math:`s`, is the sweep index. Typically, the spacing between samples in range is approx. 0.5 mm and the sweep rate, :math:`f_s`, is in the 100 Hz range, depending on configuration.

Since neighbouring samples in range are strongly correlated, the IQ samples can be downsampled in range to :math:`x_D[s,d]`, where

.. math:: x_D[s,d] = x[s,d D + D/2],

and :math:`D` is a range downsampling factor, typically close to 100. The purpose of the downsampling is simply to reduce the amount of data for further processing.

The next step is a simple noise reducing low-pass filter in the time (or sweep) dimension,

.. math:: \bar{x}[s,d] = \alpha_{iq} \bar{x}[s-1,d] + (1 - \alpha_{iq}) x_D[s,d]

where :math:`\alpha_{iq} = \exp \left\lbrace -2 / (\tau_{iq} f_s ) \right\rbrace` is the filter coefficient.

The last step in this part of the algorithm is the unwrapping of the phase of the IQ samples. Here, it is performed via

.. math:: \phi[s] = \alpha_\phi \phi[s-1] + \angle \left\lbrace \sum_{d=0} ^{N_d -1} \bar{x}_D[s,d] \bar{x}^*_D[s-1,d] \right\rbrace,

where :math:`\alpha_\phi = \exp \left\lbrace -2 f_{low} / f_s  \right\rbrace` is a high-pass filter factor to remove the any build-up of phase over time, :math:`\angle \lbrace z \rbrace` denotes the complex phase of :math:`z`, and :math:`z^*` is the complex conjugate of :math:`z`. :math:`N_d` is the number of samples in each sweep after range downsampling. With the approach described above, a single phase, representing the whole sweep, is obtained for each sweep.

Searching for oscillations
---------------------------

The motion of the chest of the sleeping person can be seen in as oscillations in the phase signal, :math:`\phi[n]`, from the previous section. A variety of approaches can be employed to find the respiration rate of the person, such as searching for zero-crossings or inspecting peaks in the autocorrelation function. Here, we instead search for peaks in the Fourier transform.

Since human breathing most often occur in the 0.1-1 Hz frequency range, the typical radar sweep frequency, :math:`f_s`, of approx 100 Hz is unnecessary high for spectral estimation in the frequency range of interest. The sweep frequency should however be lowered with care, since it also limits the maximum radial speed allowed for correct phase unwrapping.

Before downsampling in time the phase needs to be low-pass filtered. We apply a second order Butterworth low-pass filter with cut-off-frequency of :math:`f_{high}`. The low-pass filtered phase :math:`\bar{\phi}[s]` can then be downsampled in time according to

.. math:: \bar{\phi}_M[s] = \bar{\phi}[M s]

where :math:`M` is chosen so that the sampling rate of the downsampled phase, :math:`\phi_M[s]`, is approximately 10 Hz. This corresponds to a Nyquist frequency of 5 Hz, well above the highest frequency of interest, :math:`f_{high}`, of approx 1 Hz.

A Discrete Fourier Transform (DFT) is performed on the last :math:`T` seconds of low-pass filtered downsampled phase. The magnitude square of each frequency component :math:`P[i]` corresponding to the spectral power in the frequency bin :math:`f[i]`.

The spacing of frequency bins are set by the length in time of the data set, so to increase the frequency resolution the frequency of the peak is interpolated assuming a Gaussian peak shape,

.. math:: f_p = f[i_p] + \frac{\Delta f}{2} \frac{\log P[i_p +1] -\log P[i_p -1] }{2 \log P[i_p ] - \log P[i_p +1] - \log P[i_p -1]},

where :math:`i_p` is the index of the spectral bin with the highest power, :math:`i_p = \mathrm{argmax}_i \, P[i]`, and :math:`\Delta f` is the frequency spacings of the bins.


Breathing detection
-------------------

The final step in the algorithm is to see if the peak in the spectra is high compared to the spectral noise. The noise level is estimated as the average power level in the half of the frequency bins with the lowest power. If the peak is higher than the threshold, :math:`\lambda_p`, times the noise level, breathing is detected.

Since chest motion during breathing is highly non-sinusodial, many harmonics of the breathing frequency are often seen in the spectra. To avoid detecting the first harmonic, instead of the fundamental, a final check is carried out to inspect the spectral power at half the frequency of the highest peak in the spectra. This spectral power is compared to a second threshold, :math:`\lambda_{1/2}`, so that half the frequency is chosen if

.. math:: P[i_p/2]/P[i_p] > \lambda_{1/2},

and :math:`i_p/2` corresponds to a valid frequency.

These two thresholds has been set after analyzing detector performance on data sets collected on a few adults and children. However, depending on the mechanical integration of the sensor and the trade-off between missed detections and false detection, these thresholds might need tuning to achieve the optimal performance for each design.

Configuration parameters
------------------------

.. autoclass:: acconeer.exptool.a111.algo.sleep_breathing._processor.ProcessingConfiguration
   :members:
