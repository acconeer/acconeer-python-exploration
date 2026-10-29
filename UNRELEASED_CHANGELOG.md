# Unreleased Changelog

## Unreleased

### Added
- The flash tab can download the XE212 exploration server from
  developer.acconeer.com.
- The Resource Calculator estimates power and memory for A2 configurations
  as well. An A121/A2 selector, shared with the stream tab, picks which
  generation's configurations and estimates it shows.

### Changed
- The A2 apps pick the sensor's roll and pan with picture buttons, and
  show its tilt in a picture.

### Fixed
- The version menu of the docs no longer appears on every page of a printed
  single-page guide.
- Flashing an XE212 that runs firmware no longer fails every other time with
  "Timeout when receiving data from device".
- Installed with pip on Python 3.12 or newer, the app was drawn in an
  outdated theme. In an existing environment, run
  `pip uninstall pyqtdarktheme` before upgrading.
- The tabs after the first, such as the A2 sensor configuration's later
  subsweeps, set their sections closer to the tab bar than the first did.
- The A121/A2 selector's list shows "A121" in full, instead of cutting it
  off behind a blank gap.

### Removed
