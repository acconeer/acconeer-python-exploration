.. _handbook-a121-profiles:

Profiles
========

.. _fig_a121_profiles:
.. figure:: /_static/handbook/a121/profiles.png
   :align: center
   :width: 80%

   Mocked data for different profiles with three objects in the range.

One of the most important configuration parameters is the *profile*, which mainly sets the duration and shape of emitted pulses.
Other internal parameters are set up accordingly to maximize the efficiency of the system, which affects the measurement time of a point.
Higher numbered profiles use longer pulses, which generally:

- Increases SNR due to increased emitted energy.
- Decreases measurement time for a given configuration.
- Gives the possibility to sample more sparsely, decreasing measurement time and memory usage.

On the flip side, longer pulses also:

- Decreases precision due to lower bandwidth.
- Increases TX to RX leakage length, i.e., how far into the range the transmitted pulse is visible.
  The closest usable range due to this is referred to as the "close-in distance".
- Decreases distance resolution (ability to resolve objects close to each other).

:numref:`fig_a121_profiles` illustrates the difference between two profiles.
Profile 2 correctly resolves three objects where 3 cannot.
However, profile 3 gives more energy for the same object.
