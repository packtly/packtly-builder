import shutil
import tarfile
from pathlib import Path
from typing import Optional
from debian.changelog import Changelog
from git import Remote, Repo
from git.exc import InvalidGitRepositoryError, NoSuchPathError
from packtly_builder_tooling.logging_setup import setup_logger
from packtly_builder_tooling.parts.utils import run_subprocess

logger = setup_logger(__name__)


class DebSourceBuilder:
    def __init__(self, builddir: Path, outdir: Path) -> None:
        self._builddir = builddir
        self._outdir = outdir
        self._git = shutil.which("git")
        self._gbp = shutil.which("gbp")
        self._dpkg_buildpackage = shutil.which("dpkg-buildpackage")
        self._repo_loaded = False
        self._repo_cache: Optional[Repo] = None
        if not self._git:
            logger.warning(
                "git executable not found — cannot check for pristine-tar branch or "
                "reset the source tree before a quilt source build"
            )
        if not self._gbp:
            logger.warning(
                "gbp executable not found — cannot regenerate the upstream orig tarball "
                "from the pristine-tar branch"
            )
        if not self._dpkg_buildpackage:
            logger.warning(
                "dpkg-buildpackage executable not found — cannot clean the build tree "
                "before building the orig tarball from the source tree"
            )

    def source_format(self) -> str:
        format_file = self._builddir / "debian" / "source" / "format"
        if format_file.is_file():
            return format_file.read_text(encoding="utf-8").strip()
        return ""

    def is_quilt_format(self) -> bool:
        """True for non-native quilt packages that need a separate .orig tarball."""
        return self.source_format().startswith("3.0 (quilt)")

    def _changelog(self) -> Changelog:
        changelog_file = self._builddir / "debian" / "changelog"
        if not changelog_file.is_file():
            raise FileNotFoundError(f"Changelog file not found at {changelog_file}")

        return Changelog(changelog_file.read_text(encoding="utf-8"))

    def source_name(self) -> str:
        return self._changelog().package or ""

    def upstream_version(self) -> str:
        version = self._changelog().version
        return version.upstream_version or str(version)

    def orig_tarball_exists(self) -> bool:
        prefix = f"{self.source_name()}_{self.upstream_version()}.orig.tar."
        return any(
            p.name.startswith(prefix) and not p.name.endswith(".asc")
            for p in self._outdir.iterdir()
            if p.is_file()
        )

    def ensure_orig_tarball(self) -> None:
        """Ensure the upstream .orig tarball exists for a 3.0 (quilt) source build.

        Quilt packages keep upstream source and Debian packaging separate, so
        ``dpkg-source -b`` requires ``../<source>_<upstream>.orig.tar.*``. Two
        conventional sources provide it:

        * git-buildpackage repositories store the tarball on the
          ``pristine-tar`` branch; it is deterministic, so an already-exported
          tarball is reused.
        * plain Debian source trees have no stored tarball, so it is rebuilt
          from the current working tree every time to guarantee it matches the
          source being packaged (a stale tarball from a previous run would make
          ``dpkg-source`` report unrepresentable changes).
        """
        if not self.is_quilt_format():
            return

        if self._branch_exists("pristine-tar"):
            if self.orig_tarball_exists():
                logger.info(
                    "Upstream orig tarball already present, skipping regeneration"
                )
                return
            logger.info(
                "No upstream orig tarball for %s %s; exporting via pristine-tar",
                self.source_name(),
                self.upstream_version(),
            )
            self._export_orig_via_pristine_tar()
        else:
            logger.info(
                "Building upstream orig tarball for %s %s from the source tree",
                self.source_name(),
                self.upstream_version(),
            )
            self._create_orig_from_tree()

        if not self.orig_tarball_exists():
            raise FileNotFoundError(
                f"Failed to regenerate upstream orig tarball for "
                f"{self.source_name()}_{self.upstream_version()} in {self._outdir}"
            )
        logger.info("Upstream orig tarball ready")

    def reset_source_tree(self) -> None:
        """Restore the git checkout to its committed state before a quilt source build.

        ``dpkg-source -b`` for a 3.0 (quilt) package diffs the working tree
        against the pristine upstream ``.orig`` tarball. Artifacts left behind by
        a previous build that ``debian/rules clean`` does not remove — new
        symlinks, regenerated binaries, generated files — produce
        ``unrepresentable changes to source`` errors. Resetting the git checkout
        guarantees the tree matches the committed packaging branch, which is the
        state ``dpkg-source`` expects.
        """
        if not self.is_quilt_format():
            return

        repo = self._repo()
        if repo is None or repo.bare:
            return
        logger.info("Resetting source tree to committed state before source build")
        # Restore tracked files the clean target deleted or modified.
        repo.git.checkout("--", ".")
        # Remove untracked and ignored build artifacts (symlinks, binaries, etc.),
        # scoped to the build tree so a surrounding repo is never touched.
        repo.git.clean("-fdx", "--", str(self._builddir))

    def _export_orig_via_pristine_tar(self) -> None:
        if not self._gbp:
            raise FileNotFoundError(
                "gbp not found (install git-buildpackage) — cannot regenerate "
                "the upstream orig tarball from the pristine-tar branch"
            )
        self._ensure_local_branch("pristine-tar")
        # gbp export-orig writes the tarball to the parent directory (outdir).
        logger.info("Regenerating upstream orig tarball via pristine-tar")
        gbp_cmd = [self._gbp, "export-orig", "--pristine-tar"]
        run_subprocess(gbp_cmd, self._builddir)

    def _create_orig_from_tree(self) -> None:
        """Build the upstream orig tarball directly from the working tree.

        For a 3.0 (quilt) package without a ``pristine-tar`` branch this mirrors
        the standard ``dh_make`` behaviour: archive the source tree into
        ``../<source>_<upstream>.orig.tar.xz`` excluding the ``debian/``
        packaging directory, the VCS metadata and the build-log output
        directory. The tree is cleaned first so build artifacts never leak into
        the pristine tarball, and any stale tarball from an earlier run is
        removed so it cannot mask a change in the source.
        """
        self._remove_existing_orig()
        self._clean_build_tree()

        tarball = (
            self._outdir / f"{self.source_name()}_{self.upstream_version()}.orig.tar.xz"
        )
        logger.info("Building upstream orig tarball %s", tarball.name)
        _EXCLUDED = {"debian", "logs", ".git"}

        def _exclude(info: tarfile.TarInfo) -> tarfile.TarInfo | None:
            # info.name is relative to the arcname root, e.g. "./debian/control"
            top = info.name.lstrip("./").split("/")[0]
            return None if top in _EXCLUDED else info

        with tarfile.open(tarball, "w:xz") as tf:
            tf.add(self._builddir, arcname=".", filter=_exclude)

    def _remove_existing_orig(self) -> None:
        """Delete any existing upstream orig tarball for this version.

        A tarball left behind by an earlier (possibly failed) run no longer
        matches the current tree and would make ``dpkg-source`` compare against
        stale upstream source.
        """
        prefix = f"{self.source_name()}_{self.upstream_version()}.orig.tar."
        for entry in self._outdir.iterdir():
            if entry.is_file() and entry.name.startswith(prefix):
                logger.info("Removing stale orig tarball %s", entry.name)
                entry.unlink()

    def _clean_build_tree(self) -> None:
        """Run the package ``clean`` target so build artifacts are not archived.

        Without this a previously compiled binary (e.g. ``src/hello``) ends up
        inside the pristine tarball and ``dpkg-source`` later reports its
        removal once the clean target deletes it during the real build.
        """
        if not self._dpkg_buildpackage:
            return
        run_subprocess([self._dpkg_buildpackage, "-T", "clean"], self._builddir)

    def _branch_exists(self, branch: str) -> bool:
        """Return True when *branch* exists locally or on ``origin``.

        Used to decide between the pristine-tar and tree-archive workflows. A
        missing git binary or a non-git source tree simply means the branch is
        absent, so this never raises.
        """
        repo = self._repo()
        if repo is None:
            return False
        if branch in (head.name for head in repo.heads):
            return True
        origin = self._origin(repo)
        if origin is None:
            return False
        return any(ref.remote_head == branch for ref in origin.refs)

    def _ensure_local_branch(self, branch: str) -> None:
        """Create a local branch tracking origin/<branch> if it only exists remotely.

        After a plain ``git clone`` the pristine-tar data is a remote-tracking
        branch; pristine-tar/gbp operate on the local ``refs/heads`` ref.
        """
        repo = self._repo()
        if repo is None:
            raise FileNotFoundError("git not found")
        if branch in (head.name for head in repo.heads):
            return

        origin = self._origin(repo)
        if origin is None or branch not in (ref.remote_head for ref in origin.refs):
            raise FileNotFoundError(
                f"No '{branch}' branch found locally or on origin; cannot "
                "regenerate the upstream orig tarball"
            )

        repo.create_head(branch, f"origin/{branch}")

    def _repo(self) -> Optional[Repo]:
        """Return the git repository for the build tree, or ``None``.

        A missing git binary, a non-git source tree, or a missing path simply
        yields ``None`` so callers can fall back to the tree-archive workflow
        without raising. The result is cached for the lifetime of the builder.

        The build tree is opened directly (parent directories are not searched)
        so a surrounding repository is never mistaken for the source tree — that
        would scope ``git clean -fdx`` to the wrong working directory.
        """
        if not self._repo_loaded:
            self._repo_loaded = True
            if self._git:
                try:
                    self._repo_cache = Repo(self._builddir)
                except (InvalidGitRepositoryError, NoSuchPathError):
                    self._repo_cache = None
        return self._repo_cache

    @staticmethod
    def _origin(repo: Repo) -> Optional[Remote]:
        """Return the ``origin`` remote if it is configured, otherwise ``None``."""
        try:
            return repo.remote("origin")
        except ValueError:
            return None
