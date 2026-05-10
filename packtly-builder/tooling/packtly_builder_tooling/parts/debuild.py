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
        depends = self.deb_control_key("Build-Depends")
        return [dep.strip() for dep in depends.split(",")]

    def build(self) -> None:
        debuild_cmd = [self._debuild, "-uc", "-us"]
        try:
            result = subprocess.run(
                debuild_cmd,
                cwd=self._builddir,
                text=True,
                check=True,
                capture_output=True,
            )
            if result.stdout:
                self.logger.info(result.stdout)
            self.logger.info("Debian packages built successfully.")
        except subprocess.CalledProcessError as e:
            if e.stdout:
                self.logger.error(e.stdout)
            if e.stderr:
                self.logger.error(e.stderr)
            raise e

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
