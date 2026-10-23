# Unreleased Changelog

## Unreleased

### Added

### Changed

### Fixed

- Fixed `opser` loading of fixed-length `Tuple`s with more than 10 elements.
  Elements were matched to tuple positions in HDF5 name order ("0", "1",
  "10", ...) instead of numeric order, giving misordered values or a load
  error unless creation order tracking was enabled.

### Removed
