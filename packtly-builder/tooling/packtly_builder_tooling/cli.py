#!/usr/bin/env python3

import argparse
import os
import distro
import logging
from typing import List, Tuple, Optional
from pathlib import Path
from aptly_api.parts.publish import PublishEndpoint
from packtly_builder_tooling.logging_setup import setup_logger, set_verbosity
from packtly_builder_tooling.parts.debuild import Debuild
from packtly_builder_tooling.parts.debsign import Debsign
from packtly_builder_tooling.parts.gpg import Gpg
from packtly_builder_tooling.parts.aptly import Aptly
from packtly_builder_tooling.parts.apt import AptManager

logger = setup_logger(__name__)

SIGNING_KEYRING = Path("/tmp/signing-keyring.gpg")
PASSPHRASE_FILE = Path("/opt/keys/gpg/repo_signing_private_pass")
PUBLIC_KEY = Path("/opt/keys/gpg/repo_signing.key")
PRIVATE_KEY = Path("/opt/keys/gpg/repo_signing_private.key")


def create_signing_keyring() -> Gpg:

    if distro.id().lower() == "ubuntu":
        keyring = Path("/usr/share/keyrings/ubuntu-archive-keyring.gpg")
    elif distro.id().lower() == "debian":
        keyring = Path("/usr/share/keyrings/debian-archive-keyring.gpg")
    else:
        raise LookupError("Unknown Platform")

    if SIGNING_KEYRING.exists():
        SIGNING_KEYRING.unlink()

    gpg = Gpg(keyring)
    gpg.create_and_set_new_keyring(SIGNING_KEYRING)
    gpg.import_key(PUBLIC_KEY, PRIVATE_KEY, PASSPHRASE_FILE)
    return gpg


def append_basedir(files_list: List[str], base_dir: str) -> List[str]:
    return [os.path.join(base_dir, element) for element in files_list]


def establish_aptly_connection(
    aptlyhost: str, dist: str, component: str
) -> Tuple[Optional[Aptly], Optional[PublishEndpoint]]:
    aptlyclient = None
    endpoint = None
    try:
        aptlyclient = Aptly(aptlyhost)
        if not dist or not component:
            raise ValueError("Invalid dist or component name")
        endpoint = aptlyclient.get_publish_endpoint(dist, component)
        aptlyclient.log_publish_endpoints()
        aptlyclient.log_repos()
    except Exception:
        logger.error("No aptly server found at %s", aptlyhost)
    return aptlyclient, endpoint


def _main(arguments: argparse.Namespace) -> None:
    builddir = arguments.builddir
    if not builddir:
        raise ValueError("No build directory is passed")
    verbosity = logging.DEBUG if arguments.verbose else logging.INFO
    set_verbosity(verbosity)

    if arguments.log_file:
        file_handler = logging.FileHandler(arguments.log_file)
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s: %(message)s")
        )
        logging.getLogger().addHandler(file_handler)

    aptlyhost = arguments.aptlyhost or os.environ.get("APTLYHOST")
    dist = arguments.dist
    component = arguments.component

    # Initialize aptly client
    aptlyclient = None
    endpoint = None
    if aptlyhost:
        aptlyclient, endpoint = establish_aptly_connection(aptlyhost, dist, component)

    # Setup GPG and build
    gpg = create_signing_keyring()
    keyid = gpg.signing_key()

    dbuild = Debuild(Path(builddir))

    aptmanager = AptManager()
    if aptlyhost and endpoint:
        installed_keyring = aptmanager.add_key(PUBLIC_KEY.read_bytes(), "aptly-keyring")
        components = [s["Component"] for s in endpoint.sources]
        aptmanager.add_repo(aptlyhost, dist, components, keyring=installed_keyring)
    if aptmanager.update():
        logger.info("Apt cache updated successfully.")
    dbuild.install_build_dependencies()

    dbuild.build()
    logger.info("Changes file: %s", dbuild.deb_changes_file())
    logger.info("Architecture: %s", dbuild.deb_changes_arch())

    # Sign if key found
    if keyid:
        logger.info("KeyId to sign is %s", keyid.fingerprint)
        debsign = Debsign(
            SIGNING_KEYRING,
            gpg.passphrase(),
            keyid.fingerprint,
        )
        debsign.sign_deb_files(dbuild.deb_changes_file())

    # Upload if all conditions met
    files = append_basedir(dbuild.deb_changes_files(), str(dbuild.outdir()))
    logger.info("Outdir: %s", dbuild.outdir())
    logger.info("Name: %s", dbuild.deb_changes_name())

    to_upload = (
        arguments.upload
        and aptlyclient is not None
        and endpoint is not None
        and keyid is not None
    )
    if to_upload:
        assert aptlyclient is not None
        assert keyid is not None
        aptlyclient.upload_deb_files(
            endpoint,
            dbuild.deb_changes_name(),
            files,
            keyid.fingerprint,
            gpg.passphrase(),
            component,
        )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build, sign and optionally publish Debian packages."
    )

    parser.add_argument(
        "builddir",
        help="Path to Debian build directory",
        type=Path,
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Show verbose output",
    )
    parser.add_argument(
        "--aptlyhost",
        help="Specify the aptly package server host",
        type=str,
        default=None,
    )
    parser.add_argument(
        "--dist",
        help="Specify the distribution to publish",
        type=str,
        default=None,
    )
    parser.add_argument(
        "--component",
        help="Specify the component to publish",
        type=str,
        default=None,
    )
    parser.add_argument(
        "--upload",
        action="store_true",
        help="Upload to aptly server",
    )
    parser.add_argument(
        "--log-file",
        help="Write log output to this file in addition to stdout/stderr",
        type=Path,
        default=None,
    )
    return parser.parse_args()


def main() -> None:
    arguments = _parse_args()
    _main(arguments)


if __name__ == "__main__":
    main()
