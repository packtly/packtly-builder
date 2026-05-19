import os
import re
import base64
import apt
import apt_pkg
from pathlib import Path
from typing import List, Optional
from aptsources.sourceslist import SourcesList, Deb822SourceEntry
from aptsources.distro import get_distro
from packtly_builder_tooling.logging_setup import setup_logger

KEYRINGS_DIR = Path("/usr/share/keyrings")
SOURCES_DIR = Path("/etc/apt/sources.list.d")


class AptManager:
    """
    High-level interface for managing APT repositories and packages.

    Wraps aptsources and python3-apt to provide a straightforward API
    for the following operations:

    * Key management, install ASCII-armored or binary GPG signing keys
      into "/usr/share/keyrings/" via :meth:`add_key`.
    * Repository management, add deb822-format repository entries to
      "/etc/apt/sources.list.d/" via :meth:`add_repo`.  Duplicate entries
      are silently ignored.
    * Cache refresh, run the equivalent of "apt-get update" via
      :meth:`update`.
    * Package installation, mark and commit a package for installation
      via :meth:`install_package`.  An optional *source_host* filter ensures
      the package is only installed when a version originating from a specific
      host is available.

    Example::

        manager = AptManager()

        keyring = manager.add_key(open("/path/to/key.gpg", "rb").read(), "my-repo")
        manager.add_repo(
            uri="http://my-apt.example.com/debian",
            dist="bookworm",
            components=["main"],
            keyring=keyring,
        )
        manager.update()

        ok = manager.install_package("htop", source_host="my-apt.example.com")
        if not ok:
            logging.error("Installation failed.")
    """

    def __init__(self) -> None:
        apt_pkg.init()
        self.cache = apt.Cache()
        self.distro = get_distro()
        self.logger = setup_logger(__name__)

    def add_key(self, key_data: bytes | str, name: str) -> Path:
        """
        Install an APT signing key into /usr/share/keyrings/<name>.gpg.

        key_data may be ASCII-armored (str or bytes beginning with '-----BEGIN')
        or already binary (dearmored) bytes.  Returns the installed keyring path.
        """
        os.makedirs(KEYRINGS_DIR, exist_ok=True)
        keyring_path = KEYRINGS_DIR / f"{name}.gpg"

        if isinstance(key_data, str):
            key_data = key_data.encode()

        if key_data.lstrip().startswith(b"-----BEGIN"):
            binary_key = self._dearmor(key_data)
        else:
            binary_key = key_data

        with open(keyring_path, "wb") as f:
            f.write(binary_key)

        self.logger.info("Keyring written to %s", keyring_path)
        return keyring_path

    def add_repo(
        self,
        uri: str,
        dist: str,
        components: List[str] | str,
        repo_type: str = "deb",
        keyring: Optional[Path] = None,
    ) -> None:
        """
        Add an apt repository if not already present.
        The entry is written to /etc/apt/sources.list.d/<dist>.sources (deb822).

        keyring: optional path to a .gpg file in /usr/share/keyrings/ that will
                 be added as a Signed-By field in the entry.
        """
        if isinstance(components, str):
            components = [components]

        self.logger.info(
            "Checking if repository is already present: %s %s %s", uri, dist, components
        )

        sources = SourcesList()

        for entry in sources.list:
            if (
                entry.uri == uri
                and entry.dist == dist
                and set(entry.comps) == set(components)
            ):
                self.logger.info("Repository already present.")
                return

        os.makedirs(SOURCES_DIR, exist_ok=True)
        source_file = os.path.join(SOURCES_DIR, f"{dist}.sources")

        section = (
            f"Types: {repo_type}\n"
            f"URIs: {uri}\n"
            f"Suites: {dist}\n"
            f"Components: {' '.join(components)}\n"
        )
        if keyring:
            section += f"Signed-By: {keyring}\n"

        entry = Deb822SourceEntry(section, file=source_file)
        sources.list.append(entry)
        sources.save()
        self.logger.info("Repository added to %s", source_file)

    def update(self) -> bool:
        """
        Run 'apt-get update' to update packages
        """
        self.logger.info("Run apt cache update ...")
        try:
            ret = self.cache.update()
        except Exception as e:
            self.logger.warning("Failed to update apt cache: %s", e)
            return False

        self.logger.info("Apt cache update complete with %s", ret)
        return ret

    def install_package(
        self, package_name: str, source_host: Optional[str] = None
    ) -> bool:
        """
        Install a package from the cache, optionally filtered by source host.
        """
        # Strip Debian build-profile qualifiers e.g. <!nocheck>, <!stage1> and
        # arch restrictions e.g. [amd64] — apt_pkg.parse_depends cannot handle
        # them.  Build-profile names consist only of [a-zA-Z0-9_.-] optionally
        # prefixed with '!'; this avoids matching version operators like '<<'.
        _PROFILE_RE = re.compile(
            r"\s*<(?:!?[a-zA-Z0-9][a-zA-Z0-9_.+-]*)(?:\s+!?[a-zA-Z0-9][a-zA-Z0-9_.+-]*)*>"
        )
        stripped = _PROFILE_RE.sub("", package_name)
        stripped = re.sub(r"\s*\[[^\]]*\]", "", stripped).strip()

        parsed = apt_pkg.parse_depends(stripped)
        if not parsed:
            self.logger.error("Invalid package name: %s", package_name)
            return False

        package_name, req_version, req_relation = parsed[0][0]
        self.cache.open()

        if package_name not in self.cache:
            # The name may be a virtual package.  Walk rev_provides_list to
            # find a real package that satisfies it.
            try:
                apt_pkg_entry = self.cache._cache[package_name]
                providers = [
                    v.parent_pkg.name for v in apt_pkg_entry.rev_provides_list
                ]
            except (KeyError, AttributeError):
                providers = []

            if not providers:
                self.logger.error("Package '%s' not found in cache.", package_name)
                return False

            real_name = providers[0]
            self.logger.info(
                "Package '%s' is virtual; installing provider '%s' instead.",
                package_name,
                real_name,
            )
            package_name = real_name

        pkg = self.cache[package_name]

        if req_version and req_relation:
            candidate = pkg.candidate
            if not apt_pkg.check_dep(candidate.version, req_relation, req_version):
                self.logger.error(
                    "Package '%s' candidate %s does not satisfy %s %s",
                    package_name,
                    candidate.version,
                    req_relation,
                    req_version,
                )
                return False

        if source_host:
            found_version = False
            for version in pkg.versions:
                for uri in version.uris:
                    if source_host in uri:
                        found_version = True
                        break
                if found_version:
                    break
            if not found_version:
                self.logger.error(
                    "Package '%s' not found from source '%s'.",
                    package_name,
                    source_host,
                )
                return False

        self.logger.info("Installing package '%s'...", package_name)
        pkg.mark_install()
        try:
            self.cache.commit()
            self.logger.info("Package '%s' installed successfully.", package_name)
            return True
        except Exception as e:
            self.logger.error("Error during installation: %s", e)
            return False

    def _dearmor(self, armored: bytes) -> bytes:
        lines = armored.decode("ascii").splitlines()
        b64_lines = []
        in_body = False
        for line in lines:
            if line.startswith("-----BEGIN"):
                continue
            if line.startswith("-----END"):
                break
            if not in_body:
                if line.strip() == "":  # blank line separates headers from body
                    in_body = True
                continue
            if line.startswith("="):  # CRC24 checksum line — skip
                break
            b64_lines.append(line.strip())
        return base64.b64decode("".join(b64_lines))
