#!/bin/bash
# shellcheck disable=SC2054
set -eu

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
TOPDIR="$(git rev-parse --show-toplevel)"


# Keys path — adjust to match your packtly-infra secrets location
KEYS_DIR="$TOPDIR/../packtly-infra/ansible/generated-secrets/localhost"
APTLY_CREDENTIALS_FILE="$SCRIPT_DIR/../aptly-credentials"

mkdir -p "$SCRIPT_DIR/logs"

PODMAN_COMMON=(
    --rm
    -v "$SCRIPT_DIR/..":/workspace:Z
    -v "$KEYS_DIR/public/repo_signing.key":/opt/keys/gpg/repo_signing.key:Z,ro
    -v "$KEYS_DIR/private/repo_signing_private.key":/opt/keys/gpg/repo_signing_private.key:Z,ro
    -v "$KEYS_DIR/private/repo_signing_private_pass":/opt/keys/gpg/repo_signing_private_pass:Z,ro
    -v "$APTLY_CREDENTIALS_FILE":/run/secrets/aptly-credentials:Z,ro
    -v "$SCRIPT_DIR/logs":/logs:Z
    -e APTLYHOST=http://localhost:8080
    --network=host
)

COMMON_ARGS=(
    /workspace/debhello
    --log-file /logs/build.log
    --dist trixie-apollo
    --component main
    --credentials-file /run/secrets/aptly-credentials
)

# Build
podman run "${PODMAN_COMMON[@]}" packtly-builder:latest "${COMMON_ARGS[@]}"

# Upload
podman run "${PODMAN_COMMON[@]}" packtly-builder:latest "${COMMON_ARGS[@]}" \
    --no-build \
    --upload
