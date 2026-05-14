import pytest
import os
from pathlib import Path
from parts.gpg import Gpg, Key
import distro


@pytest.fixture
def GpgObj() -> Gpg:
    if distro.id().lower() == "ubuntu":
        keyring = Path("/usr/share/keyrings/ubuntu-archive-keyring.gpg")
    elif distro.id().lower() == "debian":
        keyring = Path("/usr/share/keyrings/debian-archive-keyring.gpg")
    else:
        raise RuntimeError("Unkown Platfrom")

    return Gpg(keyring)


def test_create_gpg(GpgObj: Gpg) -> None:
    assert os.path.exists(GpgObj.keyring())


def test_list_keys(GpgObj: Gpg) -> None:
    keys = GpgObj.list_keys()
    assert len(keys) != 0


def test_create_and_set_new_keyring(GpgObj: Gpg) -> None:
    GpgObj.create_and_set_new_keyring(Path("ubuntu-embtom-keyring.gpg"))
    assert os.path.exists(GpgObj.keyring())


def test_import_key(GpgObj: Gpg) -> None:
    os.remove("/usr/share/keyrings/ubuntu-embtom-keyring.gpg")
    GpgObj.create_and_set_new_keyring(Path("ubuntu-embtom-keyring.gpg"))
    GpgObj.import_key(
        Path("/opt/keys/gpg/repo_signing.key"),
        Path("/opt/keys/gpg/repo_signing_private.key"),
        Path("/opt/keys/gpg/repo_signing_private_pass"),
    )

    keys = GpgObj.list_keys()
    for key in keys:
        print(f"Key Name {key.name}")
        print(f"Key Id {key.id}")
        print(f"Key Fingerprint {key.fingerprint}")
        print(f"Key Length {key.length}")
        print(f"Key type {key.type}")
        print(f"Key date {key.date}")

    keys = GpgObj.list_keys(secret=True)

    def condition(x: Key) -> bool:
        return x.type == "sec"

    found = list(filter(condition, keys))
    assert len(found) == 1

    # keys.find()
    for key in found:
        print(f"Key Name {key.name}")
        print(f"Key Id {key.id}")
        print(f"Key Fingerprint {key.fingerprint}")
        print(f"Key Length {key.length}")
        print(f"Key type {key.type}")
        print(f"Key date {key.date}")

    assert True


def test_signing_key(GpgObj: Gpg) -> None:
    tmp_keyring = Path("/tmp/signing-key-test.gpg")
    if tmp_keyring.exists():
        tmp_keyring.unlink()

    GpgObj.create_and_set_new_keyring(tmp_keyring)
    GpgObj.import_key(
        Path("/opt/keys/gpg/repo_signing.key"),
        Path("/opt/keys/gpg/repo_signing_private.key"),
        Path("/opt/keys/gpg/repo_signing_private_pass"),
    )

    key = GpgObj.signing_key()

    assert key is not None
    assert key.type == "sec"
    assert key.fingerprint != ""

    secret_keys = GpgObj.list_keys(secret=True)
    secret_fingerprints = [k.fingerprint for k in secret_keys if k.type == "sec"]
    assert key.fingerprint in secret_fingerprints
