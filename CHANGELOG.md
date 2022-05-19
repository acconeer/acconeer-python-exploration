# Changelog

## Unreleased

### Fixed
- Bug that made `a121.Client` not stop its session
  if the session was started with a recorder.

## v4.3.0

### Added
- Unstable (but fully featured) library for the A121 sensor
  generation under `acconeer.exptool.a121`.

## v4.2.0

### Added
- Possibility to export Sensor configuration to C code for use with RSS.

### Changed
 - Update demo images in sensor introduction

### Fixed
- The update rate when replaying a saved file is now
  the same as the file was captured in.

## v4.1.1

### Changed
 - Bump A111 SDK version to v2.11.1

## v4.1.0

### Added
- Wave to exit algorithm added.
- Tank level algorithm for small tanks.

## v4.0.4

### Fixed
- Issue where Exploration tool could not be run on Python 3.7.


## v4.0.3

### Added
- Control for amount of peaks plotted in Distance Detector.

### Fixed
- Implicit behavior of calibration application. Now never applies a
  calibration unless explicitly done by the user.


## v4.0.2

### Changed
- Module server protocol is now default for UART connections in examples

### Fixed
- Outdated referenced to `recording` module in File format reference (docs)
- Bug that did not allow examples and standalones to be run over UART


## v4.0.1

### Changed
- Bump A111 SDK version to 2.11.0


## v4.0.0

### Added
- Command line arguments `--no-config` and `--purge-config` which lets you
  manage files that the Exptool app produces.
- Installation via PyPI with `python -m pip install acconeer-exptool`
- requirements-dev.txt for developers
- Common calibration interface for processors
- Deprecation warning on Streaming Server
- Drop down list in app to select server protocol


### Changed
- Change of nomenclature regarding the GUI, is now called *"the app"*.
- The Exptool app is now part of the `acconeer-exptool` package! Is now run
  with `python -m acconeer.exptool.app` instead of `python gui/main.py`
- Detector- and Service standalone examples have been moved into the
  `acconeer-exptool`-package. (`acconeer.exptool.a111.algo` to be precise.)
- Some algorithm modules have been renamed
- Standalones are now runnable with
  `python -m acconeer.exptool.a111.algo.<service or detector>`
- `internal/` renamed to `tools/`. Still intended for internal use.
- Structure of standalones are separated into
  `processor`- and `ui` modules
- Reduced code duplication of standalones' main functions.
- App sessions are saved to a standard user location instead of the current
  directory.
- Move package dependencies to setup.cfg from requirements.txt (Removing
  requirements.txt and requirements_client_only.txt). Add extras algo and app
  to define additional dependencies.
- Replace tox with nox
- Update python version for portable to 3.9.10
- Update run and update batch files for portable version for Windows. Old
  portable version is no longer compatible.
- SDK version is now specific for A111 (acconeer.exptool.a111.SDK_VERSION)

### Removed
- Machine Learning GUI
- imock
- Sensor fusion in obstacle
- Multi-sensor support in distance and obstacle
- WSL support
- Legacy dict based processing configuration interface
- Legacy calibration interfaces
