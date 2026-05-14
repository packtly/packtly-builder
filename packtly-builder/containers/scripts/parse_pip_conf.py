#!/usr/bin/env python3

import argparse
import configparser
import sys
from urllib.parse import urlparse

parser = argparse.ArgumentParser(
    description="Parse a pip.conf file and interpret its contents."
)
parser.add_argument(
    "-i",
    "--index",
    type=int,
    required=True,
    help="Index of the extra-index-url to use (0-based)."
)
parser.add_argument(
    "pip_conf",
    type=str,
    help="Path to pip.conf file"
)
args = parser.parse_args()

config = configparser.ConfigParser(interpolation=None)
config.read(args.pip_conf)

extra_index_urls = config["global"].get("extra-index-url", "").splitlines()
extra_index_urls = [url.strip() for url in extra_index_urls if url.strip()]

if not extra_index_urls:
    print("No extra-index-url entries found in pip.conf", file=sys.stderr)
    sys.exit(1)

if args.index < 0 or args.index >= len(extra_index_urls):
    print(
        f"Invalid index: {args.index}. Found {len(extra_index_urls)} entries.", file=sys.stderr)
    sys.exit(1)

url = extra_index_urls[args.index]
parsed = urlparse(url)

# Extract username from the URL, decode %40 to @
pip_user = (parsed.username or "").replace("%40", "@")
pip_pass = parsed.password or ""

print(f"PIP_USERNAME={pip_user}")
print(f"PIP_PASSWORD={pip_pass}")
print(f"PIP_URL={url}")
