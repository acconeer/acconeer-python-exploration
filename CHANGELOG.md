# Changelog

## Unreleased

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
