#!/bin/bash
set -eu

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

if [ -d "$SCRIPT_DIR/systemd/.git" ]; then
    git -C "$SCRIPT_DIR/systemd" fetch origin
    git -C "$SCRIPT_DIR/systemd" reset --hard FETCH_HEAD
else
    if [ -e "$SCRIPT_DIR/systemd" ]; then
        rm -rf "$SCRIPT_DIR/systemd"
    fi
    git clone https://salsa.debian.org/systemd-team/systemd.git "$SCRIPT_DIR/systemd"
fi
