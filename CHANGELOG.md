# Changelog

## v7.17.6

### Added
 - Add the 'acconeer-exptool' executable script, allowing ET to be
   launched directly from the command line using acconeer-exptool,
   as well as via 'uvx acconeer-exptool'.
 - Add the 'acconeer-flash' executable script, allowing flashing
   to be launched directly from the command line using acconeer-flash.

### Changed
- Change high frequency preset in Vibration.
  Previous preset only utilized half the radar data.
  Now all radar data gathered is used.

## v7.17.5

### Fixed
- Module not recognized when flashing on Windows

## v7.17.4

### Added
- Bugfix & improvement in USB code

## v7.17.3

### Changed
- Use libusb instead of winusb for USB communication on windows
- Use libusb_package to get backend for USB communication on windows

### Removed
- A121 presence detection phase boost removed

## v7.17.2

### Changed
- Bump SDK version for A121

## v7.17.1

### Changed
- Bump SDK version for A121

### Fixed
- Disallow setuptools_scm>=9.0.0

## v7.17.0

### Added
- Cargo example application added

## v7.16.1

### Fixed
- Pin PySide6 & PyQtGraph

## v7.16.0

### Added
- Level tracking feature for Tank Level

## v7.15.0

### Added​
- IQ imbalance compensation parameter​
- IQ imbalance compensation docs​
- PRF validation over subsweeps​

### Changed​
- Update flash utilities for dev site login​
- Refactor detector distance config translation

## v7.14.3

### Added
- Support for Python 3.13
- Warn users if multiple Qt binding are installed
- Possibility to export config as CSV

### Changed
- Tank level: Disable leakage cancellation as default
- Tank level: Assign correct level status
- Tank level: Update maximum distance to 23 m
- Tank level: Update presets
- A121: Bump SDK version

### Fixed
- A121 Distance: Use the same PRF for all subsweeps

### Removed
- Support for Python 3.8
- A121 Distance: Removed PRF config from distance detector

## v7.13.2

### Fixed
- A121: Validate maximum end range on surface velocity
- A121 Distance Detector/Tank Level: Resolve issues with cache loading

## v7.13.1

### Changed
- A121: Update SDK version

## v7.13.0

### Changed
- Distance: Use a more narrow filter for distance filter
- Distance: Reduce order of Butterworth distance filter
- Distance: Update CFAR threshold to be one-sided close to the sensor

## v7.12.2

### Fixed
- Don't use PySide6==6.8 as it does not work properly.

## v7.12.1

## v7.12.0

### Added
- A121 Distance: PRF override configuration

### Fixed
- A121 Distance: Fix bug where max_step_length = 1 together with profile 5
  gave undefined behavior.

## v7.11.1

### Fixed
- A121 Waste level: Avoid interference from direct leakage by limiting min start
  point
- Limit Numpy version to <2.0 to avoid compatibility issues

## v7.11.0

### Added
- A121 vibration: Add low frequency mode
- A121: Add multiple algos to convert_h5.py

### Changed
- A121 hand motion: Update to use one presence processor
- A121 hand motion: Update mode handler and make result consistent

### Fixed
- A121 Distance: Bugfix for short range measurement with profile 1
- A121 Ref app parking: Fix bug that blocks usage of other sensor ids than 1

## v7.10.0

### Changed
- Update Parking to use subsweeps
- Update presence detector to support automatic
  subsweeps configuration
- Update low power wake up preset

## v7.9.0

### Added
Plugin system! You are now able to write your own plugins for
the new Exploration Tool.

Head over to docs.acconeer.com and navigate to

Exploration Tool > Algorithms > A121 > Adding your own plugin

to get started!

## v7.8.3

### Changed
- Bump SDK version for A111 and A121

## v7.8.2

### Fixed
- A111 Presence: Avoid division by 0 for saturated data when using PCA

## v7.8.1

### Fixed
- Flashing latest binary after website update

## v7.8.0

### Added
- Waste level example app

### Changed
- Parking: Some labels in the GUI now better reflect
  fields in the config object.
- Speed: Change threshold line from solid to dotted
  to make it easier to distinguish

### Fixed
- Parking: Add missing documentation

### Removed
- The Obstacle Bilateration example app

## v7.7.4

### Added
- Plugin title to plot area
- Display filename of loaded data file
- Hide unnecessary details in the status bar when not in the Streaming tab.
- Resource calculator: Add input block renaming

## v7.7.3

### Added
- A121 Parking algorithm and documentation.
- Strength added to target in obstacle.
- Direct links to algorithms' documentation pages.
- Example for post-processing recorded data.

### Changed
- Some error messages have been improved to simplify troubleshooting.

## v7.7.2

### Added
- Tooltips for speed detector.

