# Unreleased Changelog

## Unreleased

### Added

- Quit the Exploration Tool by pressing Ctrl+C three times within five
  seconds in the launching terminal. Holding the key down counts as a
  single press, so an unintentionally long tap won't quit early.
- Link to Acconeer's security page from the documentation landing page,
  for security information and vulnerability reporting.

### Changed
- A121 Distance: `ThresholdMethod.RECORDED` and `RecordedThresholdCalibration`
  are removed. Close range measurements internally still use a recorded
  threshold, calibrated automatically.
- Distance detector's `CONFIG_MISMATCH` status now only considers changes to
  `profile` and `receiver_gain`,
  since those are the only parameters noise calibration depends on. Changes to
  other `DetectorConfig` parameters no longer force a recalibration.
- The A121 Distance Detector now uses the whole processing gain in its
  HWAAS calculation, which lowers HWAAS for a given signal quality.
  Measurements get faster and cheaper at the SNR the setting asks for,
  and reported strengths, far range breakpoints and the HWAAS saturation
  distance follow. To keep the HWAAS of an existing configuration, raise
  signal quality by 9*log10(processing gain), which is 5.2, 5.5, 5.5,
  6.3 and 5.8 dB for max profile 1 to 5 with the step length left
  automatic, and up to 17 dB with the step length forced to 1.
- The default signal quality of the A121 Distance Detector is raised from
  15.0 to 20.8 dB, and the presets of the distance, tank level, cargo and
  bilateration applications by their own offset, so every one of them
  keeps the performance it had before the HWAAS change. A configuration
  carried over from an older version can be converted with
  `distance.carry_over_signal_quality()`.

### Fixed

### Removed

- Support for Python 3.9, 3.10 & 3.11
