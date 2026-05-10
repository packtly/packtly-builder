#!/usr/bin/env python3
import semver
import sys

with open("CHANGELOG.md",encoding="utf-8") as f:
    for line in f:
        if not line.startswith("## ["):
            continue

        raw = line.split("[", 1)[1].split("]", 1)[0]

        if raw.lower() == "unreleased":
            continue

        raw = raw.lstrip("v")

        try:
            v = semver.VersionInfo.parse(raw)
            print(v)
            sys.exit(0)
        except ValueError:
            continue

sys.exit("No valid semver version found in CHANGELOG.md")
