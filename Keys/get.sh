#!/bin/bash
set -euo pipefail

TOPDIR="$(git rev-parse --show-toplevel)"

PACKTLY_INFRA_DIR="$TOPDIR/../packtly-infra/ansible/generated-secrets/localhost"
SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GPG_DIR="$SOURCE_DIR/gpg"

if [[ ! -d "$PACKTLY_INFRA_DIR" ]]; then
    echo "Error: PACKTLY_INFRA_DIR not found: $PACKTLY_INFRA_DIR" >&2
    exit 1
fi

if [[ -d "$GPG_DIR" ]]; then
    rm -rf "$GPG_DIR"
fi
mkdir -p "$GPG_DIR"

# Copy files with error checking
cp -v "$PACKTLY_INFRA_DIR/public/repo_signing.key" "$GPG_DIR/repo_signing.key"
cp -v "$PACKTLY_INFRA_DIR/private/repo_signing_private.key" "$GPG_DIR/repo_signing_private.key"
cp -v "$PACKTLY_INFRA_DIR/private/repo_signing_private_pass" "$GPG_DIR/repo_signing_private_pass"

echo "Successfully copied GPG keys to $GPG_DIR"
