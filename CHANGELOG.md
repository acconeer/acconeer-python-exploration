# Changelog

## v6.0.4

### Changed
- Pin PySide version, which evades some problems with its latest release

## v6.0.1

### Changed
- Bump SDK version for A111

### Fixed
- XM125 bin fetching (part of flash).
- ClientInfo not being able to load some older files

## v6.0.0

### Added
- A121: Tank level reference app
- A121: Distance: Add recalibration functionality.
- A121: Distance: Add calibration needed and temperature to API.
- A121: Add surface velocity example app.
- A121: Distance: Add reflector shape to detector config.
- A121: Distance: Update peak sorting strategy selections.

# Changed
- Documentation structure
- Client interface
- Setting up instructions
- Drop beta for A121 Application

## v5.9.2

### Added
- A121: High speed mode, HSM, metadata. Available in RSS version > 0.8.0.
- A121: `tcp_port`-argument to `a121.Client`, which enables specifying
        the port of an exploration server. If not specified, the default
        port will be used.
- Parameter categories
- A121: Presets for presence detector and smart presence added.
        Default values are changed.

### Fixed
- Fix mock/simulated client for portable release
- Fix Python 3.7 incompatibility in AppModel

## v5.9.1

### Changed
- Change default PRF to 15.6 MHz

## v5.9.0

### Added
- A121: Breathing example
- A121: Bilateration example
- A121: Support for subsweeps in the Sparse IQ plugin
- A111: Presence detector human only
- A121: Smart presence reference app

### Changed
- Bump A121 SDK version to v0.8.0

### Removed
- A121: Sector plots in Presence detector example and plugin

## v5.8.1

### Added
- Sensor config info in distance detector

### Changed
- A121 presence: move inter and intra from extra_result to result
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

## v5.8.0

### Added
- Make it possible to use a Mocked/Simulated sensor system
- A121: Validation of processor config
- Save app settings to file
- Add advanced settings dialog
- Add auto-connect setting, found under advanced settings

### Changed
- Rename Virutal button to Touchless button

## v5.7.0

### Added
- Separate changelog for unreleased changes
- Frame count in status bar
- Support for 15.6HMz PRF

### Fixed
- Unplugging of USB device not detected
- Sync default sensor with connected sensors

## v5.6.0

### Added
- Make it possible to select USB device with serial number
- A121: Vibration: Peak detection
- A121: Plugin configuration presets

### Changed
- Forbid setting up with 5.2HMz PRF if the connected server cannot handle that.

### Fixed
- A121 presence: Fix depth filter length so it never is bigger than
  the number of points
- Correct downloading of new firmware by adapting to new developer site
- Flasher: Enable DFU from detached usb device with PyUsbCdc
- Pickling error on Windows when running standalone

## v5.5.1

### Fixed
 - Make sure to use correct flash port interface on Linux

## v5.5.0

### Added
- A121: Calibration reuse example
- A121: Bilateration application
- Toggle to enable/disable recording

### Changed
- A121: Target RSS version v0.6.0
- A121 distance detector: Minor improvements

### Fixed
- USB connection issues

## v5.4.1

### Added
- App taskbar icon on Windows

### Changed
- A121 presence detector: Add support for setting inter frame idle state

### Fixed
- A121 recorder crashing when stopping due to empty chunk buffer
- A121 recorder can't load recording without calibration
- Flash port not detected correctly

## v5.4.0

### Added
- Vibration measurement application

### Changed
- Use USB communication when possible in linux
- Simplify USB device selection in client

### Fixed
- Fix App hints widget

## v5.3.1

### Fixed
- Make sure to have qtpy>=2.3.0

### Added
- Add SensorCalibration to session

### Changed
- A121 distance detector. Optimize CFAR calculation.
- Use built-in function to display markdown and thereby remove dependency to
  Markdown
- A121 presence detector: Change minimum start distance for profiles

### Fixed
- A121 distance detector: Fix bug in CFAR calculation where num_stds was
  applied to full threshold.
- A121 algo utils: remove prf 19.5 MHz for profile 2 in select_prf

## v5.3.0

### Fixed
- Serial port tagging for XE123, XE124, XE125 modules
- Disable connect button for an unflashed XC120 device
- Silent backend logging on Windows

### Added
- Ability to download and flash latest binary for XC120
- Backend CPU load in status bar.
- Add warning in the App if an unflashed device is connected
- Notify user for new library versions
- Support for multiple subsweep configs in view

### Changed
- Design of status bar.
- A121 distance: Aggregate calibration methods into one function

### Removed
- Proximity power from regmap


