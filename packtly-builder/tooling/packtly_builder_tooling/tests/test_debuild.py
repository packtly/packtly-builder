import pytest
import os
from pathlib import Path
import time

# from unittest.mock import MagicMock, patch
from conftest import ExtraArgs
from packtly_builder_tooling.parts.debuild import Debuild
from packtly_builder_tooling.parts.apt import AptManager
from packtly_builder_tooling.parts.hostarch import get_architecture


@pytest.fixture
def debuild_obj(testargs: ExtraArgs) -> Debuild:
    return Debuild(Path(os.path.join(os.getcwd(), testargs.dpkgbuild)))


@pytest.fixture
def apt_manager() -> AptManager:
    apt_manager = AptManager()
    apt_manager.update()
    return apt_manager


def test_deb_control_file(debuild_obj: Debuild) -> None:
    control_file = debuild_obj.deb_control_file()
    assert os.path.isfile(control_file)


def test_build_debpackage(apt_manager: AptManager, debuild_obj: Debuild) -> None:
    depend_list = debuild_obj.build_dependencies()
    for depend in depend_list:
        assert apt_manager.install_package(depend)
    debuild_obj.build()


def test_deb_changes(debuild_obj: Debuild) -> None:
    changes = debuild_obj.deb_changes_file()
    assert os.path.isfile(changes)
    assert Path(changes).suffix == ".changes"
    print(changes)


def test_deb_changes_files(debuild_obj: Debuild) -> None:
    outdir = debuild_obj.outdir()
    files = debuild_obj.deb_changes_files()
    for file in files:
        deb_file_path = os.path.join(outdir, file)
        assert os.path.exists(deb_file_path)


def test_deb_changes_name(debuild_obj: Debuild) -> None:
    assert debuild_obj.deb_changes_name() != "debhallo"


def test_deb_changes_version(debuild_obj: Debuild) -> None:
    assert debuild_obj.deb_changes_version() == "1.0.0"


def test_deb_changes_arch(debuild_obj: Debuild) -> None:
    architectures = debuild_obj.deb_changes_arch()
    assert "source" in architectures
    assert get_architecture() in architectures


def test_deb_changes_file_fallback_to_any_changes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    debuild_obj = Debuild.__new__(Debuild)
    debuild_obj._outdir = tmp_path

    # No arch-specific file, only source changes available.
    (tmp_path / "debhello_1.0.0_source.changes").write_text(
        "Source: debhello\n", encoding="utf-8"
    )
    monkeypatch.setattr(
        "packtly_builder_tooling.parts.debuild.get_architecture", lambda: "amd64"
    )

    selected = debuild_obj.deb_changes_file()
    assert selected.name == "debhello_1.0.0_source.changes"


def test_deb_changes_file_prefers_newest_arch_match(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    debuild_obj = Debuild.__new__(Debuild)
    debuild_obj._outdir = tmp_path
    monkeypatch.setattr(
        "packtly_builder_tooling.parts.debuild.get_architecture", lambda: "amd64"
    )

    older = tmp_path / "debhello_0.9.0_amd64.changes"
    newer = tmp_path / "debhello_1.0.0_amd64.changes"
    older.write_text("Source: debhello\n", encoding="utf-8")
    time.sleep(0.01)
    newer.write_text("Source: debhello\n", encoding="utf-8")

    selected = debuild_obj.deb_changes_file()
    assert selected == newer
