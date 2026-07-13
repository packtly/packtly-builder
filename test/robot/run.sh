#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Install robotframework if not already installed
if ! pipx list --short | grep -qx 'robotframework'; then
    pipx install \
        --pip-args="-r ${ROOT}/requirements.txt" \
        robotframework
fi

# Tests ausführen
robot \
    --outputdir "${ROOT}/results" \
    "${ROOT}/suites"

