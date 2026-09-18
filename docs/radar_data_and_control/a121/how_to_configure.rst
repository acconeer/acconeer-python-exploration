.. _rdac-a121-how-to-configure:

.. include:: ../common/how_to_configure/how_to_configure.rst

Idle-related parameters and control
-----------------------------------

Five idling states are available to optimize the power consumption of the sensor.
Each state progressively consumes less power, but also increase the wake-up time.

The three most shallow idling states are set through the sensor configuration:

- **READY** - Required state when measuring.
- **SLEEP**
- **DEEP_SLEEP**

The two deepest idling states are set through API calls from the host to the sensor:

- **HIBERNATE**
- **OFF** - Deepest state and longest wake-up.

The first three states are set as a part of the sensor configuration through the parameters **inter sweep idle state** and **inter frame idle state**.
Note, the inter frame idle state must be set equal or lower than the inter sweep idle state.

After determining the range and rate related parameters, set the idle states to the deepest possible state, while still being able to maintain the desired sweep and frame rate.
If the sweep rate is not set, the sensor will collect sweeps at the highest possible rate.
To maximize the sweep rate, set the inter sweep idle state to READY.

The time it takes to transition from SLEEP/DEEP SLEEP to READY impacts the maximum achievable sweep and frame rate.
More info regarding idle state transition times can be found :ref:`here<rdac-a121-timing>`.

The wake-up time from HIBERNATE and OFF are integration dependent (SPI communication speed and crystal startup/stabilization time) and has to be evaluated for each case.
As a rule of thumb, HIBERNATE should be used when the inter frame duration is longer than 15 ms and OFF when the duration is longer than 2 s.
These states only affects the inter frame power consumption.
The inter sweep idle state needs to be set through the sensor configuration.

Note, HIBERNATE and OFF are only available in the C SDK and not through the Python API.

Other parameters
----------------

- Leave **receiver gain** at the default value and reduce if saturation occurs.
- Leave **enable TX** set (default).
