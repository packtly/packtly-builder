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

# --tmpfs /run:exec,mode=0755         replace /run with private tmpfs, bypasses host MS_SHARED propagation (fixes test-mount-util)
# --cap-add SYS_ADMIN                 allow mount/unmount syscalls (required for --tmpfs and build steps)
# --cap-add SYS_PTRACE                allow process introspection (required by systemd test-namespace)
# --security-opt seccomp=unconfined   allow all syscalls including newer ones like mount_setattr
# --security-opt unmask=all           unmask /proc/acpi, /sys/firmware etc. that podman masks by default


PODMAN_COMMON=(
    --rm
    -v "$SCRIPT_DIR":/workspace:Z
    -v "$KEYS_DIR/public/repo_signing.key":/opt/keys/gpg/repo_signing.key:Z,ro
    -v "$KEYS_DIR/private/repo_signing_private.key":/opt/keys/gpg/repo_signing_private.key:Z,ro
    -v "$KEYS_DIR/private/repo_signing_private_pass":/opt/keys/gpg/repo_signing_private_pass:Z,ro
    -v "$APTLY_CREDENTIALS_FILE":/run/secrets/aptly-credentials:Z,ro
    -v "$SCRIPT_DIR/logs":/logs:Z
    -e APTLYHOST=http://localhost:8080
    --tmpfs /run:exec,mode=0755
    --cap-add SYS_ADMIN
    --cap-add SYS_PTRACE
    --security-opt seccomp=unconfined
    --security-opt unmask=all
    --network=host
)

COMMON_ARGS=(
    /workspace/systemd
    --log-file /logs/build.log
    --dist trixie-apollo
    --component main
    --credentials-file /run/secrets/aptly-credentials
    --build-mode full
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
        echo "Usage: $0 {build|upload|force-upload|all|all-force-upload}" >&2
        exit 2
        ;;
    esac
}

main "$@"
