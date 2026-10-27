.. _integration-a212-electrical:

A212 Electrical integration
===========================

The A212 is a 60 GHz, multi-antenna radar system delivered as a
one package solution with an integrated MCU, RF front-end and antennas (3TX, 4RX).
To integrate it in your application, an external 26 MHz crystal, decoupling capacitors and power
supply are required.

 Some applications can run directly on the A212’s internal MCU, i.e. no external host is needed. For
 these cases an external NVM is required to boot the A212.

In production test the NVM can be flashed via the SPI (fastest), UART (slower) or the TCKC/TMSC
pins (slowest).

For applications that require an external MCU host, the NVM is
optional since the sensor can boot from the external MCU.
See :ref:`Figure A: NVM integration <A212_NVM>` and :ref:`Figure B: MCU integration <A212_MCU>` for example integrations.


.. grid:: 2

   .. grid-item::

      .. _A212_NVM:

      .. thumbnail:: /images/hw_images/A212_NVM_sch.svg
         :title: Figure A: A212 NVM integration
         :show_caption: True
         :group: a212-schematics

   .. grid-item::

      .. _A212_MCU:

      .. thumbnail:: /images/hw_images/A212_MCU.svg
         :title: Figure B: A212 MCU integration
         :show_caption: True
         :group: a212-schematics





Power
-----
A regulator is needed to provide 1.8V and IO_VDD to the sensor. IO_VDD supports both 3.3 V and 1.8 V.
The total current consumption per sensor state is specified in the
table :numref:`a212-power-consumption` (T\ :sub:`op` = 25°C, nominal supplies):

.. list-table:: Total current consumption per sensor state
   :name: a212-power-consumption
   :header-rows: 1
   :widths: 20 40 10 10 40

   * - Symbol
     - Parameter
     - Typ
     - Unit
     - Condition
   * - I\ :sub:`sleep-ultra`
     - Current consumption, SLEEP-ULTRA-DEEP state
     - 40
     - µA
     -
   * - I\ :sub:`sleep-deep`
     - Current consumption, SLEEP-DEEP state
     - 46
     - µA
     -
   * - I\ :sub:`sleep-shallow`
     - Current consumption, SLEEP-SHALLOW state
     - 0.28
     - mA
     -
   * - I\ :sub:`idle`
     - Current consumption, IDLE state
     - 1.1
     - mA
     -
   * - I\ :sub:`processing`
     - Current consumption, PROCESSING state
     - 33
     - mA
     -
   * - I\ :sub:`measure`
     - Current consumption, MEASURE state
     - 174
     - mA
     - Profile 1, 2, 3, 5; PRF = 27.7 MHz
   * - I\ :sub:`measure-p6`
     - Current consumption, MEASURE state
     - 182
     - mA
     - Profile 6; PRF = 27.7 MHz
   * - I\ :sub:`full`
     - Current consumption, FULL state
     - 192
     - mA
     - Profile 1, 2, 3, 5; PRF = 27.7 MHz
   * - I\ :sub:`full-p6`
     - Current consumption, FULL state
     - 200
     - mA
     - Profile 6; PRF = 27.7 MHz

.. _supply-noise:

Supply noise
~~~~~~~~~~~~

Noise in the power supplies may affect the performance of the A212 sensor.
:numref:`a212-supply-ripple` provides the recommended maximum ripple levels for the
DIG_VDD, RX_VDD, TX_VDD, WG_VDD, XO_VDD, VCO_VDD and ANA_VDD supplies.

.. list-table:: Power supply ripple specifications (T\ :sub:`op` = 25°C)
   :name: a212-supply-ripple
   :header-rows: 1
   :widths: 50 50

   * - Frequency [kHz]
     - Max supply ripple [mV\ :sub:`pp`\]
   * - 50
     - 30
   * - 100
     - 30
   * - 200
     - 15
   * - 300
     - 15
   * - 500
     - 12
   * - 750
     - 7
   * - 1000
     - 7
   * - 1500
     - 5

If the voltage source violates the supply ripple specifications in :numref:`a212-supply-ripple`,
an LC filter as shown in :numref:`a212-lc-filter` can be used.
This filter has a cut-off frequency of 22 kHz. You can tune the values depending on the frequency and
amplitude of the ripple. Be aware of the LC filter peaking at the series resonance frequency
:math:`f_r = \frac{1}{2\pi\sqrt{LC}}`. A small snubber resistor (250 mΩ in the example) can be
inserted to lower the Q factor.

.. _a212-lc-filter:

.. figure:: /images/hw_images/A212_LC_filter.svg
   :width: 400px

   Optional LC supply filter.


.. _a212-xtal-selection:

Crystal selection
------------------

The A212 has a built in oscillator that requires an external 26 MHz crystal.
The crystal connection diagram is shown in :numref:`a212-xtal-diagram`.

.. figure:: /images/hw_images/A212_XTAL_connection.svg
   :name: a212-xtal-diagram
   :width: 300px
   :align: center

   Crystal (XTAL) connection diagram.

For the oscillator to be able to drive the crystal, the following criterion must be fulfilled:

.. math::

   f_{xtal} \cdot C_L^{0.8} \cdot R_{ESR}^{0.61} < 0.7 \quad \text{(Eq. 1)}

where :math:`f_{xtal}`, :math:`C_L` and :math:`R_{ESR}` are defined in the crystal datasheet.

The load capacitance :math:`C_L` is calculated as:

.. math::

   C_L = \frac{C'_{10} \cdot C'_{11}}{C'_{10} + C'_{11}} \quad \text{(Eq. 2)}

where:

.. math::

   C'_{10} = C_{10} + C_{10\text{-parasitic}} \quad \text{(Eq. 3)}

.. math::

   C'_{11} = C_{11} + C_{11\text{-parasitic}} \quad \text{(Eq. 4)}

- :math:`C_{\text{parasitic}}` is the PCB trace and package capacitance between the crystal pins (XIN and XOUT) and GND, expected to be between 1 pF and 2.5 pF per cm (depending on the trace width and stackup) plus package capacitance.
- :math:`C_{10}` and :math:`C_{11}` can be calculated as:

.. math::

   C_{10} = C_{11} = 2 \cdot C_L - C_{\text{parasitic}} \quad \text{(Eq. 5)}

Hardware schematics design checklist
------------------------------------

When designing the hardware schematics for the A212 sensor, the following checklist can be used to ensure a good design:

1. Does the selected crystal fulfill the load conditions according to the :ref:`XTAL selection <a212-xtal-selection>`?
2. Are all ground pins of the A212 connected on the schematic symbol?
3. Does the selected regulator meets the :ref:`Supply noise <supply-noise>` recommendations?
4. Are enable and interrupt pins connected?
5. Have you considered how to flash the NVM/MCU during production test?


