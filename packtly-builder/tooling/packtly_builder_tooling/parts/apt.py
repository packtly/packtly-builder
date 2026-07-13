import os
import re
import base64
import apt
import apt_pkg
import apt_inst
from debian.deb822 import Deb822
from pathlib import Path
from typing import List, Optional, NamedTuple
from aptsources.sourceslist import SourcesList, Deb822SourceEntry
from aptsources.distro import get_distro
from packtly_builder_tooling.logging_setup import setup_logger

KEYRINGS_DIR = Path("/usr/share/keyrings")
SOURCES_DIR = Path("/etc/apt/sources.list.d")

# Compiled once at module scope to avoid repeated compilation overhead.
# Matches Debian build-profile qualifiers e.g. <!nocheck>, <!stage1>.
_PROFILE_RE = re.compile(
    r"\s*<(?:!?[a-zA-Z0-9][a-zA-Z0-9_.+-]*)(?:\s+!?[a-zA-Z0-9][a-zA-Z0-9_.+-]*)*>"
)


class DebFileInfo(NamedTuple):
    name: str
    version: str
    arch: str


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

    # ------------------------------------------------------------------ #
    # Repository management                                                #
    # ------------------------------------------------------------------ #

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
    ) -> Path:
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

        source_file = os.path.join(SOURCES_DIR, f"{dist}.sources")
        sources = SourcesList()

        for entry in sources.list:
            if (
                entry.uri == uri
                and entry.dist == dist
                and set(entry.comps) == set(components)
            ):
                self.logger.info("Repository already present.")
                return Path(source_file)

        os.makedirs(SOURCES_DIR, exist_ok=True)

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
        return Path(source_file)

    def update(self, sources_list: Optional[Path] = None) -> bool:
        """
        Run 'apt-get update' to update packages.
        """
        self.logger.info("Run apt cache update ...")
        try:
            cache = apt.Cache()
            cache.update(sources_list=str(sources_list) if sources_list else None)
            cache.open()
            self.cache = cache
        except Exception:
            self.logger.exception("Failed to update apt cache")
            return False

        self.logger.info(
            "Apt cache update complete with %d packages available.", len(self.cache)
        )
        return True

    # ------------------------------------------------------------------ #
    # Package installation                                                 #
    # ------------------------------------------------------------------ #

    def install_dependencies(
        self,
        package_name: str,
        source_host: Optional[str] = None,
    ) -> bool:
        """
        Install a package from the cache, optionally filtered by source host.
        """

        # Strip Debian build-profile qualifiers e.g. <!nocheck>, <!stage1> and
        # arch restrictions e.g. [amd64] — apt_pkg.parse_depends cannot handle
        # them.
        stripped = _PROFILE_RE.sub("", package_name)
        stripped = re.sub(r"\s*\[[^\]]*\]", "", stripped).strip()

        parsed = apt_pkg.parse_depends(stripped)
        if not parsed:
            self.logger.error("Invalid package name: %s", package_name)
            return False

        package_name, req_version, req_relation = parsed[0][0]
        self.cache.open()
        is_virtual = package_name not in self.cache
        resolved_name: Optional[str] = None

        if req_version and req_relation:
            resolved_name = self._resolve_package_name(package_name)
            if resolved_name is None:
                self.logger.error("Package '%s' not found in cache.", package_name)
                return False

            if is_virtual:
                # For virtual packages the version constraint applies to the
                # *provided* version, not the real provider's version.  Check
                # that at least one provides entry satisfies the constraint.
                try:
                    apt_pkg_entry = self.cache._cache[package_name]
                    satisfied = any(
                        prov[1]
                        and apt_pkg.check_dep(prov[1], req_relation, req_version)
                        for prov in apt_pkg_entry.provides_list
                        if prov[2].parent_pkg.name == resolved_name
                    )
                except (KeyError, AttributeError):
                    satisfied = False
                if not satisfied:
                    self.logger.error(
                        "No provider for '%s %s %s' found in cache.",
                        package_name,
                        req_relation,
                        req_version,
                    )
                    return False
            else:
                pkg = self.cache[resolved_name]
                candidate = pkg.candidate
                if not apt_pkg.check_dep(candidate.version, req_relation, req_version):
                    self.logger.error(
                        "Package '%s' candidate %s does not satisfy %s %s",
                        resolved_name,
                        candidate.version,
                        req_relation,
                        req_version,
                    )
                    return False

        if is_virtual:
            # Install the real provider; do not pin to the virtual version.
            install_name = resolved_name or self._resolve_package_name(package_name)
            if install_name is None:
                self.logger.error("Package '%s' not found in cache.", package_name)
                return False
            return self.install_package(install_name, source_host=source_host)

        pinned_version = req_version if req_relation in ("=", "==") else None

        return self.install_package(
            package_name,
            version=pinned_version,
            source_host=source_host,
        )

    def install_package(
        self,
        package_name: str,
        version: Optional[str] = None,
        source_host: Optional[str] = None,
    ) -> bool:
        """
        Install a package from the cache, optionally filtered by version and source host.
        """

        self.cache.open()

        resolved_name = self._resolve_package_name(package_name)
        if resolved_name is None:
            self.logger.error("Package '%s' not found in cache.", package_name)
            return False

        pkg = self.cache[resolved_name]

        for candidate in pkg.versions:
            if version and candidate.version != version:
                continue

            if source_host:
                found = False
                for uri in candidate.uris:
                    if source_host in uri:
                        found = True
                        break

                if not found:
                    continue

            self.logger.info("Installing package '%s'...", resolved_name)
            pkg.mark_install()
            try:
                self.cache.commit()
                self.logger.info(
                    "Package '%s' installed successfully.",
                    resolved_name,
                )
                return True
            except Exception as e:
                self.logger.error("Error during installation: %s", e)
                return False

        self.logger.error(
            "Package '%s' not available%s%s.",
            package_name,
            f" with version '{version}'" if version else "",
            f" from source '{source_host}'" if source_host else "",
        )
        return False

    # ------------------------------------------------------------------ #
    # Package existence checks                                             #
    # ------------------------------------------------------------------ #

    def package_exists(
        self,
        package_name: str,
        version: Optional[str] = None,
        source_host: Optional[str] = None,
    ) -> bool:
        """
        Check whether a package (optionally with a specific version)
        is available from the configured apt repositories.
        """
        resolved_name = self._resolve_package_name(package_name)
        if resolved_name is None:
            return False

        pkg = self.cache[resolved_name]

        return any(
            (version is None or candidate.version == version)
            and (
                source_host is None or any(source_host in uri for uri in candidate.uris)
            )
            for candidate in pkg.versions
        )

    def upstream_file_exists(
        self,
        file_path: Path,
        source_host: Optional[str] = None,
    ) -> bool:
        """Check whether the package represented by a .deb file path already
        exists on *source_host*.

        Parses the .deb control data and delegates to :meth:`package_exists`.
        Non-deb files (e.g. .buildinfo) that cannot be parsed are silently
        ignored and return False.
        """
        parsed = self._parse_deb_file(file_path)
        if parsed is None:
            return False
        name, version, _arch = parsed
        return self.package_exists(
            name,
            version=version,
            source_host=source_host,
        )

    def deb_dsc_extra_files(self, dsc_path: Path) -> List[str]:
        """Return all files listed in a .dsc.

        dpkg-buildpackage omits the orig tarball from the .changes on
        non-first uploads.  Aptly needs it to successfully import a source
        package, so we surface those extra files here.
        """
        with open(dsc_path, "r", encoding="utf-8") as fh:
            dsc_info = Deb822(fh.read().split("\n"))

        dsc_files_str = dsc_info.get_as_string("Files")
        if not dsc_files_str:
            return []

        return [line.split()[2] for line in dsc_files_str.strip().split("\n")]

    def source_package_exists(self, dsc_path: Path) -> bool:
        """Check whether all source files listed in a .dsc are present in the
        apt source cache.

        Looks up the source record by name + version in the apt SourceRecords
        index.  If a matching record is found, all files from the .dsc are
        logged as [EXISTS]; otherwise each file is logged as [MISSING].

        Requires ``deb-src`` to be listed in the apt sources entry so that
        aptly serves the Sources index and apt-get update downloads it.
        """
        parsed = self._parse_dsc_file(dsc_path)
        if parsed is None:
            return False
        name, version = parsed

        source_files = self.deb_dsc_extra_files(dsc_path)
        if not source_files:
            return False

        try:
            records = apt_pkg.SourceRecords()
            found = False
            while records.lookup(name):
                if records.version == version:
                    found = True
                    break

            for f in source_files:
                if found:
                    self.logger.info("[EXISTS]   %s (source)", f)
                else:
                    self.logger.warning("[MISSING]  %s (source)", f)
            return found
        except Exception:
            self.logger.exception("Failed source package lookup for %s", dsc_path)
            return False

    # ------------------------------------------------------------------ #
    # Private helpers                                                      #
    # ------------------------------------------------------------------ #

    def _parse_dsc_file(self, dsc_path: Path) -> Optional[tuple[str, str]]:
        """Parse a .dsc file and return (name, version), or None on failure."""
        path = Path(dsc_path)
        if not path.is_file():
            return None
        try:
            fields: dict[str, str] = {}
            for line in path.read_text(encoding="utf-8").splitlines():
                if (
                    ":" in line
                    and not line.startswith(" ")
                    and not line.startswith("-")
                ):
                    key, _, value = line.partition(":")
                    fields[key.strip().lower()] = value.strip()
            name = fields.get("source") or fields.get("package")
            version = fields.get("version")
            if name and version:
                return name, version
        except Exception:
            pass
        return None

    def _parse_deb_file(self, filepath: Path) -> Optional[DebFileInfo]:
        """
        Parse a Debian binary package into a DebFileInfo named tuple.
        Uses apt_inst.DebFile which reads only the control.tar member.
        """
        path = Path(filepath)
        if not path.is_file():
            return None
        try:
            deb = apt_inst.DebFile(str(path))
            control_data = deb.control.extractdata("control").decode("utf-8")
            fields = {}
            for line in control_data.splitlines():
                if ":" in line and not line.startswith(" "):
                    key, _, value = line.partition(":")
                    fields[key.strip().lower()] = value.strip()
            return DebFileInfo(
                name=fields["package"],
                version=fields["version"],
                arch=fields["architecture"],
            )
        except Exception:
            return None

    def _resolve_package_name(self, package_name: str) -> Optional[str]:
        if package_name in self.cache:
            return package_name

        # The name may be a virtual package.  Walk provides_list to
        # find a real package that satisfies it.
        # provides_list entries are tuples: (virtual_name, provided_version, apt_pkg.Version)
        try:
            apt_pkg_entry = self.cache._cache[package_name]
            providers = [v[2].parent_pkg.name for v in apt_pkg_entry.provides_list]
        except (KeyError, AttributeError):
            providers = []

        if not providers:
            return None

        real_name = providers[0]
        self.logger.info(
            "Package '%s' is virtual; using provider '%s' instead.",
            package_name,
            real_name,
        )
        return real_name

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
