########
Glossary
########

.. glossary::

   SNR
      Abbrevation of *Signal-to-noise ratio*.
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
      A near-complete use case specific package-offering.
      Differs from :term:`Detectors<Detector>` as they are not intended to be usable, but
      rather do one thing, and one thing well.

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
