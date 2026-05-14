import os
from collections.abc import Iterator
from pathlib import Path
import pytest
from unittest.mock import MagicMock, patch
from packtly_builder_tooling.parts.apt import AptManager, KEYRINGS_DIR, SOURCES_DIR

REPO_URI = "http://localhost:8080"
REPO_DIST = "trixie-apollo"
REPO_COMP = "main"
KEY_FILE = "/opt/keys/gpg/repo_signing.key"
KEY_NAME = "trixie-apollo"
REPO_SOURCE_FILE = os.path.join(SOURCES_DIR, f"{REPO_DIST}.sources")

# only once for a test process


@pytest.fixture(scope="session")
def AptObj() -> AptManager:
    return AptManager()


@pytest.fixture(scope="session")
def installed_keyring(AptObj: AptManager) -> Path:
    armored_key = open(KEY_FILE, "rb").read()
    return AptObj.add_key(armored_key, KEY_NAME)


@pytest.fixture(scope="module", autouse=True)
def cleanup_repo_sources_file() -> Iterator[None]:
    if os.path.exists(REPO_SOURCE_FILE):
        os.remove(REPO_SOURCE_FILE)
    try:
        yield
    finally:
        if os.path.exists(REPO_SOURCE_FILE):
            os.remove(REPO_SOURCE_FILE)


# ---------------------------------------------------------------------------
# add_key
# ---------------------------------------------------------------------------


def test_add_key_writes_gpg_file(installed_keyring: Path) -> None:
    assert installed_keyring.is_file()
    assert installed_keyring.suffix == ".gpg"


def test_add_key_path_is_in_keyrings_dir(installed_keyring: Path) -> None:
    assert KEYRINGS_DIR in installed_keyring.parents


def test_add_key_file_is_not_armored(installed_keyring: Path) -> None:
    with open(installed_keyring, "rb") as f:
        data = f.read(10)
    assert not data.lstrip().startswith(
        b"-----BEGIN"
    ), "Keyring file should be binary (dearmored), not ASCII-armored"


def test_add_key_binary_input_also_accepted(AptObj: AptManager) -> None:
    """Passing already-dearmored bytes must not raise and must write the file."""
    binary_key = open(f"{KEYRINGS_DIR}/{KEY_NAME}.gpg", "rb").read()
    path = AptObj.add_key(binary_key, "trixie-apollo-binary")
    assert os.path.isfile(path)
    os.remove(path)


# ---------------------------------------------------------------------------
# add_repo
# ---------------------------------------------------------------------------


def test_add_repo_creates_sources_file(
    AptObj: AptManager, installed_keyring: Path
) -> None:
    source_file = os.path.join(SOURCES_DIR, f"{REPO_DIST}.sources")
    # Remove any pre-existing file so the creation path is exercised.
    if os.path.exists(source_file):
        os.remove(source_file)
    AptObj.add_repo(REPO_URI, REPO_DIST, REPO_COMP, keyring=installed_keyring)
    assert os.path.isfile(source_file)


def test_add_repo_sources_file_has_correct_content(installed_keyring: Path) -> None:
    source_file = os.path.join(SOURCES_DIR, f"{REPO_DIST}.sources")
    content = open(source_file).read()
    assert f"URIs: {REPO_URI}" in content
    assert f"Suites: {REPO_DIST}" in content
    assert f"Components: {REPO_COMP}" in content
    assert f"Signed-By: {installed_keyring}" in content
    assert "Types: deb" in content


def test_add_repo_is_idempotent(AptObj: AptManager, installed_keyring: Path) -> None:
    """Calling add_repo twice must not duplicate the entry."""
    source_file = os.path.join(SOURCES_DIR, f"{REPO_DIST}.sources")
    AptObj.add_repo(REPO_URI, REPO_DIST, REPO_COMP, keyring=installed_keyring)
    content_before = open(source_file).read()
    AptObj.add_repo(REPO_URI, REPO_DIST, REPO_COMP, keyring=installed_keyring)
    content_after = open(source_file).read()
    assert content_before == content_after


