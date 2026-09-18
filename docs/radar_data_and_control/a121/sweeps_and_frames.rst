.. _rdac-a121-sweeps-and-frames:

.. include:: ../common/sweeps_and_frames.rst

Limitations
-----------

As with the number of points :math:`N_d`, the only limitation on the number of sweeps per frame :math:`N_s` itself is related to the available buffer size of 4095 complex numbers.
The buffer usage is the number of points :math:`N_d` times the number of sweeps per frame :math:`N_s`.
In short, :math:`N_d \cdot N_s \leq 4095`.
