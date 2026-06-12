import pytest
import os
import subprocess
from pathlib import Path
import time
from typing import Any, Sequence
from unittest.mock import MagicMock

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
        assert apt_manager.install_dependencies(depend)
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


# ---------------------------------------------------------------------------
# Unit tests for install_build_dependencies (hermetic, no real subprocesses)
# ---------------------------------------------------------------------------


def _make_debuild(tmp_path: Path) -> Debuild:
    """Return a Debuild instance bypassing __init__ with a minimal control file."""
    control_dir = tmp_path / "debian"
    control_dir.mkdir(parents=True)
    (control_dir / "control").write_text(
        "Source: debhello\nBuild-Depends: debhelper\n", encoding="utf-8"
    )
    obj = Debuild.__new__(Debuild)
    obj._builddir = tmp_path
    obj._outdir = tmp_path.parent
    from debian.deb822 import Deb822

    obj.parsed_control_info = Deb822()
    obj.parsed_deb_info = Deb822()
    return obj


def test_install_build_dependencies_raises_when_mk_build_deps_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """FileNotFoundError is raised when mk-build-deps is not on PATH."""
    obj = _make_debuild(tmp_path)
    monkeypatch.setattr(
        "packtly_builder_tooling.parts.debuild.shutil.which", lambda _name: None
    )
    with pytest.raises(FileNotFoundError, match="mk-build-deps"):
        obj.install_build_dependencies()


def test_install_build_dependencies_builds_correct_command(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The command passed to Popen contains the expected flags and the control file path."""
    obj = _make_debuild(tmp_path)
    mk_path = "/usr/bin/mk-build-deps"
    monkeypatch.setattr(
        "packtly_builder_tooling.parts.debuild.shutil.which", lambda _name: mk_path
    )

    captured: list = []

    mock_proc = MagicMock()
    mock_proc.__enter__ = lambda s: s
    mock_proc.__exit__ = MagicMock(return_value=False)
    mock_proc.stdout = iter([])
    mock_proc.returncode = 0

    def fake_popen(cmd: Sequence[str], **kwargs: Any) -> MagicMock:
        captured.append(cmd)
        return mock_proc

    monkeypatch.setattr(
        "packtly_builder_tooling.parts.debuild.subprocess.Popen", fake_popen
    )

    obj.install_build_dependencies()

    assert len(captured) == 1
    cmd = captured[0]
    assert cmd[0] == mk_path
    assert "--install" in cmd
    assert "--remove" in cmd
    assert any("apt-get" in arg for arg in cmd)
    assert str(obj.deb_control_file()) in cmd


def test_install_build_dependencies_raises_on_nonzero_exit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """CalledProcessError is raised when mk-build-deps exits with a non-zero code."""
    obj = _make_debuild(tmp_path)
    monkeypatch.setattr(
        "packtly_builder_tooling.parts.debuild.shutil.which",
        lambda _name: "/usr/bin/mk-build-deps",
    )

    mock_proc = MagicMock()
    mock_proc.__enter__ = lambda s: s
    mock_proc.__exit__ = MagicMock(return_value=False)
    mock_proc.stdout = iter(["error output\n"])
    mock_proc.returncode = 1

    monkeypatch.setattr(
        "packtly_builder_tooling.parts.debuild.subprocess.Popen",
        lambda *_args, **_kwargs: mock_proc,
    )

    with pytest.raises(subprocess.CalledProcessError):
        obj.install_build_dependencies()
