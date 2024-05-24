Differences between A121 and A111
=================================

Here are some of the main differences, additions, and highlights with A121 compared to A111:

- The four services available for the A111
  --
  *power bins*, *envelope*, *IQ*, and *sparse*
  --
  are all superseded by the *sparse IQ* service.
  This new service combines the individual strengths of all A111 services into one, without any sacrifices or compromises.
- Range is now set in a discrete "point" scale instead of meters, which allows full control over the measured range.
  The range is no longer limited to 60 mm intervals.
- In the new range scale, the *downsampling factor* of A111 is replaced by *step length*.
  This also brings a much wider range of settings, starting at 2.5 mm.
- Any number of sweeps may be measured per frame, only limited by buffer size.
- The sensor buffer now holds 4095 complex points.
- The floating point gain scale is replaced by a much wider integer scale, allowing for more precise control and removing the need for *maximize signal attenuation*.
- *Power save mode* is replaced by *inter sweep/frame idle states*, meaning it's now possible to set the idle state between sweeps as well as between frames.
- *MUR* is replaced by *PRF* with similar behavior but a wider range of settings.
- The *repetition mode* is simplified to a *frame rate* setting.
  If set, it corresponds to using the *streaming* mode.
  If not set, it corresponds to using the *on demand* mode.
- The *get next* function is split up into four functions for more flexible control over the measurement execution flow
  --
  *measure*, *wait for interrupt*, *read*, and *execute processing*.
  This also removes the need for the *asynchronous measurement* setting.
- The sensor can now be fully reconfigured on the fly via the *prepare* function, which loads a (new) configuration onto the sensor.
- The sweep can now be split up into *subsweeps* with different configurations,
  for example allowing you to use different profiles across the range.