## v5.2.9

### Fixed
- A121 presence detector: set prf based on range
- A121 presence detector: fix number of points calculation to include end range
- A121 presence detector: set presence:distance to 0 when no presence detected
- A121 distance detector: offset compensation bugfix
- A121 distance detector: fixed numpy warning due to mean of empty slice
- Pin PySide6 to 6.3.1 to avoid incompatible versions

### Added
- Update rate to distance detector.
- Rate/jitter warnings in status bar.

### Changed
- A121 distance detector: increase signal quality span
- A121 distance detector: perform noise calibration standalone.

## v5.2.8

### Fixed
- Fix bug where no folder was created when caching

### Add
- int16_complex_array_to_complex utility function to `a121`-package

## v5.2.7

### Fixed
- QGraphicsEllipseItem was moved from QtGui to QtWidgets.
- Make sure to set correct sensor id when playing back recorded data.
- Bug that made SessionConfigEditor overwrite changes made by the user
  (unless the user was really fast).

## v5.2.6

### Fixed
- Replace addDataItem() with addItem(). This function was removed in pyqtgraph
  0.13.0

## v5.2.5

### Fixed
- Pin version of PySide6 to avoid bug with overriding builtin enum in Python 3.9

### Changed
- A121: Convert cache from pickle to h5

## v5.2.4

### Added
- A121: Possibility to specify baudrate in the App
- A121: Phase tracking example app.
- A121 presence detector: inter-frame phase boost
- A121 presence detector: inter-frame timeout

### Removed
- A121: One-sided CFAR.
  The concept is not valid with the close range measurement strategy.

### Fixed
- A121: Convert config/context classes to dict before pickle
- Metadata view spacing issue
- A121: Double buffering added to sensor config editor in app

## v5.2.3

### Fixed
- A111: Unclear-ness in the Calibration management section.
  Users are now able see if calibrations are used by the processor or not.
- A121 presence detector: Fix step_length bug when using profile 1.

### Added
- A121 presence detector: Separate output for inter- and intra-frame parts.

## v5.2.2

### Removed
- Temporally disable auto-connect functionality because it introduced issues
  related to flashing

## v5.2.1

### Fixed
- Cache-related bug that made Distance Detector unusable.

### v5.2.0
- Platform setup script that is ran with `python -m acconeer.exptool.setup`.
- Sensor selection for Presence- and Distance detector.

## v5.1.0

### Added
- Platform-specific setup scripts
- A121 distance detector: Distance offset calibration
- A121 distance detector: Noise calibration
- A121 presence detector: Settings for profile and step length

### Changed
- A121 distance detector: Account for processing gain when calculating
  HWAAS.

### Fixed
- Fix sensor selection bug on disconnect.
- Only detect USB devices on Windows.

## v5.0.4

### Added
- Support for "simple" A121 records to the `convert_to_csv` utility.
- Sensor id selection to the new A121 application.

## v5.0.3

### Fixed
- Fix version parsing for a111. Version string "a111-vx.x.x" is now
  handled properly.

## v5.0.2

### Fixed
- Fix client timeout when auto-detecting port

## v5.0.1

### Added
- Add *.orig to .gitignore
- Add A121 EVK setup to readme

### Changed
- Bump A111 SDK version to 2.12.0

### Fixed
- Make clean up after stop session more stable
- Set link timeout depending on server update rate and sweep rate

## v5.0.0

This major release provides initial support for the A121, with a new
app, new algorithms, and a stable core API.

No changes has been made to the old application nor the A111 API.

### Added
- A new application, currently only for A121. In the future, A111 will
  be supported in this new app as well, removing the need for two
  separate apps.
- Support for A121 v0.4, amongst other things adding a
  `double_buffering` parameter to `a121.SensorConfig`.
- A121: Initial version of a distance detector.
- A121: Initial version of a presence detector.
- A121: XC120 WinUSB support, for improved data streaming performance
  on Windows.
- A121: Ability to load record from file to RAM.

### Fixed
- A121: Several minor issues in the core API.
- Avoid incompatible dependencies.

## v4.4.1

### Changed
 - Remove references to Ubuntu 18.04
 - Moved Parking to examples

### Fixed
 - Add sampling mode for Sparse in configuration.
   Was accidentally removed, when sampling mode was removed for IQ.
 - Add sampling mode for Sparse when exporting C code.

## v4.4.0

### Added
- `enable_loopback` parameter to `a121.SubsweepConfig`.
- Side/pole mounted case for parking detector.
  Modifies some default settings as well as slight changes in computations.

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
