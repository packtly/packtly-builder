import sys
from pathlib import Path

import pytest

from packtly_builder_tooling import cli

TEST_CREDENTIALS_FILE = Path(__file__).parent / "test_credentials.txt"


def test_resolve_aptly_credentials_from_test_file() -> None:
    username, password = cli.resolve_aptly_credentials(TEST_CREDENTIALS_FILE)

    assert username == "user"
    assert password == "secret"


def test_resolve_aptly_credentials_from_file(tmp_path: Path) -> None:
    credentials_file = tmp_path / "aptly-credentials.txt"
    credentials_file.write_text("username=admin\npassword=secret\n", encoding="utf-8")

    assert cli.resolve_aptly_credentials(credentials_file) == ("admin", "secret")


def test_resolve_aptly_credentials_ignores_comments(tmp_path: Path) -> None:
    credentials_file = tmp_path / "aptly-credentials.txt"
    credentials_file.write_text(
        "# aptly auth\nusername=admin\n\npassword=secret\n",
        encoding="utf-8",
    )

    assert cli.resolve_aptly_credentials(credentials_file) == ("admin", "secret")


def test_resolve_aptly_credentials_requires_both_entries(tmp_path: Path) -> None:
    credentials_file = tmp_path / "aptly-credentials.txt"
    credentials_file.write_text("username=admin\n", encoding="utf-8")

    with pytest.raises(ValueError, match="Missing username or password"):
        cli.resolve_aptly_credentials(credentials_file)


def test_parse_args_accepts_credentials_file(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "packtly_builder_tooling",
            "/tmp/build",
            "--credentials-file",
            "/tmp/secret",
        ],
    )

    arguments = cli._parse_args()

    assert arguments.builddir == Path("/tmp/build")
    assert arguments.credentials_file == Path("/tmp/secret")


def test_parse_args_rejects_removed_password_flag(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        ["packtly_builder_tooling", "/tmp/build", "--password", "secret"],
    )

    with pytest.raises(SystemExit):
        cli._parse_args()


def test_parse_args_rejects_removed_password_file_flag(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        ["packtly_builder_tooling", "/tmp/build", "--password-file", "/tmp/secret"],
    )

    with pytest.raises(SystemExit):
        cli._parse_args()


def test_parse_args_force_upload_default_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        ["packtly_builder_tooling", "/tmp/build"],
    )

    arguments = cli._parse_args()

    assert arguments.force_upload is False


def test_parse_args_force_upload_enabled_when_flag_present(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        ["packtly_builder_tooling", "/tmp/build", "--force_upload"],
    )

    arguments = cli._parse_args()

    assert arguments.force_upload is True
