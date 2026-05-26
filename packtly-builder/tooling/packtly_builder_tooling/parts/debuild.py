import shutil
import subprocess

from pathlib import Path
from debian.deb822 import Deb822
from typing import List
from packtly_builder_tooling.parts.hostarch import get_architecture
from packtly_builder_tooling.logging_setup import setup_logger


class Debuild:
    def __init__(self, builddir: Path) -> None:
        self.logger = setup_logger(__name__)
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
        with subprocess.Popen(
            cmd,
            cwd=self._outdir,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        ) as proc:
            assert proc.stdout is not None
            for line in proc.stdout:
                self.logger.info(line.rstrip())
        if proc.returncode != 0:
            raise subprocess.CalledProcessError(proc.returncode, cmd)
        self.logger.info("Build dependencies installed successfully.")

    def build(self) -> None:
        # -b  build binary packages only; skips dpkg-source so no .orig
        # tarball is required for 3.0 (quilt) source packages.
        debuild_cmd = [self._debuild, "-uc", "-us", "-b"]
        with subprocess.Popen(
            debuild_cmd,
            cwd=self._builddir,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            stdin=subprocess.PIPE,
        ) as proc:
            assert proc.stdin is not None
            # Answer "y" to debuild's interactive orig-tarball prompt so
            # the build does not stall or abort in non-tty environments.
            proc.stdin.write("y\n")
            proc.stdin.close()
            assert proc.stdout is not None
            for line in proc.stdout:
                self.logger.info(line.rstrip())
        if proc.returncode != 0:
            raise subprocess.CalledProcessError(proc.returncode, debuild_cmd)
        self.logger.info("Debian packages built successfully.")

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
        list = self.deb_changes_key("Architecture").split()
        return list
