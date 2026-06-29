#!/bin/bash
# shellcheck disable=SC2054
set -eu

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
TOPDIR="$(git rev-parse --show-toplevel)"

# Keys path — adjust to match your packtly-infra secrets location
KEYS_DIR="$TOPDIR/../packtly-infra/ansible/generated-secrets/localhost"
APTLY_CREDENTIALS_FILE="$SCRIPT_DIR/../aptly-credentials"

CONTAINER_IMAGE="ghcr.io/packtly/packtly-builder:latest"
#CONTAINER_IMAGE="packtly-builder:latest"

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

run_build() {
    podman run \
        "${PODMAN_COMMON[@]}" \
        "$CONTAINER_IMAGE" \
        "${COMMON_ARGS[@]}"
}

run_upload() {
    podman run \
        "${PODMAN_COMMON[@]}" \
        "$CONTAINER_IMAGE" \
        "${COMMON_ARGS[@]}" \
        --no-build \
        --upload
}

run_force_upload() {
    podman run \
        "${PODMAN_COMMON[@]}" \
        "$CONTAINER_IMAGE" \
        "${COMMON_ARGS[@]}" \
        --no-build \
        --upload \
        --force-upload
}

main() {

    mkdir -p "$SCRIPT_DIR/logs"
    ACTION="${1:-all}"
    ARCH="${2:-amd64}"

    PODMAN_COMMON+=(--platform "linux/${ARCH}")

    if [[ "$ARCH" == "amd64" ]]; then
        COMMON_ARGS+=(--build-mode full)
    fi

    case "$ACTION" in
    build)
        run_build
        ;;
    upload)
        run_upload
        ;;
    force-upload)
        run_force_upload
        ;;
    all-force-upload)
        run_build
        run_force_upload
        ;;
    all)
        run_build
        run_upload
        ;;
    *)
        echo "Usage: $0 {build|upload|force-upload|all-force-upload|all}" >&2
        exit 2
        ;;
    esac
}

main "$@"
