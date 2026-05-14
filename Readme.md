# packtly-builder

A containerized build system for creating, signing, and publishing Debian packages to an [Aptly](https://www.aptly.info/) repository.

## Overview

packtly-builder provides:

- **Container images** — a layered set of Podman images based on Debian Trixie for building and running Debian packages
- **`packtly_builder_tooling`** — a Python CLI that orchestrates the full build-sign-publish pipeline
- **CI/CD pipeline** — GitLab CI configuration covering image builds, tooling tests, deployment, and versioned releases

### Container stages

| Image | Purpose |
|---|---|
| `packtly-builder-base` | Debian Trixie with `debhelper`, `devscripts`, `gnupg2`, etc. |
| `packtly-builder-builder` | Base + Poetry, `just`, tooling venv — used for CI builds |
| `packtly-builder` (runtime) | Base + installed `packtly_builder_tooling` wheel |
| `packtly-builder-devcontainer` | Builder image configured for VS Code devcontainer use |

## Prerequisites

- [Podman](https://podman.io/) and [podman-compose](https://github.com/containers/podman-compose)
- [just](https://github.com/casey/just)

## Getting started

```bash
# Build all images, run tests, and build the tooling wheel
just all

# Or step by step:
just build-builder        # Build the builder image
just test-tooling-keys    # Verify GPG key setup
just test-tooling         # Run the Python test suite
just build-tooling        # Build the Python wheel
just build-runtime        # Build the final runtime image
```

## Available targets

```
just                      # List all targets
```

### Build

| Target | Description |
|---|---|
| `build-base` | Build the base container image |
| `build-builder` | Build the builder container image |
| `build-runtime` | Build the runtime container image |
| `build-devcontainer` | Build the devcontainer image |
| `build-tooling` | Build the `packtly_builder_tooling` Python wheel |

### Test

| Target | Description |
|---|---|
| `test-tooling` | Run the full pytest suite inside the builder container |
| `test-tooling-keys` | Verify GPG key availability before tests |

### Clean

| Target | Description |
|---|---|
| `clean-base` | Remove the base image |
| `clean-builder` | Remove the builder image |
| `clean-runtime` | Remove the runtime image |
| `clean-devcontainer` | Remove the devcontainer image |
| `clean-containers` | Remove all container images |
| `clean` | Remove all images and built wheel artifacts |

### Utilities

| Target | Description |
|---|---|
| `shell` | Open an interactive bash shell in the builder container |
| `all` | Full pipeline: build-builder → test → build-tooling → build-runtime |

## `packtly_builder_tooling` CLI

The CLI is the runtime entrypoint of the final container image. It builds, signs, and optionally uploads a Debian package.

```
packtly_builder_tooling <builddir> [options]

Options:
  --aptlyhost URL     Aptly REST API base URL (or set APTLYHOST env var)
  --dist NAME         Aptly publish distribution (e.g. trixie-apollo)
  --component NAME    Aptly component (e.g. main)
  --upload            Upload the built package to Aptly after signing
  --verbose           Enable debug logging
```

GPG signing keys are expected at:
```
/opt/keys/gpg/repo_signing.key
/opt/keys/gpg/repo_signing_private.key
/opt/keys/gpg/repo_signing_private_pass
```
## Related

- **[packtly-infra](https://github.com/packtly/packtly-infra)** — Infrastructure automation for deploying packtly: a self-hosted Debian package repository based on [aptly](https://www.aptly.info/) and [nginx](https://nginx.org/), running as a rootless Podman container managed by systemd Quadlets.

## Versioning

The release version is driven by `CHANGELOG.md` (Keep a Changelog format). The CI reads the latest `## [x.y.z]` entry and applies it as the container image label and Git tag at release time.

## Development

The repository includes a VS Code devcontainer configuration. Open the project in VS Code and select **Reopen in Container** to get a fully configured Debian build environment.

For local development without the devcontainer:

```bash
cd packtly-builder/tooling
just prepare   # Install Poetry dependencies
just pytest    # Run tests
just mypy      # Type-check
just flake8    # Lint
```
