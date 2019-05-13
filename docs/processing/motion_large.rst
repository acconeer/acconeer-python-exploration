Motion large
============

``motion_large.py`` is an example of a simple motion detection algorithm based on changes in **power** in the received signal over time, based on the :ref:`envelope-service` service. Large motions or changes in front of the sensor are required to trigger the detector. Further, static objects are ignored but could reduce the sensitivity due to increased received average power. A typical use case is to detect a person walking up to or away from the sensor's coverage region. It will not detect small motions as breathing or pulse from a person standing in front of the sensor, which is the case for the ``presence_detection_iq.py`` utilizing the phase coherency of the sensor.

=============== ===================================
Abbreviations   Description
:math:`f_s`     Sweep frequency [Hz]
:math:`f_b`     Burst frequency [Hz]
:math:`N_D`     Number delay points per sweep
:math:`N_S`     Number of sweeps per burst
:math:`P`       Average received power per burst
:math:`d`       Delay sample index
:math:`s`       Sweep index
:math:`b`       Burst index
:math:`\beta_s` Slow filter or smoothing factor
:math:`\beta_f` Fast filter or smoothing factor
:math:`t_f`     Slow filter length [s]
:math:`t_s`     Fast filter length [s]
:math:`\lambda` Detector threshold
=============== ===================================

At a rate of :math:`f_b` a burst of :math:`N_S` sweeps is collected
at a sweep rate of :math:`f_s`. Each sweep consists of :math:`N_D`, delay samples. Here, the data samples is represented by

.. math:: x[d,s,b] \tag{1}

where :math:`d` is the delay sample index :math:`s` is the sweep index and :math:`b` is the burst index. We take the average received power over delay and sweeps indecies for each burst as

.. math:: P[b]= \frac{1}{N_D} \sum_{d=0}^{N_D-1} \sum_{s=0}^{N_S-1} |x[d,s,b]|^2 \tag{2}

There are different possibilities to build a detector on top of changes in the received burst power metric :math:`P[b]`. Here :math:`P[b]` is filtered by an exponential smoothing filter - one with a slow and one a fast filter factor as

.. math::
    P_s[b]=\begin{cases}
        0, &  b=0 \\
        (1-\beta_s) P[b] + \beta_s P_s[b-1], & b > 0
    \end{cases}


.. math::
    P_f[b]=\begin{cases}
        0, &  b=0 \\
        (1-\beta_f) P[b] + \beta_f P_f[b-1], & b > 0
    \end{cases}

where the exponentional smoothing factors are defined as

.. math:: \beta_s=\exp(-\frac{2}{f_b t_s}) \tag{3}

.. math:: \beta_f=\exp(-\frac{2}{f_b t_f}) \tag{4}

We suggested that these two :math:`P_s[b]` and :math:`P_f[b]` are treated separately and detect changes between the slow and the fast low-pass filtered versions, i.e., motion is detected detected if

.. math:: M[b]=\frac{|P_{f}[b]-P_{s}[b-1]|}{P_{s}[b-1]} > \lambda \tag{5}

where :math:`\lambda` is a detection threshold for :math:`b>0`.

Note: In the implementation we plot :math:`M[b]` and have added an exponential smoothing over the :math:`b`, in order to get a smoother behaviour. Further, we receive bursts continously, :math:`f_b=f_s N_s`, where for a power limited system the burst frequency could be reduced.
