import gnupg
import shutil
from pathlib import Path
from datetime import datetime
from typing import NamedTuple, Optional


class Key(NamedTuple):
    name: str
    id: str
    fingerprint: str
    length: int
    type: str
    date: datetime


class Gpg:
    def __init__(self, keyring: Path) -> None:
        if not keyring.exists():
            raise FileNotFoundError(f"The file '{keyring!r}' does not exist.")
        self._keyring = keyring
        self._gnupg = gnupg.GPG(
            keyring=str(self._keyring), verbose=False, use_agent=True
        )
        self._passphrase = ""
        self._signing_fingerprint: str = ""

    def keyring(self) -> Path:
        return self._keyring

    def create_and_set_new_keyring(self, new_keyring: Path) -> None:
        if not new_keyring.is_absolute():
            keyring_directory = self._keyring.parent
            new_keyring = keyring_directory / new_keyring

        shutil.copy(str(self._keyring), str(new_keyring))
        self._keyring = new_keyring
        self._gnupg = gnupg.GPG(
            keyring=str(self._keyring), verbose=False, use_agent=True
        )

    def list_keys(self, secret: bool = False) -> list[Key]:
        keys = self._gnupg.list_keys(secret=secret)
        key_list: list[Key] = []
        for key in keys:
            key_list.append(
                Key(
                    name=key["uids"][0],
                    id=key["keyid"],
                    fingerprint=key["fingerprint"],
                    length=int(key["length"]),
                    type=key["type"],
                    date=datetime.fromtimestamp(int(key["date"])),
                )
            )
        return key_list

    def import_key(
        self, public_key: Path, private_key: Path, passphrase_file: Path
    ) -> None:
        if not public_key.exists():
            raise FileNotFoundError(f"The file '{public_key!r}' does not exist.")

        if not private_key.exists():
            raise FileNotFoundError(f"The file '{private_key!r}' does not exist.")

        if not passphrase_file.exists():
            raise FileNotFoundError(f"The file '{passphrase_file!r}' does not exist.")

        public_key_data = self._read_key_from_file(public_key)
        private_key_data = self._read_key_from_file(private_key)
        passphrase = self._read_passphrase(passphrase_file)
        self._passphrase = passphrase
        self._gnupg.import_keys(public_key_data)
        result = self._gnupg.import_keys(private_key_data, None, passphrase)
        if result.fingerprints:
            self._signing_fingerprint = result.fingerprints[0]

    def passphrase(self) -> str:
        return self._passphrase

    def signing_key(self) -> Optional[Key]:
        if not self._signing_fingerprint:
            return None
        keys = self._gnupg.list_keys(secret=True)
        for key in keys:
            if key["fingerprint"] == self._signing_fingerprint:
                return Key(
                    name=key["uids"][0],
                    id=key["keyid"],
                    fingerprint=key["fingerprint"],
                    length=int(key["length"]),
                    type=key["type"],
                    date=datetime.fromtimestamp(int(key["date"])),
                )
        return None

    def _read_passphrase(self, passphrase_file_path: Path) -> str:
        with open(passphrase_file_path, "r", encoding="utf-8") as file:
            passphrase_content = file.read().strip()
        return passphrase_content

    def _read_key_from_file(self, file_path: Path) -> str:
        with open(file_path, "r", encoding="utf-8") as file:
            key_data = file.read()
        return key_data
