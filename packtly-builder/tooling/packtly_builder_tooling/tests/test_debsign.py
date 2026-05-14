import pytest
import os
import distro
from pathlib import Path

# from unittest.mock import MagicMock, patch
from conftest import ExtraArgs
from packtly_builder_tooling.parts.apt import AptManager
from packtly_builder_tooling.parts.debuild import Debuild
from packtly_builder_tooling.parts.gpg import Gpg
from packtly_builder_tooling.parts.debsign import Debsign


@pytest.fixture
def debuild_obj(testargs: ExtraArgs) -> Debuild:
    return Debuild(Path(os.path.join(os.getcwd(), testargs.dpkgbuild)))


@pytest.fixture
def apt_manager() -> AptManager:
    apt_manager = AptManager()
    apt_manager.update()
    return apt_manager


@pytest.fixture
def GpgObj() -> Gpg:
    if distro.id().lower() == "ubuntu":
        basering = Path("/usr/share/keyrings/ubuntu-archive-keyring.gpg")
    elif distro.id().lower() == "debian":
        basering = Path("/usr/share/keyrings/debian-archive-keyring.gpg")
    else:
        raise RuntimeError("Unkown Platfrom")

    tmp_signing_keyring = Path("/tmp/signing-keyring.gpg")
    if tmp_signing_keyring.exists():
        tmp_signing_keyring.unlink()

    gpg = Gpg(basering)
    gpg.create_and_set_new_keyring(tmp_signing_keyring)
    gpg.import_key(
        Path("/opt/keys/gpg/repo_signing.key"),
        Path("/opt/keys/gpg/repo_signing_private.key"),
        Path("/opt/keys/gpg/repo_signing_private_pass"),
    )
    return gpg


def test_debsign(debuild_obj: Debuild, GpgObj: Gpg, apt_manager: AptManager) -> None:
    try:
        changes_file = debuild_obj.deb_changes_file()
    except FileNotFoundError:
        for depend in debuild_obj.build_dependencies():
            assert apt_manager.install_package(depend)
        debuild_obj.build()
        changes_file = debuild_obj.deb_changes_file()

    tmp_signing_keyring = Path(GpgObj.keyring())
    passphrase = GpgObj.passphrase()

    result = GpgObj.signing_key()
    assert result is not None
    assert result.fingerprint is not None
    assert result.type == "sec"

    DebsignObj = Debsign(
        keyring=tmp_signing_keyring,
        passphrase=passphrase,
        keyid=result.fingerprint,
    )

    DebsignObj.sign_deb_files(changes_file=changes_file)

    assert DebsignObj.keyring() == tmp_signing_keyring
    assert DebsignObj.passphrase() == passphrase
    assert DebsignObj.keyid() == result.fingerprint
