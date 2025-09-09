########
Glossary
########

.. glossary::

   Direct leakage
      Direct leakage refers to the transmission of the radar signal directly from the transmitter to the receiver without reflecting off a target. The length of the direct leakage varies with the transmitted pulse length. The transmitted pulse length is set using :term:`Profiles<Profile>`.

   PCR
      Pulsed Coherent Radar.

   PRF
      Pulse repetition frequency. The frequency at which the radar transmits wavelets.

   Profile
      Profiles are used to set the transmitted pulse length in discreet steps. The higher the Profile, the longer the transmitted pulse length.

   SNR
      Abbreviation of *Signal-to-noise ratio*.
      General ratios quantify how much more there is of *one thing* (Signal in this case),
      compared to the *other thing* (noise). Generally, a high SNR means high signal quality. SNR can be defined as

      .. math::
         :label: eq_snr_glossary

         SNR=C \sigma \gamma \frac{1}{R^{4}}

      Where :math:`R` is the distance of the radar to the target, :math:`C` is the radar loop gain, including both the transmitter and receiver chain (two-ways signal path), :math:`\sigma` is the :term:`Radar Cross Section (RCS)<Radar Cross Section>` of the scattering object and :math:`\gamma` determines the reflected power of the object's material. :term:`RCS<Radar Cross Section>` depends on the size and shape of the scattering object.

   Reflectivity
      A property of physical materials.
      If a material is more *reflective*, more power finds its way back to the sensor and vice versa. See :math:`\gamma` in :eq:`eq_snr_glossary`.

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

   Far-field
      The far-field distance can be determined by the aperture of the sensor and the radar target.

      .. math::
         :label: eq_farfieldistance

         R_{farfield}>\frac{2A^{2}}{\lambda_{0}}

      where :math:`A` is the largest dimension of either the sensor or the radar target, and :math:`\lambda_{0}` is the wavelength in free-space. The far-field region is where the radiation pattern shape does not change with the distance. However, the radar works below the far-field distance with different characteristics than the far-field region with radiation pattern dependency on the distance.

   RLG
      Radar Loop Gain, the transmitter and receiver gain of the radar, combined.

   Dielectric
      A dielectric is an insulating, non-conducting material that can be polarized by an electric field. It is often used as a structural component or as a medium for controlling electromagnetic wave propagation. Some common examples include air, wood, and various polymers and plastics.

   Reflection
      Reflection is the portion of an electromagnetic wave that is returned or “bounced back” when it encounters a boundary between two materials with different dielectric properties. In radomes, reflection causes a fraction of the radar signal to be lost or redirected, depending on the difference in dielectric constants between air and the radome material.

   Transmission
      Transmission is the portion of an electromagnetic wave that passes through a material. For radomes, good transmission means most of the radar signal passes through the material without significant loss or distortion.

   Refraction
      Refraction is the bending or change in direction of an electromagnetic wave as it passes from one material into another with a different dielectric constant. In radomes, refraction slightly alters the wave's path but is usually minimal if the material is thin and uniform.

   Diffraction
      Diffraction is the bending and spreading of electromagnetic waves as they pass through apertures or around obstacles. In dielectric Fresnel zone plate lenses, diffraction is the primary mechanism that shapes the wavefront and focuses energy along the designed propagation path.

   Permittivity
      Permittivity is a material property that describes how an electric field interacts with a medium. It determines how much the electromagnetic wave slows down and how the material stores electric energy. The relative permittivity, often called the dielectric constant, compares the material’s permittivity to that of free space and is the key parameter for radar-transparent materials like radomes and lenses.

   Linear polarization
      Linear polarization describes an electromagnetic wave in which the electric field oscillates in a single plane along the direction of propagation. Most radome and lens analyses assume linear polarization to simplify reflection and transmission calculations.

   Normal incidence
      Normal incidence occurs when an electromagnetic wave strikes a surface or interface at a 90° angle, meaning the wavefront is perpendicular to the surface. Reflection and transmission at normal incidence are simplified compared to oblique angles.

   LOS
      Line-of-sight. A straight line between the radar and a target without obstructions.
