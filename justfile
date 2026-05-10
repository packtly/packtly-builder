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
    for cmd in podman {{ compose }}; do
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
    if [ ! -f "${HOME}/.pip/pip.conf" ]; then
        mkdir -p "${HOME}/.pip"
        printf '[global]\nbreak-system-packages = true\nindex-url = https://pypi.org/simple\n' \
            > "${HOME}/.pip/pip.conf"
        echo "Created minimal ~/.pip/pip.conf (no private registry configured)"
    fi

[private]
_build-service service: _ensure-pip-conf
    #!/usr/bin/env bash
    set -eu
    extra=""
    if [ -n "${RELEASE_VERSION:-}" ]; then
        extra="--build-arg VERSION=${RELEASE_VERSION}"
    fi
    {{ compose }} --file "{{ compose_file }}" build $extra "{{ service }}"

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
_tooling target: _ensure-pip-conf
    #!/usr/bin/env bash
    set -eu
    rm -rf {{ tooling_dir }}/dist
    extra=""
    if [ -n "${RELEASE_VERSION:-}" ]; then
        extra="-e RELEASE_VERSION=${RELEASE_VERSION}"
    fi
    {{ compose }} --file "{{ compose_file }}" run --rm $(just _keys-volume-args) $extra builder "{{ target }}"

# --- build containers ---

build-base: _require-tools
    just _build-service base

build-builder: _require-tools
    just _build-service builder

build-runtime: _require-tools
    just _build-service runtime

build-devcontainer: _require-tools
    just _build-service devcontainer

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

test-tooling: _require-tools
    just _tooling test

test-tooling-keys: _require-tools
    just _tooling test-keys

# --- Runtime helpers ---

shell: _require-tools
    #!/usr/bin/env bash
    set +e
    {{ compose }} --file "{{ compose_file }}" run --rm $(just _keys-volume-args) --entrypoint bash builder
    rc=$?
    if [ "$rc" -ne 0 ] && [ "$rc" -ne 130 ]; then
        exit "$rc"
    fi

# --- Pipeline ---

clean: _require-tools
    just clean-containers
    rm -rf {{ tooling_dir }}/dist

all: _require-tools
    just build-builder
    just test-tooling
    just build-tooling
    just build-runtime
