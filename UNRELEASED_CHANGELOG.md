# Unreleased Changelog

## Unreleased

### Added

### Changed

### Fixed

- Errors not listed in a type migration timeline's `fail=` are again
  propagated unchanged when raised while migrating through an older epoch,
  instead of being wrapped in a `MigrationErrorGroup`.

### Removed
