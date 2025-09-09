.. _integration-a121-electrical:

======================
Electrical integration
======================

The A111 and A121 sensor contains the mmWave front-end, digital control logic, digitization of received signal and memory, all in one package.
To integrate it in your application a 24 MHz crystal, a power supply, and a host processor are required, as illustrated in :numref:`fig_host_platform`.

.. _fig_host_platform:
.. figure:: /_static/introduction/fig_host_platform.png
    :align: center
    :width: 80%

    Illustration of integration into host platform, the A121 is marked with the Acconeer logo.


A121 Power
==========

The A121 radar sensor requires a 1.8 V input to the RX, TX, and VDIG power domains. The A121 VIO power domain can be powered by either 1.8 V or 3.3 V. To avoid stressing the A121 and to optimize the current consumption, the VIO on A121 should be equal to the I/O voltage on the host MCU that controls it. The A121 current consumption when the ENABLE pin is low is < 1 :math:`\mathrm{\mu A}` and there is thus no need for a power switch.

If the power to the A121 is switched off in between radar sweeps it is important that the control signals and Serial Peripheral Interface (SPI) interface are pulled low during this time, otherwise reverse leakage will occur via the Electrostatic Discharge (ESD) diodes in the A121.

.. _integration-a121-electrical-power-reg:

Choosing a 1.8 V power regulator for A121
=========================================

When the A121 radar sensor transfer from the *SLEEP* state to the *MEASURE* state, there is an abrupt change in current consumption from ~3 mA to ~75 mA on the 1.8 V power domain. The power regulator supplying the A121 must have a load transient response capable of handling this change in current without the output voltage dropping below the minimum operating supply voltage of A121. For details regarding the power consumption of A121, refer to the `A121 Datasheet <a121_datasheet_>`_.

SPI interface
=============
To ensure good signal integrity for the SPI bus, it is recommended to keep the SPI traces as short as possible with an adjacent ground plane. Place a ground via close to each signal via when changing layers to maintain a constant trace impedance. Impedance matching of the SPI bus is usually not needed as the trace lengths are electrically short for low drive strength configurations.

Hardware schematics design checklist
====================================

1. Does the selected crystal fulfill the load conditions according to the `A121 Datasheet <a121_datasheet_>`_?
2. Have you connected all ground balls on the package?
3. Is the ground plane size based on :numref:`fig_gain_vs_groundplanesize`.
4. Are the decoupling capacitors placed according to the guidelines under section :ref:`integration-a121-EM_PCB_component_placement` in the next chapter?
5. Have you chosen your power regulator based on the information under section :ref:`integration-a121-electrical-power-reg`?
6. Is the power supply and SPI interface routed with an adjacent ground plane?
7. Have you placed nearby ground vias to your signal and power supply vias?

.. _fig_gain_vs_groundplanesize:
.. figure:: /_static/handbook/a121/in-depth_topics/integration/A121_groundplane_size_simulation_with_sensor.png
    :align: center
    :width: 95%

    Simulated relative radar loop gain as function of ground plane side length (x). Ground plane is a solid square ground plane without routing.

For more information, see:

* :octicon:`download` `A111 Datasheet <a111_datasheet_>`_
* :octicon:`download` `A121 Datasheet <a121_datasheet_>`_
* :octicon:`download` `Hardware integration guideline <a121_hw_integration_guideline_>`_, in section *Electrical integration*

.. _a111_datasheet: https://developer.acconeer.com/download/a111-datasheet
.. _a121_datasheet: https://developer.acconeer.com/download/A121-datasheet
.. _a121_hw_integration_guideline: https://developer.acconeer.com/download/Hardware-integration-guideline
