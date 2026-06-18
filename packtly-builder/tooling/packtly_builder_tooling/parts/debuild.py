import shutil
from enum import Enum
from pathlib import Path
from debian.deb822 import Deb822
from typing import List
from packtly_builder_tooling.parts.hostarch import get_architecture
from packtly_builder_tooling.logging_setup import setup_logger
from packtly_builder_tooling.parts.utils import run_subprocess

logger = setup_logger(__name__)


class BuildMode(Enum):
    BINARY = "-b"  # binary packages only (no .orig tarball required)
    SOURCE = "-S"  # source package only
    FULL = "-F"  # source + binary


class Debuild:
    def __init__(self, builddir: Path) -> None:
        debuild_executable = shutil.which("debuild")
        self.parsed_control_info = Deb822()
        self.parsed_deb_info = Deb822()
        if debuild_executable:
            print("debuild executable found at:", debuild_executable)
            self._debuild = debuild_executable
            self._builddir = builddir
            self._outdir = Path(builddir).parent.resolve()
        else:
            raise FileNotFoundError("debuild executable not found")

    def build_dependencies(self) -> List[str]:
        all_deps: List[str] = []
        for key in ("Build-Depends", "Build-Depends-Indep", "Build-Depends-Arch"):
            try:
                raw = self.deb_control_key(key)
            except KeyError:
                continue
            if raw:
                all_deps.extend(dep.strip() for dep in raw.split(",") if dep.strip())
        return all_deps

    def install_build_dependencies(self) -> None:
        """
        Install all build dependencies declared in debian/control using
        mk-build-deps.  This correctly handles virtual packages, OR
        alternatives, architecture restrictions, and build-profile
        qualifiers — all of which the manual apt parsing approach cannot
        reliably handle.
        """
        mk_build_deps = shutil.which("mk-build-deps")
        if not mk_build_deps:
            raise FileNotFoundError("mk-build-deps not found (install devscripts)")

        cmd = [
            mk_build_deps,
            "--install",
            "--remove",
            "--tool=apt-get -y --no-install-recommends",
            str(self.deb_control_file()),
        ]
        run_subprocess(cmd, self._outdir)

        logger.info("Build dependencies installed successfully.")

    def build(self, mode: BuildMode = BuildMode.BINARY) -> None:
        # -b  binary only  — no .orig tarball required (3.0 quilt or native)
        # -S  source only  — requires .orig.tar.* in parent dir for quilt
        # -F  full build   — source + binary
        debuild_cmd = [self._debuild, "-uc", "-us"]
        if mode in (BuildMode.SOURCE, BuildMode.FULL):
            self._reset_source_tree()
            self.ensure_orig_tarball()
            # The build log is written into a ``logs/`` directory inside the
            # source tree; tell dpkg-source to ignore it so the live log does
            # not register as an unrepresentable upstream change.
            debuild_cmd.append(
                "--source-option=--extend-diff-ignore=(^|/)logs/"
            )
        debuild_cmd.append(mode.value)
        run_subprocess(debuild_cmd, self._builddir, stdin_data="y\n")
        logger.info("Debian packages built successfully.")

    def builddir(self) -> Path:
        return self._builddir

    def outdir(self) -> Path:
        return self._outdir

    def source_format(self) -> str:
        format_file = self._builddir / "debian" / "source" / "format"
        if format_file.is_file():
            return format_file.read_text(encoding="utf-8").strip()
        return ""

    def is_quilt_format(self) -> bool:
        """True for non-native quilt packages that need a separate .orig tarball."""
        return self.source_format().startswith("3.0 (quilt)")

    def _parse_changelog(self, field: str) -> str:
        changelog = self._builddir / "debian" / "changelog"
        output = run_subprocess(
            ["dpkg-parsechangelog", "-l", str(changelog), "-S", field],
            self._builddir,
            mode="capture",
        )
        return output.stdout.strip()

    def source_name(self) -> str:
        return self._parse_changelog("Source")

    def upstream_version(self) -> str:
        """Upstream version: drop epoch (before ':') and Debian revision (after last '-')."""
        version = self._parse_changelog("Version")
        if ":" in version:
            version = version.split(":", 1)[1]
        if "-" in version:
            version = version.rsplit("-", 1)[0]
        return version

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

    def _reset_source_tree(self) -> None:
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
        git = shutil.which("git")
        if not git:
            return

        result = run_subprocess(
            [git, "-C", str(self._builddir), "rev-parse", "--is-inside-work-tree"],
            cwd=self._builddir,
            mode="capture",
            check=False,
        )
        if result.returncode != 0 or result.stdout.strip() != "true":
            return
        logger.info("Resetting source tree to committed state before source build")
        # Restore tracked files the clean target deleted or modified.
        cmd_checkout = [git, "-C", str(self._builddir), "checkout", "--", "."]
        run_subprocess(cmd_checkout, self._builddir)

        # Remove untracked and ignored build artifacts (symlinks, binaries, etc.).
        cmd_clean = [git, "-C", str(self._builddir), "clean", "-fdx"]
        run_subprocess(cmd_clean, self._builddir)

    def _export_orig_via_pristine_tar(self) -> None:
        gbp = shutil.which("gbp")
        if not gbp:
            raise FileNotFoundError(
                "gbp not found (install git-buildpackage) — cannot regenerate "
                "the upstream orig tarball from the pristine-tar branch"
            )
        self._ensure_local_branch("pristine-tar")
        # gbp export-orig writes the tarball to the parent directory (outdir).
        logger.info("Regenerating upstream orig tarball via pristine-tar")
        gbp_cmd = [gbp, "export-orig", "--pristine-tar"]
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
        tar = shutil.which("tar")
        if not tar:
            raise FileNotFoundError("tar not found — cannot build the orig tarball")

        self._remove_existing_orig()
        self._clean_build_tree()

        tarball = (
            self._outdir
            / f"{self.source_name()}_{self.upstream_version()}.orig.tar.xz"
        )
        logger.info("Building upstream orig tarball %s", tarball.name)
        tar_cmd = [
            tar,
            "--create",
            "--xz",
            "--exclude=./debian",
            "--exclude=./logs",
            "--exclude=./.git",
            f"--file={tarball}",
            ".",
        ]
        run_subprocess(tar_cmd, self._builddir)

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
        dpkg_buildpackage = shutil.which("dpkg-buildpackage")
        if not dpkg_buildpackage:
            return
        run_subprocess([dpkg_buildpackage, "-T", "clean"], self._builddir)

    def _branch_exists(self, branch: str) -> bool:
        """Return True when *branch* exists locally or on ``origin``.

        Used to decide between the pristine-tar and tree-archive workflows. A
        missing git binary or a non-git source tree simply means the branch is
        absent, so this never raises.
        """
        git = shutil.which("git")
        if not git:
            return False
        for ref in (f"refs/heads/{branch}", f"refs/remotes/origin/{branch}"):
            found = run_subprocess(
                [git, "-C", str(self._builddir), "show-ref", "--verify", "--quiet", ref],
                self._builddir,
                mode="silent",
                check=False,
            )
            if found.returncode == 0:
                return True
        return False

    def _ensure_local_branch(self, branch: str) -> None:
        """Create a local branch tracking origin/<branch> if it only exists remotely.

        After a plain ``git clone`` the pristine-tar data is a remote-tracking
        branch; pristine-tar/gbp operate on the local ``refs/heads`` ref.
        """
        git = shutil.which("git")
        if not git:
            raise FileNotFoundError("git not found")
        has_local = run_subprocess(
            [
                git,
                "-C",
                str(self._builddir),
                "show-ref",
                "--verify",
                "--quiet",
                f"refs/heads/{branch}",
            ],
            self._builddir,
            mode="capture",
            check=False,
        )
        if has_local.returncode == 0:
            return

        has_remote = run_subprocess(
            [
                git,
                "-C",
                str(self._builddir),
                "show-ref",
                "--verify",
                "--quiet",
                f"refs/remotes/origin/{branch}",
            ],
            self._builddir,
            mode="capture",
            check=False,
        )
        if has_remote.returncode != 0:
            raise FileNotFoundError(
                f"No '{branch}' branch found locally or on origin; cannot "
                "regenerate the upstream orig tarball"
            )

        cmd = [
            git,
            "-C",
            str(self._builddir),
            "branch",
            branch,
            f"origin/{branch}",
        ]

        run_subprocess(cmd, self._builddir)

    def deb_control_file(self) -> Path:
        control_file = self._builddir / "debian" / "control"
        if not control_file.is_file():
            raise FileNotFoundError("No control file found")
        return control_file

    def deb_control_key(self, key: str) -> str:
        if not self.parsed_control_info:
            with open(self.deb_control_file(), "r", encoding="utf-8") as file:
                control_info = file.read()
                self.parsed_control_info = Deb822(control_info.splitlines())
        return self.parsed_control_info.get_as_string(key)

    def deb_changes_file(self) -> Path:
        arch = get_architecture()
        outdir = Path(self._outdir)

        # Prefer architecture-specific changes files first.
        arch_matches = sorted(
            outdir.glob(f"*_{arch}.changes"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        if arch_matches:
            return arch_matches[0]

        # Fallback to any .changes file and pick the newest artifact.
        all_matches = sorted(
            outdir.glob("*.changes"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        if all_matches:
            return all_matches[0]

        raise FileNotFoundError(
            f"No .changes files found in {outdir} (expected arch: {arch})"
        )

    def deb_changes_key(self, key: str) -> str:
        if not self.parsed_deb_info:
            with open(self.deb_changes_file(), "r", encoding="utf-8") as file:
                package_info = file.read()
                self.parsed_deb_info = Deb822(package_info.split("\n"))
        return self.parsed_deb_info.get_as_string(key)

    def deb_changes_files(self) -> List[str]:
        deb_files = self.deb_changes_key("Files")
        files = [line.split()[4] for line in deb_files.strip().split("\n")]
        return files

    def deb_changes_name(self) -> str:
        return self.deb_changes_key("Source")

    def deb_changes_version(self) -> str:
        return self.deb_changes_key("Version")

    def deb_changes_arch(self) -> List[str]:
        list = self.deb_changes_key("Architecture").split()
        return list