## v7.7.1

### Changed
- Bump SDK version for A121

## v7.7.0

### Added
- Support for Python 3.12
- Many algorithms have gotten tooltips in their config editors.
  Hover the name to get a description of that parameter!
- High and low frequency presets for new vibration application

### Changed
- The Vibration algorithm has been improved to be able to measure both higher
  and lower vibration frequencies, all while not having to use
  continuous sweep mode.
- Distance detector no longer defaults to use
  `close_range_leakage_cancellation`.

### Removed
- Support for Python 3.7

## v7.6.1

### Fixed
- Bug in Sparse IQ where selecting multiple subsweeps
  resulted in an uncaught exception

## v7.6.0

### Added
- Add hand motion detection algorithm for faucet applications

### Changed
- Resource Calculator
    - Power Curve average current is no longer dependent on "X-axis length"
    - Power Curve now displays average current in 10ths of uA when below 1 mA.

### Fixed
- Make it possible to run on other sensor ids than 1 for ref app breathing

## v7.5.1

###
- Mention resource calculator in docs

### Changed
- Bump SDK version for A121

## v7.5.0

### Added
- New tab: Resource Calculator.
  Visualizes power- and memory consumption for different configurations,
  enabling quick-and-easy comparisons.
  Supports Sparse IQ, Distance- and Presence detector.

### Changed
- Rename covert\_to\_csv.py to convert\_h5.py

### Fixed
- Distance: Remove duplicate breakpoints

## v7.4.0

### Added
- Basic multisensor support in the SparseIQ plugin.

## v7.3.0

### Added
- A121: Distance: Add fixed strength threshold
- A121: Distance: Visualize multiple time series in history plot

### Changed
- Move links.py from a111 folder to root folder

## v7.2.1

This release only contains minor fixes and improvements.

## v7.2.0

### Added
- A121: Smart presence: Add wake up mode
- A121: Client now raises an error if no sensors can be detected
        on the server.
- Documentation for the speed detector
- Examples for the speed detector
- Better handling of unexpected communication errors (lost connection, etc.)
  in the A121 Client.

### Fixed
- A111: convert_to_csv.py can now output metadata for the envelope service
- A121: Detach recorded if start_session fails
- A121: Validate start point in subsweep config

## v7.1.0

### Added
- New algorithm: Speed detector
- Config load- & save for the majority of configs in the A121 App.
- Export some configurations to C via the config save buttons.
  + Sparse IQ
  + Distance detector
  + Presence detector
  + Tank level
- A121: Presence: Add context with estimated frame rate to presence detector

### Changed
- Breathing is now a reference application instead of an example

## v7.0.2

### Fixed
- A121: Fix replaying issues in apps

## v7.0.1

### Fixed
- Recording bug introduced in v7.0.0 that broke all algorithms.

## v7.0.0
This release is not fully backwards compatibility,
which calls for a *major bump* (`v6 -> v7`).

### Changed
`Client` & `H5Recorder` classes have been changed (and upgraded).
`H5Recorder` is now able to record multiple `Client` sessions in a single file.
Recommended usage can be seen below.
Detectors and Reference Applications have gotten no changes.

```
client = a121.Client.open()

with a121.H5Recorder("filename.h5", client):
    for number_of_sessions in range(10):
        client.setup_session(a121.SessionConfig())
        client.start_session()

        for _ in range(10):
            client.get_next()

        client.stop_session()

client.close()
```

All examples have been updated accordingly.

## v6.0.5

### Added
- A121: Surface velocity: Validation added to check that start point is
  larger than the surface distance
- Tabs in the A121 Application

### Changed
- A121: Surface velocity: Remove unused sensor angle from processing config

### Fixed
- A111: Perform handshake on multiple baudrate even when overriding baudrate
- A111: Fix bug with not being able to untick override baudrate option
- A111: Bug in acconeer.exptool.app --purge-config which caused a crash

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

### Changed
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
- Rename Virtual button to Touchless button

## v5.7.0

### Added
- Separate changelog for unreleased changes
- Frame count in status bar
- Support for 15.6MHz PRF

### Fixed
- Unplugging of USB device not detected
- Sync default sensor with connected sensors

## v5.6.0

### Added
- Make it possible to select USB device with serial number
- A121: Vibration: Peak detection
- A121: Plugin configuration presets

### Changed
- Forbid setting up with 5.2MHz PRF if the connected server cannot handle that.

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
- Use USB communication when possible in Linux
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
- A121 algo utils: remove PRF 19.5 MHz for profile 2 in `select_prf`

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
- A121 presence detector: set PRF based on range
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
- A111: Unclearness in the Calibration management section.
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
- Fix version parsing for a111. Version string `"a111-vx.x.x"` is now
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
