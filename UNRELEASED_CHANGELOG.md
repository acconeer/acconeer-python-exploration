# Unreleased Changelog

## Unreleased

### Added
- Sensor config info in distance detector

### Changed
- A111: Update calibration behavior
  * No longer automatically applied on start, unless auto-apply is ticked
  * Loading calibration will not auto-apply, unless auto-apply is ticked
  * New calibration will not be stored in application if a calibration is
    already present. Old calibration has to be cleared first
  * Calibration status is updated to reflect this

### Fixed
- Make sure to sync sensor ids after replaying file
- A111: Check that calibration background and data length matches, otherwise
  raise an exception
- Re-add TickUnwrapper
