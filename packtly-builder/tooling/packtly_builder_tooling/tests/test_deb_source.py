from pathlib import Path
from typing import Any, List, Optional

import pytest
from git import Repo

from packtly_builder_tooling.parts.deb_source import DebSourceBuilder


def _make_builder(builddir: Path, outdir: Path) -> DebSourceBuilder:
    """Bypass __init__ so tests don't depend on which()-resolved binaries."""
    obj = DebSourceBuilder.__new__(DebSourceBuilder)
    obj._builddir = builddir
    obj._outdir = outdir
    obj._gbp = "gbp"
    obj._dpkg_buildpackage = "dpkg-buildpackage"
    obj._repo_loaded = False
    obj._repo_cache = None
    obj._changelog_cache = None
    return obj


def _write_source_format(builddir: Path, fmt: str) -> None:
    src = builddir / "debian" / "source"
    src.mkdir(parents=True, exist_ok=True)
    (src / "format").write_text(fmt, encoding="utf-8")


def _write_changelog(builddir: Path, pkg: str, version: str) -> None:
    deb = builddir / "debian"
    deb.mkdir(parents=True, exist_ok=True)
    (deb / "changelog").write_text(
        f"{pkg} ({version}) unstable; urgency=low\n\n"
        f"  * test\n\n"
        f" -- Tester <t@example.com>  Mon, 30 Jun 2026 00:00:00 +0000\n",
        encoding="utf-8",
    )


# --- pure logic -------------------------------------------------------------


def test_is_quilt_format_true(tmp_path: Path) -> None:
    _write_source_format(tmp_path, "3.0 (quilt)\n")
    builder = _make_builder(tmp_path, tmp_path.parent)
    assert builder.is_quilt_format() is True


def test_is_quilt_format_native(tmp_path: Path) -> None:
    _write_source_format(tmp_path, "3.0 (native)\n")
    builder = _make_builder(tmp_path, tmp_path.parent)
    assert builder.is_quilt_format() is False


def test_source_name_and_version(tmp_path: Path) -> None:
    _write_changelog(tmp_path, "debhello", "1.0.0-1")
    builder = _make_builder(tmp_path, tmp_path.parent)
    assert builder.source_name() == "debhello"
    assert builder.upstream_version() == "1.0.0"


def test_orig_tarball_exists_ignores_asc(tmp_path: Path) -> None:
    out = tmp_path / "out"
    out.mkdir()
    _write_changelog(tmp_path, "debhello", "1.0.0-1")
    builder = _make_builder(tmp_path, out)

    (out / "debhello_1.0.0.orig.tar.xz.asc").write_text("sig", encoding="utf-8")
    assert builder.orig_tarball_exists() is False

    (out / "debhello_1.0.0.orig.tar.xz").write_bytes(b"data")
    assert builder.orig_tarball_exists() is True


def test_remove_existing_orig(tmp_path: Path) -> None:
    out = tmp_path / "out"
    out.mkdir()
    _write_changelog(tmp_path, "debhello", "1.0.0-1")
    stale = out / "debhello_1.0.0.orig.tar.gz"
    stale.write_bytes(b"old")
    keep = out / "unrelated_2.0.0.orig.tar.gz"
    keep.write_bytes(b"keep")

    builder = _make_builder(tmp_path, out)
    builder._remove_existing_orig()

    assert not stale.exists()
    assert keep.exists()


# --- git logic against a real temp repo -------------------------------------


@pytest.fixture
def git_builddir(tmp_path: Path) -> Path:
    builddir = tmp_path / "src"
    builddir.mkdir()
    repo = Repo.init(builddir)
    with repo.config_writer() as cw:
        cw.set_value("user", "name", "Tester")
        cw.set_value("user", "email", "t@example.com")
    (builddir / "file.txt").write_text("content", encoding="utf-8")
    repo.index.add(["file.txt"])
    repo.index.commit("initial")
    return builddir


def test_branch_exists_local(git_builddir: Path) -> None:
    Repo(git_builddir).create_head("pristine-tar")
    builder = _make_builder(git_builddir, git_builddir.parent)
    assert builder._branch_exists("pristine-tar") is True
    assert builder._branch_exists("nope") is False


def test_repo_none_for_non_git_tree(tmp_path: Path) -> None:
    builder = _make_builder(tmp_path, tmp_path.parent)
    assert builder._repo() is None
    assert builder._branch_exists("pristine-tar") is False


def test_repo_does_not_climb_to_parent(tmp_path: Path) -> None:
    """A non-git build tree nested in a parent repo must not resolve the parent."""
    Repo.init(tmp_path)
    builddir = tmp_path / "src"
    builddir.mkdir()
    builder = _make_builder(builddir, tmp_path)
    assert builder._repo() is None


def test_reset_source_tree_cleans_untracked(git_builddir: Path) -> None:
    _write_source_format(git_builddir, "3.0 (quilt)\n")
    artifact = git_builddir / "generated.bin"
    artifact.write_bytes(b"junk")  # untracked build artifact

    builder = _make_builder(git_builddir, git_builddir.parent)
    builder.reset_source_tree()

    assert not artifact.exists()  # git clean removed it
    assert (git_builddir / "file.txt").exists()  # tracked file preserved


def test_reset_source_tree_noop_when_native(git_builddir: Path) -> None:
    _write_source_format(git_builddir, "3.0 (native)\n")
    artifact = git_builddir / "generated.bin"
    artifact.write_bytes(b"junk")

    builder = _make_builder(git_builddir, git_builddir.parent)
    builder.reset_source_tree()

    assert artifact.exists()  # native packages are not reset


# --- external tool call is delegated, not executed --------------------------


def test_export_orig_invokes_gbp(
    git_builddir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    Repo(git_builddir).create_head("pristine-tar")
    captured: dict[str, Any] = {}

    def fake_run_subprocess(
        cmd: List[str], cwd: Path, stdin_data: Optional[str] = None
    ) -> None:
        captured["cmd"] = cmd
        captured["cwd"] = cwd

    monkeypatch.setattr(
        "packtly_builder_tooling.parts.deb_source.run_subprocess",
        fake_run_subprocess,
    )

    builder = _make_builder(git_builddir, git_builddir.parent)
    builder._export_orig_via_pristine_tar()

    assert captured["cmd"][:2] == ["gbp", "export-orig"]
    assert captured["cwd"] == git_builddir
