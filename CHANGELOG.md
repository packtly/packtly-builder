# Changelog
All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

<!--
## [x.y.z] - yyyy-mm-dd
### Added
### Changed
### Removed
### Fixed
-->
<!--
RegEx for release version from file
r"^\#\# \[\d{1,}[.]\d{1,}[.]\d{1,}\] \- \d{4}\-\d{2}-\d{2}$"
-->

## [1.1.0] - 2026-06-11
### Added
- Aptly authentication via `--credentials-file`
- `--log-file` CLI argument for file logging
- Build dependency handling for virtual packages and architecture restrictions
- Dedicated aptly credentials support for authenticated publishing workflows
- Add check if a package is already published

### Changed
- Build/test scripts were modularized to separate package build and upload phases
- Aptly package build/upload flow was hardened with improved validation, logging, and failure handling

## [1.0.0] - 2025-01-26
### Added
- First release
