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

### Fixed

### Removed

- Support for Python 3.9, 3.10 & 3.11
