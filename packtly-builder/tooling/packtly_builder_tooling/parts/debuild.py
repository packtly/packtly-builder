import shutil
from enum import Enum
from pathlib import Path
from debian.deb822 import Deb822
from typing import List
from packtly_builder_tooling.parts.hostarch import get_architecture
from packtly_builder_tooling.logging_setup import setup_logger
from packtly_builder_tooling.parts.deb_source import DebSourceBuilder
from packtly_builder_tooling.parts.utils import run_subprocess

logger = setup_logger(__name__)


class BuildMode(Enum):
    BINARY = "-b"  # binary packages only (no .orig tarball required)
    SOURCE = "-S"  # source package only
    FULL = "-F"  # source + binary

    @property
    def description(self) -> str:
        return {
            BuildMode.BINARY: "binary (binary packages only)",
            BuildMode.SOURCE: "source (source package only)",
            BuildMode.FULL: "full (source + binary)",
        }[self]


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
            self._orig_tarball = DebSourceBuilder(builddir, self._outdir)
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
            self._orig_tarball.reset_source_tree()
            self._orig_tarball.ensure_orig_tarball()
            # The build log is written into a ``logs/`` directory inside the
            # source tree; tell dpkg-source to ignore it so the live log does
            # not register as an unrepresentable upstream change.
            debuild_cmd.append("--source-option=--extend-diff-ignore=(^|/)logs/")
        debuild_cmd.append(mode.value)
        run_subprocess(debuild_cmd, self._builddir, stdin_data="y\n")
        logger.info("Debian packages built successfully.")

    def builddir(self) -> Path:
        return self._builddir

    def outdir(self) -> Path:
        return self._outdir

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
        arch_list = self.deb_changes_key("Architecture").split()
        return arch_list
