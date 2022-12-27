# Unreleased Changelog

## Unreleased

### Changed
- A111: Update calibration behavior
  * No longer automatically applied on start, unless auto-apply is ticked
  * Loading calibration will not auto-apply, unless auto-apply is ticked
  * New calibration will not be stored in application if a calibration is
    already present. Old calibration has to be cleared first
  * Calibration status is updated to reflect this

### Fixed
- Make sure to sync sensor ids after replaying file
