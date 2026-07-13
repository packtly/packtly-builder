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

## [1.3.0] - 2026-07-13
### Added
- Robot Framework integration test environment for end-to-end validation of packtly-builder builds via Podman
- Robot test runner, keywords, and a Debian example build/verification suite
- Debian packaging fixtures (`test/fixtures/debhello-quilt`) for integration testing
- CI workflow for running Robot Framework tests with artifact upload and PR reporting via `robotframework-reporter-action`


## [1.2.0] - 2026-07-04
### Added
- Source package build
- Introduced automatic creation of .orig tarballs from the working tree when pristine-tar is not available
- Added DebSourceBuilder to manage and automate upstream source archive generation.
- Add of multi architecture support (x86, arm64 and armhf)
- Add support for full build mode and enhance package existence checks
- `deb_source`: cache parsed changelog; invalidate after `git checkout` in `reset_source_tree`

### Changed
- Improved SIGINT / KeyboardInterrupt handling
- `debuild`: pass `-sa` flag to always include orig tarball in `.changes` for source/full builds
- `apt`: improve binary and source package existence detection with per-file `[EXISTS]`/`[MISSING]` logging
- `AptManager`: reorganise class into logical sections (repository, installation, existence checks, private helpers)
- `log`: add error logging for failed package upload

### Fixed
- Source package upload no longer fails when `.orig.tar.*` is absent from `.changes` on non-first revisions


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
