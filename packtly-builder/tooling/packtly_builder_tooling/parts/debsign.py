import subprocess
import shutil
from pathlib import Path


class Debsign:
    def __init__(self, keyring: Path, passphrase: str, keyid: str):
        debsign_executable = shutil.which("debsign")
        gpg_executable = shutil.which("gpg")

        if debsign_executable is None:
            raise FileNotFoundError("debsign executable not found")

        if gpg_executable is None:
            raise FileNotFoundError("gpg executable not found")

        self._debsign = debsign_executable
        self._gpg = gpg_executable

        self._keyring = keyring
        self._passphrase = passphrase
        self._keyid = keyid

    def keyring(self) -> Path:
        return self._keyring

    def passphrase(self) -> str:
        return self._passphrase

    def keyid(self) -> str:
        return self._keyid

    def sign_deb_files(self, changes_file: Path) -> None:
        # Pass passphrase via stdin (fd 0) to avoid exposure in process list.
        gpg_cmd = (
            f"{self._gpg} --no-tty --no-default-keyring"
            f" --keyring {self._keyring}"
            f" --passphrase-fd 0"
        )
        command = [
            self._debsign,
            "-p",
            gpg_cmd,
            "--re-sign",
            "--debs-dir",
            str(changes_file.parent),
            "-k",
            self._keyid,
            str(changes_file),
        ]

        subprocess.run(
            command,
            check=True,
            shell=False,
            input=self._passphrase,
            text=True,
        )
