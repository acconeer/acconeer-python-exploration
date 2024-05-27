########
Glossary
########

.. glossary::

   PCR
      Pulsed Coherent Radar.

   PRF
      Pulse repetition frequency. The frequency at which the radar transmits wavelets.

   SNR
      Abbreviation of *Signal-to-noise ratio*.
      General ratios quantify how much more there is of *one thing* (Signal in this case),
      compared to the *other thing* (noise). Generally, a high SNR means high signal quality.

   Reflectivity
      A property of physical materials.
      If a material is more *reflective*, more power finds its way back to the sensor and vice versa.

   Radar Cross Section
      Depends on the shape of the :term:`Object` measured. Affects how much power returns to the sensor.

   Object
      The physical thing a sensor should measure.

   Detector
      A reusable, well tested, package-offering that consists of an API for
      :term:`Sensor Control`, higher-level output (like distance to :term:`objects<Object>`)
      all backed by signal processing algorithms.

      Detectors are used to enable many use cases.
      They are diligently used in our :term:`Reference Applications<Reference Application>`.

   Sensor Control
      Describes controlling the sensor on a low level or the sequence of sensor *verbs*
      (``prepare``, ``measure``, ``process``, ``power_on``, etc.) in the context of
      :term:`Detectors<Detector>`,
      :term:`Reference Applications<Reference Application>` or
      :term:`Example Applications<Example Application>`.

   Reference Application
      A nearly complete use case specific package-offering.
      Unlike :term:`Detectors<Detector>`, these packages are targeting more specific
      use cases, such as *Tank Level* or *Parking*.

   Example Application
      A use case specific proof-of-concept signal processing algorithm
      that haven't undergone significant testing, but works quite well in the scenarios tested.

   Exploration Tool
      Acconeer's graphical sensor evaluation application.
      All
      :term:`Detectors<Detector>`,
      :term:`Reference Applications<Reference Application>` and
      :term:`Example Applications<Example Application>`
      are showcased here and new ones are added continuously.
