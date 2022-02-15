# Changelog

## Unreleased

### Added
- Command line arguments `--no-config` and `--purge-config` which lets you
  manage files that the Exptool app produces.

### Changed
- Change of nomenclature regarding the GUI, is now called *"the app"*.
- The Exptool app is now part of the `acconeer-exptool` package! Is now run
  with `python -m acconeer.exptool.app` instead of `python gui/main.py`
- Detector- and Service standalone examples have been moved into the
  `acconeer-exptool`-package. (`acconeer.exptool.a111.algo` to be precise.)
- Standalones are now runnable with
  `python -m acconeer.exptool.a111.algo.<service or detector>`
- `internal/` renamed to `tools/`. Still intended for internal use.
- Structure of standalones are separated into
  `processing`- and `plotting` modules
- Reduced code duplication of standalones' main functions.
- App sessions are saved to a standard user location instead of the current
  directory.

### Removed
- Machine Learning GUI
- imock
