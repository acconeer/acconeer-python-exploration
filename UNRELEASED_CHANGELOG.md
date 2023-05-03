# Unreleased Changelog

## Unreleased

### Added
- A121: Surface velocity: Validation added to check that start point is
  larger than the surface distance
- Tabs in the A121 Application

### Changed
- A121: Surface velocity: Remove sensor angle from processing config, it's not used

### Fixed
- A111: Perform handshake on multiple baudrate even when overriding baudrate
- A111: Fix bug with not being able to untick override baudrate option
- A111: Bug in acconeer.exptool.app --purge-config which caused a crash