def test_add_repo_without_keyring(AptObj: AptManager) -> None:
    dist = "trixie-apollo-nokey"
    source_file = os.path.join(SOURCES_DIR, f"{dist}.sources")
    try:
        AptObj.add_repo(REPO_URI, dist, REPO_COMP)
        assert os.path.isfile(source_file)
        content = open(source_file).read()
        assert "Signed-By" not in content
    finally:
        if os.path.exists(source_file):
            os.remove(source_file)


def test_add_repo_components_as_list(
    AptObj: AptManager, installed_keyring: Path
) -> None:
    dist = "trixie-apollo-list"
    source_file = os.path.join(SOURCES_DIR, f"{dist}.sources")
    try:
        AptObj.add_repo(REPO_URI, dist, ["main", "contrib"], keyring=installed_keyring)
        content = open(source_file).read()
        assert "main contrib" in content
    finally:
        if os.path.exists(source_file):
            os.remove(source_file)


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def apt_manager_mock() -> Iterator[AptManager]:
    with (
        patch("packtly_builder_tooling.parts.apt.apt.Cache") as MockCache,
        patch("packtly_builder_tooling.parts.apt.get_distro"),
    ):
        manager = AptManager()
        manager.cache = MockCache.return_value
        yield manager


# ---------------------------------------------------------------------------
# update
# ---------------------------------------------------------------------------


def test_apt_cache_update_success(apt_manager_mock: AptManager) -> None:
    apt_manager_mock.cache.update.return_value = True
    assert apt_manager_mock.update() is True
    apt_manager_mock.cache.update.assert_called_once()


def test_apt_cache_update_failure(apt_manager_mock: AptManager) -> None:
    apt_manager_mock.cache.update.side_effect = Exception("update failed")
    assert apt_manager_mock.update() is False


# ---------------------------------------------------------------------------
# install_package
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def setup_package(manager: AptManager, pkg: MagicMock) -> None:
    manager.cache.__contains__.return_value = True
    manager.cache.__getitem__.return_value = pkg


def make_pkg(uris_per_version: list[list[str]]) -> MagicMock:
    pkg = MagicMock()
    pkg.versions = []

    for uris in uris_per_version:
        v = MagicMock()
        v.uris = uris
        pkg.versions.append(v)

    return pkg


# ---------------------------------------------------------------------------
# tests
# ---------------------------------------------------------------------------


def test_install_package_not_in_cache(apt_manager_mock: AptManager) -> None:
    apt_manager_mock.cache.__contains__.return_value = False

    assert apt_manager_mock.install_package("nonexistent") is False
    apt_manager_mock.cache.open.assert_called_once()


def test_install_package_success(apt_manager_mock: AptManager) -> None:
    pkg = MagicMock()
    setup_package(apt_manager_mock, pkg)

    assert apt_manager_mock.install_package("htop") is True

    pkg.mark_install.assert_called_once()
    apt_manager_mock.cache.commit.assert_called_once()


def test_install_package_commit_error(apt_manager_mock: AptManager) -> None:
    pkg = MagicMock()
    setup_package(apt_manager_mock, pkg)
    apt_manager_mock.cache.commit.side_effect = Exception("fail")

    assert apt_manager_mock.install_package("htop") is False


# ---------------------------------------------------------------------------
# source_host behavior (parametrized)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "versions, source_host, expected",
    [
        # match in first version
        ([["http://my-apt.example.com/pkg.deb"]], "my-apt.example.com", True),
        # no match
        ([["http://deb.debian.org/pkg.deb"]], "my-apt.example.com", False),
        # match in later version
        (
            [
                ["http://deb.debian.org/pkg.deb"],
                ["http://my-apt.example.com/pkg.deb"],
            ],
            "my-apt.example.com",
            True,
        ),
    ],
)
def test_install_package_source_host(
    apt_manager_mock: AptManager,
    versions: list[list[str]],
    source_host: str,
    expected: bool,
) -> None:
    pkg = make_pkg(versions)
    setup_package(apt_manager_mock, pkg)

    result = apt_manager_mock.install_package("htop", source_host=source_host)

    assert result is expected
