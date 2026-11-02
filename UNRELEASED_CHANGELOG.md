# Unreleased Changelog

## Unreleased

### Added
- Quit the Exploration Tool by pressing Ctrl+C three times within five
  seconds in the launching terminal.
- Link to Acconeer's security page from the documentation's front page.
- Single-page A121 and A212 hardware integration guides, for printing or
  saving as PDF.

### Changed
- A121 Distance: Measures faster at the same detection performance.
  Configs saved by an older version get a lower HWAAS; raise their
  signal quality by 5-6 dB (up to 17 dB with step length 1) to keep it.
- A121 Distance: Only changes to profile, HWAAS or receiver gain
  require a recalibration.
- A121 Distance: The recorded threshold method is removed.
- On Linux, the app requires glibc 2.34 or newer (e.g. Ubuntu 22.04).
- Replaying recordings is much faster.
- USB no longer delays or drops frames while the PC is busy. If USB
  misbehaves, set the environment variable `ET_LEGACY_USB=1`.

### Fixed
- Resource tab: more accurate heap estimate for the A121 Distance Detector.
- Generic icon instead of the app's own in the Windows taskbar at startup.
- Leaving fullscreen plots un-maximized a maximized window.
- Busy mouse pointer for seconds at startup on GNOME (Wayland).
- Flash wizard's license dialog was nearly empty.
- A fresh install could fail to start with an import error from h5py or
  pandas.

### Removed
- Support for Python 3.9, 3.10 & 3.11
