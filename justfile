compose := "podman-compose"
compose_file := "packtly-builder/podman-compose.yml"
tooling_dir := "packtly-builder/tooling"

default: list

list:
    @just --list

[private]
_keys-volume-args:
    #!/usr/bin/env bash
    mkdir -p ../Keys/gpg
    printf '%s\n' \
        -v ../Keys/gpg:/opt/keys/gpg:Z

[private]
_require-tools:
    #!/usr/bin/env bash
    set -eu
    for cmd in podman {{ compose }} yq; do
        command -v "$cmd" >/dev/null 2>&1 || {
            echo "Error: '$cmd' not found in PATH"
            exit 1
        }
    done
    test -f "{{ compose_file }}" || {
        echo "Error: Compose file '{{ compose_file }}' not found"
        exit 1
    }

[private]
_ensure-pip-conf:
    #!/usr/bin/env bash
    set -eu
    if [ ! -f "${HOME}/.config/pip/pip.conf" ]; then
        mkdir -p "${HOME}/.config/pip"
        printf '[global]\nbreak-system-packages = true\nindex-url = https://pypi.org/simple\n' \
            > "${HOME}/.config/pip/pip.conf"
        echo "Created minimal ~/.config/pip/pip.conf (no private registry configured)"
    fi

[private]
_build-service service arch="amd64": _ensure-pip-conf
    #!/usr/bin/env bash
    set -eu

    case "{{ arch }}" in
        amd64) platform="linux/amd64" ;;
        arm64) platform="linux/arm64" ;;
        *) echo "Unsupported arch: {{ arch }}" >&2; exit 1 ;;
    esac

    echo "Building {{ service }} for ${platform}"

    export PLATFORM="${platform}"
    export ARCH="{{ arch }}"

    extra=""
    if [ -n "${RELEASE_VERSION:-}" ]; then
        extra="--build-arg VERSION=${RELEASE_VERSION}"
    fi

    {{ compose }} \
        --file "{{ compose_file }}" \
        build $extra "{{ service }}"

    image="$(yq -r '.services["{{ service }}"].image // ""' "{{ compose_file }}")"
    if [ -z "$image" ] || [ "$image" = "null" ]; then
        echo "Error: No image defined for service '{{ service }}' in {{ compose_file }}" >&2
        exit 1
    fi
    podman tag "$image" "${image}-{{ arch }}"
    podman rmi "$image"

[private]
_assemble-manifest service:
    #!/usr/bin/env bash
    set -eu

    base_image="$(yq -r '.services["{{ service }}"].image' "{{ compose_file }}")"
    base_name="${base_image%%:*}"
    manifest="${base_name}:latest"

    echo "Assembling manifest: $manifest"

    # Remove existing manifest list or regular image before creating a fresh manifest.
    podman manifest rm "$manifest" 2>/dev/null || true
    podman rmi "$manifest" 2>/dev/null || true
    podman manifest create "$manifest"

    for arch in amd64 arm64; do
        podman manifest add "$manifest" "${base_name}:latest-${arch}"
    done


[private]
_remove-service-image service:
    #!/usr/bin/env bash
    set -eu
    command -v yq >/dev/null 2>&1 || { echo "Error: 'yq' not found in PATH"; exit 1; }
    image="$(yq -r '.services["{{ service }}"].image // empty' "{{ compose_file }}")"

    if [ -z "$image" ]; then
        echo "No image defined for {{ service }}, skipping."
        exit 0
    fi

    if podman image exists "$image"; then
        echo "Removing image: $image"
        podman rmi "$image" || echo "Warning: Could not remove $image."
    else
        echo "Image $image does not exist, skipping."
    fi

[private]
_tooling target arch="amd64": _ensure-pip-conf
    #!/usr/bin/env bash
    set -eu
    rm -rf {{ tooling_dir }}/dist

    case "{{ arch }}" in
        amd64) platform="linux/amd64" ;;
        arm64) platform="linux/arm64" ;;
        *) echo "Unsupported arch: {{ arch }}" >&2; exit 1 ;;
    esac

    echo "Running {{ target}} for ${platform}"

    export PLATFORM="${platform}"

    extra=""
    if [ -n "${RELEASE_VERSION:-}" ]; then
        extra="-e RELEASE_VERSION=${RELEASE_VERSION}"
    fi
    {{ compose }} \
        --file "{{ compose_file }}"\
        run --rm \
        $(just _keys-volume-args)\
        $extra \
        builder "{{ target }}"

# --- build containers ---

build-base arch="amd64": _require-tools
    just _build-service base {{ arch }}

build-builder arch="amd64": _require-tools
    just _build-service builder {{ arch }}

build-runtime arch="amd64": _require-tools
    just _build-service runtime {{ arch }}

build-devcontainer arch="amd64": _require-tools
    just compose_file=packtly-builder/podman-compose.devcontainer.yml _build-service devcontainer {{ arch }}

# --- multi arch builds ---

build-builder-multiarch: _require-tools
    #!/usr/bin/env bash
    set -eu
    for arch in amd64 arm64; do
        just build-builder "$arch"
    done
    just _assemble-manifest builder

build-runtime-multiarch: _require-tools
    #!/usr/bin/env bash
    set -eu
    for arch in amd64 arm64; do
        just build-runtime "$arch"
    done
    just _assemble-manifest runtime

# --- clean containers ---

clean-base: _require-tools
    just _remove-service-image base

clean-builder: _require-tools
    just _remove-service-image builder

clean-runtime: _require-tools
    just _remove-service-image runtime

clean-devcontainer: _require-tools
    just _remove-service-image devcontainer

clean-containers: _require-tools
    just clean-base
    just clean-builder
    just clean-runtime
    just clean-devcontainer

# --- Tooling ---

build-tooling: _require-tools
    just _tooling build

test-tooling arch="amd64": _require-tools
    just _tooling test {{ arch }}

test-tooling-keys arch="amd64": _require-tools
    just _tooling test-keys {{ arch }}

# --- Runtime helpers ---

shell: _require-tools
    #!/usr/bin/env bash
    set +e
    {{ compose }} --file "{{ compose_file }}" run --rm $(just _keys-volume-args) --entrypoint bash builder
    rc=$?
    if [ "$rc" -ne 0 ] && [ "$rc" -ne 130 ]; then
        exit "$rc"
    fi

# --- Robot Framework linting ---

# Install robocop linter (own pipx venv, independent of the RF test runner)
install-robocop:
    #!/usr/bin/env bash
    set -euo pipefail
    if ! pipx list --short | grep -q 'robotframework-robocop'; then
        pipx install robotframework-robocop
    fi

# Lint Robot Framework files with robocop
lint-robot: install-robocop
    robocop check test/robot

# --- Pipeline ---

clean: _require-tools
    just clean-containers
    rm -rf {{ tooling_dir }}/dist

all: _require-tools
    just build-builder
    just test-tooling
    just build-tooling
    just build-runtime-multiarch
