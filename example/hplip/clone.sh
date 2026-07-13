#!/bin/bash
set -eu

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

if [ -d "$SCRIPT_DIR/hplip.v2/.git" ]; then
    git -C "$SCRIPT_DIR/hplip.v2" fetch origin
    git -C "$SCRIPT_DIR/hplip.v2" reset --hard FETCH_HEAD
else
    if [ -e "$SCRIPT_DIR/hplip.v2" ]; then
        rm -rf "$SCRIPT_DIR/hplip.v2"
    fi
    git clone https://salsa.debian.org/printing-team/hplip.v2.git "$SCRIPT_DIR/hplip.v2"
fi



