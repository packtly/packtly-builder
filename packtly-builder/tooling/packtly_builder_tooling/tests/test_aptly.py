from types import SimpleNamespace
from unittest.mock import MagicMock

from packtly_builder_tooling.parts.aptly import Aptly


def make_aptly_with_mocks() -> tuple[Aptly, MagicMock, MagicMock, MagicMock]:
    aptly = Aptly.__new__(Aptly)
    aptly.host = "http://localhost:8080"

    files_api = MagicMock()
    repos_api = MagicMock()
    publish_api = MagicMock()

    aptly.client = MagicMock(files=files_api, repos=repos_api, publish=publish_api)
    return aptly, files_api, repos_api, publish_api


def make_endpoint() -> SimpleNamespace:
    return SimpleNamespace(
        distribution="trixie-apollo",
        sources=[{"Component": "main", "Name": "repo-main"}],
        prefix=".",
    )


def test_upload_marks_changed_when_new_package_added() -> None:
    aptly, files_api, repos_api, publish_api = make_aptly_with_mocks()
    endpoint = make_endpoint()

    files_api.upload.return_value = True
    repos_api.search_packages.return_value = []
    repos_api.add_uploaded_file.return_value = SimpleNamespace(
        failed_files=[],
        report={"Added": ["Pdebhello_1.0.0_amd64"]},
    )

    result = aptly.upload_deb_files(
        endpoint=endpoint,
        name="upload-dir",
        files=["/tmp/debhello_1.0.0_amd64.deb"],
        keyid="ABC123",
        passphrase="secret",
        component="main",
    )

    assert result is True
    publish_api.update.assert_called_once()
